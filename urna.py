"""
Urna Eletronica — voting-machine screen simulator for a presidential runoff
(2º turno: a single cargo, two candidates), driven entirely from Python
running in Pyodide. Mirrors the design mockup's state machine: digit entry ->
candidate lookup / null vote / blank vote -> confirm -> fim.

Which election is on screen comes from `eleicoes.py` via the `ano` option, so
the same terminal renders any of the runoffs in the page's selector.
"""
from js import document, window
from pyodide.ffi import create_proxy, to_js

import eleicoes

BRAILLE = {'1': '⠁', '2': '⠃', '3': '⠉', '4': '⠙', '5': '⠑', '6': '⠋', '7': '⠛', '8': '⠓', '9': '⠊', '0': '⠚'}

THEMES = {
    'tse': {
        '--s-bg': 'var(--color-neutral-100)', '--s-ink': 'var(--color-neutral-900)',
        '--s-muted': 'var(--color-neutral-700)', '--s-line': 'var(--color-neutral-300)',
        '--s-accent': 'var(--color-accent-700)', '--s-photo': 'var(--color-neutral-200)',
    },
    'contraste': {
        '--s-bg': 'var(--color-bg)', '--s-ink': 'var(--color-text)',
        '--s-muted': 'var(--color-neutral-400)', '--s-line': 'var(--color-neutral-800)',
        '--s-accent': 'var(--color-accent)', '--s-photo': 'var(--color-surface)',
    },
}

# One random face per candidate slot for the life of the page (mirrors the
# design's window.__urnaFaceSeed): stable while voting, fresh on reload.
_FACE_SEED = None


def _face_seed():
    global _FACE_SEED
    if _FACE_SEED is None:
        existing = getattr(window, '__urnaFaceSeed', None)
        if existing:
            _FACE_SEED = str(existing)
        else:
            import random
            import string
            _FACE_SEED = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
            window.__urnaFaceSeed = _FACE_SEED
    return _FACE_SEED


def face_url(key, female):
    seed = _face_seed() + key
    h = 0
    for ch in seed:
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    idx = h % 100
    gender_path = 'women' if female else 'men'
    return f'https://randomuser.me/api/portraits/{gender_path}/{idx}.jpg'


def esc(s):
    return (str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))


def photo_html(cls, src, alt, caption):
    """Real face photo (randomuser.me), filling the same plain photo-box
    the real urna screen uses for the candidate/vice portraits."""
    return (
        f'<div class="photo-item">'
        f'<div class="photo-box {cls}"><img src="{esc(src)}" alt="{esc(alt)}" '
        f'style="width:100%;height:100%;object-fit:cover" loading="lazy"></div>'
        f'<span class="photo-caption">{esc(caption)}</span>'
        f'</div>'
    )


class Urna:
    def __init__(self, root, theme='tse', teclado=True, teclas=True,
                 libras=True, som=True, vinculada=False, ano=None):
        self.root = root
        self.theme = theme
        self.teclado = teclado
        self.teclas = teclas
        self.libras = libras
        self.som = som
        self.vinculada = vinculada

        self.eleicao = eleicoes.get(ano or eleicoes.DEFAULT)
        self.cands = eleicoes.cands_map(self.eleicao['ano'])

        self.num = ''
        self.branco = False
        self.fim = False
        # When vinculada (gated by the mesário terminal), the keypad stays
        # locked until a urna-liberar event arrives for this voter.
        self.liberada = not vinculada

        # Módulo Impressor: the real printer is built into the voter
        # terminal's own cabinet (not the mesário terminal), so it renders
        # here. Each entry is one cut, printed receipt (zerésima/resumo/BU/
        # BUJ/BIM), newest on top, mirroring the real auto-cutter producing
        # a separate strip per document rather than one continuous roll.
        self.recibos = []

        self._ac = None
        self._kd_proxy = None
        self._click_proxy = None
        self._liberar_proxy = None
        self._print_zeresima_proxy = None
        self._print_bu_proxy = None

        if self.teclas:
            self._kd_proxy = create_proxy(self._on_keydown)
            window.addEventListener('keydown', self._kd_proxy)

        self._click_proxy = create_proxy(self._on_click)
        self.root.addEventListener('click', self._click_proxy)

        if self.vinculada:
            self._liberar_proxy = create_proxy(self._on_liberar)
            window.addEventListener('urna-liberar', self._liberar_proxy)

        self._print_zeresima_proxy = create_proxy(self._on_print_zeresima)
        window.addEventListener('urna-print-zeresima', self._print_zeresima_proxy)
        self._print_bu_proxy = create_proxy(self._on_print_bu)
        window.addEventListener('urna-print-bu', self._print_bu_proxy)

        self.render()

    def destroy(self):
        if self._kd_proxy:
            window.removeEventListener('keydown', self._kd_proxy)
            self._kd_proxy.destroy()
        if self._click_proxy:
            self.root.removeEventListener('click', self._click_proxy)
            self._click_proxy.destroy()
        if self._liberar_proxy:
            window.removeEventListener('urna-liberar', self._liberar_proxy)
            self._liberar_proxy.destroy()
        if self._print_zeresima_proxy:
            window.removeEventListener('urna-print-zeresima', self._print_zeresima_proxy)
            self._print_zeresima_proxy.destroy()
        if self._print_bu_proxy:
            window.removeEventListener('urna-print-bu', self._print_bu_proxy)
            self._print_bu_proxy.destroy()

    def _on_liberar(self, e):
        self.num = ''
        self.branco = False
        self.fim = False
        self.liberada = True
        self.render()

    def _on_print_zeresima(self, e):
        detail = e.detail.to_py() if hasattr(e.detail, 'to_py') else dict(e.detail)
        self.recibos.insert(0, {'tipo': 'ZERÉSIMA', 'linhas': detail['zeresima']})
        self.recibos.insert(0, {'tipo': 'RESUMO DA ZERÉSIMA', 'linhas': detail['resumo']})
        self.render()

    def _on_print_bu(self, e):
        detail = e.detail.to_py() if hasattr(e.detail, 'to_py') else dict(e.detail)
        self.recibos.insert(0, {'tipo': 'BIM — BOLETIM DE IDENTIFICAÇÃO DA MÍDIA', 'linhas': detail['bim']})
        self.recibos.insert(0, {'tipo': 'BUJ — BOLETIM DE URNA DA JUSTIFICATIVA', 'linhas': detail['buj']})
        self.recibos.insert(0, {'tipo': 'BOLETIM DE URNA', 'linhas': detail['bu']})
        self.render()

    # ---- audio ----
    def tone(self, freq, dur, at=0.0):
        if not self.som:
            return
        try:
            if self._ac is None:
                ctor = getattr(window, 'AudioContext', None) or window.webkitAudioContext
                self._ac = ctor.new()
            ac = self._ac
            t = ac.currentTime + at
            osc = ac.createOscillator()
            gain = ac.createGain()
            osc.type = 'square'
            osc.frequency.value = freq
            gain.gain.setValueAtTime(0.0001, t)
            gain.gain.exponentialRampToValueAtTime(0.06, t + 0.005)
            gain.gain.setValueAtTime(0.06, t + dur - 0.01)
            gain.gain.exponentialRampToValueAtTime(0.0001, t + dur)
            osc.connect(gain)
            gain.connect(ac.destination)
            osc.start(t)
            osc.stop(t + dur + 0.02)
        except Exception:
            pass

    def fim_sound(self):
        for t in (0, 0.12, 0.24, 0.36):
            self.tone(1150, 0.08, t)
        self.tone(1150, 0.5, 0.48)

    # ---- input handling ----
    def _on_keydown(self, e):
        tag = getattr(e.target, 'tagName', '') or ''
        if tag in ('INPUT', 'TEXTAREA'):
            return
        key = e.key
        if len(key) == 1 and key.isdigit():
            self.press(key)
        elif key == 'Backspace':
            e.preventDefault()
            self.press('corrige')
        elif key == 'Enter':
            self.press('confirma')
        elif key in ('b', 'B'):
            self.press('branco')

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
        if action == 'reset':
            self.reset()
        else:
            self.press(action)

    def press(self, k):
        if self.fim or (self.vinculada and not self.liberada):
            return
        if k.isdigit():
            if self.branco or len(self.num) >= 2:
                return
            self.tone(980, 0.07)
            self.num += k
        elif k == 'branco':
            if self.num or self.branco:
                return
            self.tone(980, 0.07)
            self.branco = True
        elif k == 'corrige':
            self.tone(760, 0.09)
            self.num = ''
            self.branco = False
        elif k == 'confirma':
            if not (self.branco or len(self.num) == 2):
                return
            self.fim_sound()
            self.fim = True
            if self.vinculada:
                self.liberada = False
            # Announced even when voting freely (not vinculada): the page uses
            # this to offer the mesário terminal after the first vote, and the
            # mesário itself ignores the event unless it is mid-votação.
            resultado = 'branco' if self.branco else (self.num if self.num in self.cands else 'nulo')
            detail = to_js({'detail': {'resultado': resultado}}, dict_converter=window.Object.fromEntries)
            window.dispatchEvent(window.CustomEvent.new('urna-fim', detail))
        self.render()

    def reset(self):
        self.num = ''
        self.branco = False
        self.fim = False
        self.render()

    # ---- módulo impressor ----
    def _render_printer(self):
        """Thermal printer (Módulo Impressor): built into the voter terminal's
        own cabinet, behind the screen — so printed strips feed up and out
        through a slot at the top-back of the machine, not a separate box.
        Direct-thermal, 57mm paper, auto-cutter — each document comes out as
        its own cut strip, newest on top."""
        if not self.recibos:
            return ''
        strips_html = ''.join(
            '<div class="recibo">'
            f'<div class="recibo-tipo">{esc(r["tipo"])}</div>'
            + ''.join(f'<div class="recibo-linha">{esc(linha)}</div>' for linha in r['linhas'])
            + '</div>'
            for r in self.recibos
        )
        return f'<div class="printer-tray">{strips_html}</div>'

    # ---- render ----
    def render(self):
        theme = THEMES.get(self.theme, THEMES['tse'])
        num, branco, fim = self.num, self.branco, self.fim
        espera = self.vinculada and not self.liberada and not fim

        cand = self.cands.get(num) if len(num) == 2 else None
        is_cand = bool(cand) and not fim
        is_nulo = len(num) == 2 and not cand and not fim
        is_branco = branco and not fim

        # A runoff ballot has a single cargo, so the progress bar is one step:
        # in progress while voting, done at FIM.
        if fim:
            bar = theme['--s-ink']
            txt = '✓ Presidente'
            extra = f"color:{theme['--s-muted']}"
        else:
            bar = theme['--s-accent']
            txt = '● Presidente'
            extra = f"color:{theme['--s-ink']};font-weight:700"
        steps_html = [
            f'<div class="progress-col">'
            f'<div class="progress-bar" style="background:{bar}"></div>'
            f'<div class="progress-label" style="{extra}">{txt}</div>'
            f'</div>'
        ]

        d1 = num[0] if len(num) > 0 else ''
        d2 = num[1] if len(num) > 1 else ''
        cur1 = (len(num) == 0 and not branco and not espera)
        cur2 = (len(num) == 1)

        show_seu_voto = len(num) > 0 or branco

        libras_label = 'Presidente'
        if is_nulo:
            libras_label = 'Voto nulo'
        elif is_branco:
            libras_label = 'Voto em branco'
        elif is_cand:
            libras_label = 'Confira e confirme'

        screen_style_vars = ';'.join(f'{k}:{v}' for k, v in theme.items())

        if espera:
            body_html = (
                '<div class="espera-screen">'
                '<div class="espera-brasao">brasão</div>'
                '<span class="espera-title">JUSTIÇA ELEITORAL</span>'
                '</div>'
                '<div class="espera-footer">'
                f'<span>{esc(eleicoes.secao_label())}</span>'
                f'<span>{esc(eleicoes.SECAO["local"])}</span>'
                '</div>'
            )
        elif fim:
            body_html = '<div class="fim-screen">FIM</div>'
        else:
            left_parts = []
            left_parts.append(
                f'<div class="seu-voto">{"SEU VOTO PARA" if show_seu_voto else ""}</div>'
            )
            left_parts.append('<div class="cargo-label">Presidente</div>')

            if not branco:
                cursor1 = '<span class="cursor-blink"></span>' if cur1 else ''
                cursor2 = '<span class="cursor-blink"></span>' if cur2 else ''
                left_parts.append(
                    '<div class="numero-row">'
                    '<span class="numero-label">Número:</span>'
                    f'<div class="digit-box">{esc(d1)}{cursor1}</div>'
                    f'<div class="digit-box">{esc(d2)}{cursor2}</div>'
                    '</div>'
                )

            if is_cand:
                left_parts.append(
                    '<div class="cand-grid">'
                    f'<span>Nome:</span><span><b>{esc(cand["nome"])}</b></span>'
                    f'<span>Partido:</span><span><b>{esc(cand["partido"])}</b></span>'
                    f'<span style="white-space:nowrap">Vice-Presidente:</span><span><b>{esc(cand["vice"])}</b></span>'
                    '</div>'
                )
            if is_nulo:
                left_parts.append(
                    '<div class="nulo-box">'
                    '<span class="nulo-title">NÚMERO ERRADO</span>'
                    '<span class="nulo-sub">VOTO NULO</span>'
                    '</div>'
                )
            if is_branco:
                left_parts.append(
                    '<div class="branco-box"><span class="branco-txt">VOTO EM BRANCO</span></div>'
                )

            right_html = ''
            if is_cand:
                pres_src = face_url(cand['num'], cand['gender'] == 'f')
                vice_src = face_url(cand['num'] + 'v', cand['gender_vice'] == 'f')
                pres_photo = photo_html('photo-pres', pres_src,
                                         f'Foto do candidato a Presidente {cand["num"]}', 'Presidente')
                vice_photo = photo_html('photo-vice', vice_src,
                                         f'Foto do candidato a Vice-Presidente {cand["num"]}', 'Vice-Presidente')
                right_html = f'<div class="photos-col">{pres_photo}{vice_photo}</div>'

            body_html = (
                f'<div class="body-row">'
                f'<div class="left-col">{"".join(left_parts)}</div>'
                f'{right_html}'
                f'</div>'
            )

            if is_cand or is_nulo or is_branco:
                body_html += (
                    '<div class="footer-row">'
                    '<span>Aperte a tecla:</span>'
                    '<span class="footer-indent"><b>CONFIRMA</b> para <b>CONFIRMAR</b> este voto</span>'
                    '<span class="footer-indent"><b>CORRIGE</b> para <b>REINICIAR</b> este voto</span>'
                    '</div>'
                )

        libras_html = ''
        if self.libras and not fim and not espera:
            libras_html = (
                '<div class="libras-box">'
                '<span class="libras-kicker">Intérprete Libras</span>'
                f'<span class="libras-label">{esc(libras_label)}</span>'
                '</div>'
            )

        progress_html = '' if espera else f'<div class="progress-row">{"".join(steps_html)}</div>'

        screen_html = (
            f'<div class="screen" style="{screen_style_vars}" data-screen-label="Tela da urna">'
            f'{progress_html}'
            f'{body_html}'
            f'{libras_html}'
            f'</div>'
        )

        keyboard_html = ''
        if self.teclado:
            keys_html = []
            for d in '123456789':
                mark = '<span class="key-mark"></span>' if d == '5' else ''
                keys_html.append(
                    f'<button type="button" class="key" data-action="{d}" aria-label="Tecla {d}">'
                    f'<span>{d}</span><span class="key-braille">{BRAILLE[d]}</span>{mark}'
                    f'</button>'
                )
            keypad_html = (
                '<div class="keypad">'
                f'{"".join(keys_html)}'
                f'<button type="button" class="key key-zero" data-action="0" aria-label="Tecla 0">'
                f'<span>0</span><span class="key-braille">{BRAILLE["0"]}</span>'
                f'</button>'
                '</div>'
            )
            keyboard_html = (
                '<div class="keyboard">'
                '<div class="keyboard-head"><span>JUSTIÇA ELEITORAL</span>'
                '<span class="brasao">brasão</span></div>'
                f'{keypad_html}'
                '<div class="action-row">'
                '<button type="button" class="key-branco" data-action="branco">BRANCO</button>'
                '<button type="button" class="key-corrige" data-action="corrige">CORRIGE</button>'
                '<button type="button" class="key-confirma" data-action="confirma">CONFIRMA</button>'
                '</div>'
                '</div>'
            )

        printer_html = self._render_printer()
        screen_stack_html = f'<div class="screen-stack">{printer_html}{screen_html}</div>'

        shell_class = 'shell' if self.teclado else 'shell no-keyboard'
        shell_html = f'<div class="{shell_class}">{screen_stack_html}{keyboard_html}</div>'

        below_html = ''
        if self.teclado:
            if self.vinculada:
                hint = 'Liberada pelo terminal do mesário'
                reset_btn = ''
            else:
                hint = ('Teclado físico: 0–9 · B = branco · ⌫ = corrige · Enter = confirma'
                        if self.teclas else 'Clique nas teclas para votar')
                reset_btn = '<button type="button" class="btn" data-action="reset">Liberar nova votação</button>'
            below_html = (
                '<div class="below-row">'
                f'{reset_btn}'
                f'<span>{esc(hint)}</span>'
                '</div>'
            )

        self.root.innerHTML = shell_html + below_html


def mount(selector, opts=None):
    """opts: a Python dict (pass pyodide.toPy({...}) from JS) with
    theme/teclado/teclas/libras/som/vinculada/ano."""
    root = document.querySelector(selector)
    kwargs = dict(opts) if opts else {}
    return Urna(root, **kwargs)
