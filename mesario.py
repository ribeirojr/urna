"""
Terminal do Mesário 2026 — poll-worker terminal, driven from Python in
Pyodide. Mirrors the design mockup's flow: identificação (CPF/título) ->
biometria (fingerprint reader, simulated failure after 4 tries falls back
to birth-year confirmation) -> libera o voto -> aguarda o fim do voto na
urna (via window events 'urna-liberar' / 'urna-fim') -> concluído.
"""
from js import document, window
from pyodide.ffi import create_proxy

ELEITOR = {'nome': 'Ana Beatriz Moura', 'titulo': '0123 4567 8901', 'ano': '1987'}


def esc(s):
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def fmt_titulo(s):
    out = []
    for i, ch in enumerate(s):
        out.append(ch)
        if (i + 1) % 4 == 0 and i + 1 != len(s):
            out.append(' ')
    return ''.join(out)


class Mesario:
    def __init__(self, root, teclado=True):
        self.root = root
        self.teclado = teclado

        self.fase = 'ident'  # ident -> bio -> ano (fallback) -> votando -> concluido
        self.campo = ''
        self.tentativa = 0

        self._click_proxy = create_proxy(self._on_click)
        self.root.addEventListener('click', self._click_proxy)

        self._fim_proxy = create_proxy(self._on_urna_fim)
        window.addEventListener('urna-fim', self._fim_proxy)

        self.render()

    def destroy(self):
        self.root.removeEventListener('click', self._click_proxy)
        self._click_proxy.destroy()
        window.removeEventListener('urna-fim', self._fim_proxy)
        self._fim_proxy.destroy()

    def _on_urna_fim(self, e):
        if self.fase == 'votando':
            self.fase = 'concluido'
            self.render()

    def _on_click(self, e):
        target = e.target
        action = None
        depth = 0
        while target is not None and depth < 6:
            action = target.getAttribute('data-action') if hasattr(target, 'getAttribute') else None
            if action:
                break
            target = getattr(target, 'parentElement', None)
            depth += 1
        if not action:
            return
        if action.startswith('digit:'):
            self.digit(action.split(':', 1)[1])
        elif action == 'corrige':
            self.corrige()
        elif action == 'confirma':
            self.confirma()
        elif action == 'ler-digital':
            self.ler_digital()
        elif action == 'falha-digital':
            self.falha_digital()
        elif action == 'exemplo':
            self.exemplo()

    def digit(self, d):
        if self.fase == 'ident' and len(self.campo) < 12:
            self.campo += d
        elif self.fase == 'ano' and len(self.campo) < 4:
            self.campo += d
        else:
            return
        self.render()

    def corrige(self):
        if self.fase in ('ident', 'ano'):
            self.campo = ''
        elif self.fase == 'bio':
            self.fase = 'ident'
            self.campo = ''
            self.tentativa = 0
        self.render()

    def confirma(self):
        if self.fase == 'ident' and len(self.campo) >= 11:
            self.fase = 'bio'
            self.campo = ''
            self.tentativa = 0
        elif self.fase == 'ano' and len(self.campo) == 4:
            self.liberar()
            return
        elif self.fase == 'concluido':
            self.fase = 'ident'
            self.campo = ''
            self.tentativa = 0
        self.render()

    def liberar(self):
        self.fase = 'votando'
        self.campo = ''
        self.render()
        window.dispatchEvent(window.Event.new('urna-liberar'))

    def ler_digital(self):
        if self.fase == 'bio':
            self.liberar()

    def falha_digital(self):
        if self.fase != 'bio':
            return
        t = self.tentativa + 1
        if t >= 4:
            self.fase = 'ano'
            self.campo = ''
            self.tentativa = t
        else:
            self.tentativa = t
        self.render()

    def exemplo(self):
        if self.fase == 'ident':
            self.campo = '012345678901'
            self.render()

    def render(self):
        fase, campo, tentativa = self.fase, self.campo, self.tentativa
        votando = fase == 'votando'

        if fase == 'ident':
            body = (
                '<div class="tm-body">'
                '<span class="tm-label">IDENTIFICAÇÃO DO ELEITOR</span>'
                '<span class="tm-text">Digite o CPF ou o número do título:</span>'
                f'<div class="tm-field">{esc(fmt_titulo(campo))}<span class="tm-cursor"></span></div>'
                '<span class="tm-hint">CONFIRMA para prosseguir · CORRIGE para apagar</span>'
                '</div>'
            )
        elif fase == 'bio':
            body = (
                '<div class="tm-body">'
                f'<span class="tm-nome">{esc(ELEITOR["nome"])}</span>'
                f'<span class="tm-sub">Título {esc(ELEITOR["titulo"])} · Seção 0412</span>'
                '<span class="tm-badge">APTO A VOTAR</span>'
                '<div class="tm-bio-row">'
                '<i class="tm-fingerprint-icon">⚹</i>'
                '<div class="tm-bio-text">'
                '<span class="tm-bio-title">Posicione o dedo no leitor biométrico</span>'
                f'<span class="tm-sub">Tentativa {min(tentativa + 1, 4)} de 4</span>'
                '</div></div></div>'
            )
        elif fase == 'ano':
            boxes = ''.join(
                f'<div class="tm-ano-box">{esc(campo[i]) if i < len(campo) else ""}</div>'
                for i in range(4)
            )
            body = (
                '<div class="tm-body">'
                '<span class="tm-label">BIOMETRIA NÃO RECONHECIDA</span>'
                '<span class="tm-text">Confira o documento e digite o <b>ANO DE NASCIMENTO</b> do eleitor:</span>'
                f'<div class="tm-ano-row">{boxes}</div>'
                f'<span class="tm-hint">{esc(ELEITOR["nome"])} · CONFIRMA para habilitar</span>'
                '</div>'
            )
        elif fase == 'votando':
            body = (
                '<div class="tm-body">'
                '<span class="tm-label">ELEITOR HABILITADO</span>'
                f'<span class="tm-nome">{esc(ELEITOR["nome"])}</span>'
                '<div class="tm-progress-mini"><div class="tm-progress-bar"></div>'
                '<span class="tm-progress-label">● Presidente · em votação</span></div>'
                '<span class="tm-blink">Eleitor votando…</span>'
                '</div>'
            )
        else:  # concluido
            body = (
                '<div class="tm-body">'
                '<span class="tm-label">VOTO CONCLUÍDO</span>'
                f'<span class="tm-nome">{esc(ELEITOR["nome"])}</span>'
                '<div class="tm-progress-mini"><div class="tm-progress-bar tm-progress-done"></div>'
                '<span class="tm-progress-label tm-progress-label-done">✓ Presidente</span></div>'
                '<span class="tm-text">CONFIRMA para o próximo eleitor</span>'
                '</div>'
            )

        screen_html = (
            '<div class="tm-screen" data-screen-label="Tela do terminal do mesário">'
            '<div class="tm-topbar"><span>Zona ZZ · Seção 0412 · Lisboa</span><span>Exterior</span></div>'
            f'{body}'
            '</div>'
        )

        keyboard_html = ''
        if self.teclado:
            keys_html = ''.join(
                f'<button type="button" class="tm-key" data-action="digit:{d}">{d}</button>'
                for d in '123456789'
            )
            keypad_html = (
                '<div class="tm-keypad">'
                f'{keys_html}'
                '<button type="button" class="tm-key tm-key-corrige" data-action="corrige">CORRIGE</button>'
                '<button type="button" class="tm-key" data-action="digit:0">0</button>'
                '<button type="button" class="tm-key tm-key-confirma" data-action="confirma">CONFIRMA</button>'
                '</div>'
            )
            led_votando = 'tm-led-on' if votando else ''
            led_pronta = 'tm-led-on' if not votando else ''
            keyboard_html = (
                '<div class="tm-keyboard">'
                '<div class="tm-leds">'
                f'<div class="tm-led-item"><span class="tm-led {led_votando}"></span>Em votação</div>'
                f'<div class="tm-led-item"><span class="tm-led {led_pronta}"></span>Pronta</div>'
                '<div class="tm-led-item"><span class="tm-led tm-led-power"></span>Energia</div>'
                '</div>'
                f'{keypad_html}'
                '</div>'
            )
            reader_class = 'tm-reader-active' if fase == 'bio' else ''
            reader_hint = ('Clique para ler a digital' if fase == 'bio'
                            else ('Aguardando o fim do voto' if votando else '—'))
            keyboard_html += (
                '<div class="tm-reader-col">'
                f'<button type="button" class="tm-reader {reader_class}" data-action="ler-digital" '
                'aria-label="Leitor biométrico">⚹</button>'
                '<span class="tm-reader-label">LEITOR BIOMÉTRICO</span>'
                f'<span class="tm-reader-hint">{esc(reader_hint)}</span>'
                '</div>'
            )

        shell_html = f'<div class="tm-shell">{screen_html}{keyboard_html}</div>'

        below_html = ''
        if self.teclado:
            below_html = (
                '<div class="below-row">'
                '<button type="button" class="btn btn-secondary" data-action="exemplo">Preencher título de exemplo</button>'
                '<button type="button" class="btn btn-ghost" data-action="falha-digital">Simular falha na digital</button>'
                '</div>'
            )

        self.root.innerHTML = shell_html + below_html


def mount(selector, opts=None):
    root = document.querySelector(selector)
    kwargs = dict(opts) if opts else {}
    return Mesario(root, **kwargs)
