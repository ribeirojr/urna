"""
Terminal do Mesário — poll-worker terminal, driven from Python in Pyodide.
Mirrors the real documented flow (Manual/Guia Rápido do Mesário, TSE
"Encerramento da Votação" post-2024 procedure):

  zerésima (zero-report, 7h) -> registro de mesários (each present poll
  worker's título + CONFIRMA, CORRIGE to finish) -> identificação do
  eleitor (CPF/título) -> biometria (até 4 tentativas; falha cai para
  confirmação por ano de nascimento) -> libera o voto -> aguarda o fim do
  voto na urna (via window events 'urna-liberar' / 'urna-fim') ->
  concluído -> próximo eleitor.

CORRIGE on the identificação screen is not just "erase" — it opens the
real "outras opções" menu (encerrar votação / registrar mesários tardios
/ exibir contadores / ativar áudio). Encerramento itself is: menu opção 2
-> confirma fila vazia -> título do presidente de mesa + CONFIRMA ->
imprime BU + BUJ + BIM. A "suspensão da votação" incident flow (voter
authorized but doesn't vote) is reachable the same way — CORRIGE during
biometria/votação, authorized by the presidente's título — and ends that
voter's session without casting a vote.
"""
from js import document, window
from pyodide.ffi import create_proxy, to_js

import eleicoes


def dispatch(name, detail):
    js_detail = to_js({'detail': detail}, dict_converter=window.Object.fromEntries)
    window.dispatchEvent(window.CustomEvent.new(name, js_detail))


ELEITOR = {'nome': 'Ana Beatriz Moura', 'titulo': '0123 4567 8901', 'ano': '1987'}
PRESIDENTE_TITULO = '9988 7766 5544'

MESARIOS_PRESENTES = ['Carlos Eduardo Lima', 'Fernanda Rocha Dias']

MENU_OPCOES = [
    {'id': 'registrar', 'n': '1', 'label': 'Registrar mesário'},
    {'id': 'encerrar', 'n': '2', 'label': 'Encerrar votação'},
    {'id': 'contadores', 'n': '3', 'label': 'Exibir contadores'},
    {'id': 'audio', 'n': '4', 'label': 'Ativar/desativar áudio'},
]

# The candidate slate for the zerésima/BU printouts comes from eleicoes.py,
# the same source the urna reads: the two terminals have to agree on which
# election is loaded, so the election selector cannot leave one of them
# printing another year's candidates.


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
    def __init__(self, root, teclado=True, ano=None):
        self.root = root
        self.teclado = teclado

        self.eleicao = eleicoes.get(ano or eleicoes.DEFAULT)
        self.cands = self.eleicao['cands']

        # zeresima -> registro_mesarios -> ident <-> menu -> (encerrar_fila
        # -> encerrar_titulo) -> encerrada; ident -> bio -> ano -> votando
        # -> concluido; bio/votando -(CORRIGE)-> suspensao_titulo
        self.fase = 'zeresima'
        self.campo = ''
        self.tentativa = 0
        self.zeresima_impressa = False
        self.urna_encerrada = False
        self.audio_ativo = False
        self.mesarios_registrados = []
        self._fase_antes_suspensao = None

        # Running section tally, fed by each voter's urna-fim result — the
        # real BU reports these totals once at close of polls, not per voter.
        self.votos = {c['num']: 0 for c in self.cands}
        self.votos_branco = 0
        self.votos_nulo = 0
        self.comparecimento = 0
        self.suspensoes = 0

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
        if self.fase != 'votando':
            return
        detail = e.detail.to_py() if hasattr(e.detail, 'to_py') else dict(e.detail)
        resultado = detail.get('resultado')
        self.comparecimento += 1
        if resultado == 'branco':
            self.votos_branco += 1
        elif resultado in self.votos:
            self.votos[resultado] += 1
        else:
            self.votos_nulo += 1
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
        elif action.startswith('menu:'):
            self.escolher_menu(action.split(':', 1)[1])
        elif action == 'voltar':
            self.voltar()

    # ---- entrada ----
    def digit(self, d):
        if self.fase == 'menu':
            # Real hardware: the menu options are picked with the same
            # numeric keypad, by the number shown next to each option —
            # not a mouse click on an on-screen button.
            opcao = next((o['id'] for o in MENU_OPCOES if o['n'] == d), None)
            if opcao:
                self.escolher_menu(opcao)
            return
        if self.fase in ('ident', 'ano', 'registro_mesarios', 'encerrar_titulo', 'suspensao_titulo'):
            limite = 4 if self.fase == 'ano' else 12
            if len(self.campo) < limite:
                self.campo += d
        else:
            return
        self.render()

    def corrige(self):
        if self.fase == 'ident':
            if self.campo:
                self.campo = ''
            else:
                self.fase = 'menu'
        elif self.fase == 'ano':
            self.campo = ''
        elif self.fase in ('bio', 'votando'):
            self.pedir_suspensao()
            return
        elif self.fase == 'menu':
            self.fase = 'ident'
            self.campo = ''
        elif self.fase in ('encerrar_fila', 'encerrar_titulo', 'contadores'):
            self.fase = 'ident'
            self.campo = ''
        elif self.fase == 'suspensao_titulo':
            self.fase = self._fase_antes_suspensao or 'bio'
            self._fase_antes_suspensao = None
            self.campo = ''
        self.render()

    def confirma(self):
        if self.fase == 'zeresima':
            if not self.zeresima_impressa:
                self.imprimir_zeresima()
            else:
                self.abrir_votacao()
            return
        if self.fase == 'registro_mesarios':
            if self.campo and len(self.campo) >= 4:
                nome = MESARIOS_PRESENTES[len(self.mesarios_registrados) % len(MESARIOS_PRESENTES)]
                self.mesarios_registrados.append({'titulo': self.campo, 'nome': nome})
                self.campo = ''
            else:
                self.fase = 'ident'
                self.campo = ''
            self.render()
            return
        if self.fase == 'ident' and not self.urna_encerrada and len(self.campo) >= 11:
            self.fase = 'bio'
            self.campo = ''
            self.tentativa = 0
        elif self.fase == 'ano' and len(self.campo) == 4:
            self.liberar()
            return
        elif self.fase == 'concluido' and not self.urna_encerrada:
            self.fase = 'ident'
            self.campo = ''
            self.tentativa = 0
        elif self.fase == 'encerrar_fila':
            self.fase = 'encerrar_titulo'
            self.campo = ''
        elif self.fase == 'encerrar_titulo':
            if len(self.campo) >= 4:
                self._concluir_encerramento()
        elif self.fase == 'suspensao_titulo':
            if len(self.campo) >= 4:
                self._concluir_suspensao()
        self.render()

    def voltar(self):
        self.fase = 'ident'
        self.campo = ''
        self.render()

    # ---- menu CORRIGE ("outras opções") ----
    def escolher_menu(self, opcao):
        if self.fase != 'menu':
            return
        if opcao == 'registrar':
            self.fase = 'registro_mesarios'
            self.campo = ''
        elif opcao == 'encerrar':
            if self.urna_encerrada:
                return
            self.fase = 'encerrar_fila'
        elif opcao == 'contadores':
            self.fase = 'contadores'
        elif opcao == 'audio':
            self.audio_ativo = not self.audio_ativo
            self.fase = 'ident'
        self.render()

    def _concluir_encerramento(self):
        self.urna_encerrada = True
        self.fase = 'ident'
        self.campo = ''
        dispatch('urna-print-bu', {
            'bu': self._linhas_bu(),
            'buj': self._linhas_buj(),
            'bim': self._linhas_bim(),
        })

    # ---- biometria / liberação ----
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
        if self.fase == 'ident' and not self.urna_encerrada:
            self.campo = '012345678901'
            self.render()

    # ---- suspensão da votação (eleitor autorizado que não vota) ----
    def pedir_suspensao(self):
        if self.fase not in ('bio', 'votando'):
            return
        self._fase_antes_suspensao = self.fase
        self.fase = 'suspensao_titulo'
        self.campo = ''
        self.render()

    def _concluir_suspensao(self):
        self.suspensoes += 1
        self._fase_antes_suspensao = None
        self.fase = 'ident'
        self.campo = ''
        self.tentativa = 0

    # ---- zerésima / encerramento ----
    def imprimir_zeresima(self):
        if self.fase == 'zeresima' and not self.zeresima_impressa:
            self.zeresima_impressa = True
            dispatch('urna-print-zeresima', {
                'zeresima': self._linhas_zeresima(),
                'resumo': self._linhas_resumo_zeresima(),
            })
            self.render()

    def abrir_votacao(self):
        if self.fase == 'zeresima' and self.zeresima_impressa:
            self.fase = 'registro_mesarios'
            self.campo = ''
            self.render()

    # ---- conteúdo dos recibos (Módulo Impressor) ----
    def _linhas_zeresima(self):
        linhas = [eleicoes.secao_label(), 'Nenhum voto ou justificativa', 'registrado nesta urna.', '', 'PRESIDENTE DA REPÚBLICA']
        for c in self.cands:
            linhas.append(f'{c["num"]} {c["nome"][:22]} 0')
        linhas += ['Brancos 0', 'Nulos 0']
        return linhas

    def _linhas_resumo_zeresima(self):
        return [
            eleicoes.secao_label(),
            'Todos os cargos conferidos com',
            'zero votos e zero justificativas.',
            'Afixar em local visível.',
        ]

    def _linhas_bu(self):
        linhas = [
            eleicoes.secao_label(),
            'PRESIDENTE DA REPÚBLICA',
            f'Comparecimento: {self.comparecimento}',
        ]
        for c in self.cands:
            linhas.append(f'{c["num"]} {c["nome"][:22]} {self.votos[c["num"]]}')
        linhas += [f'Brancos {self.votos_branco}', f'Nulos {self.votos_nulo}']
        return linhas

    def _linhas_buj(self):
        return [
            eleicoes.secao_label(),
            'Justificativas de ausência',
            'registradas: 0',
            f'Votações suspensas: {self.suspensoes}',
        ]

    def _linhas_bim(self):
        linhas = [eleicoes.secao_label(), 'Mesários registrados:', f'Presidente — {PRESIDENTE_TITULO}']
        for m in self.mesarios_registrados:
            linhas.append(f'{m["nome"][:20]} — {m["titulo"]}')
        return linhas

    # ---- render ----
    def render(self):
        fase, campo, tentativa = self.fase, self.campo, self.tentativa
        votando = fase == 'votando'

        if fase == 'zeresima':
            if not self.zeresima_impressa:
                body = (
                    '<div class="tm-body">'
                    '<span class="tm-label">ANTES DE ABRIR A VOTAÇÃO</span>'
                    '<span class="tm-text">Confira, com testemunhas e fiscais presentes, que todos os candidatos estão com zero votos.</span>'
                    '<span class="tm-hint" style="margin-top:auto">CONFIRMA para imprimir a zerésima</span>'
                    '</div>'
                )
            else:
                rows = ''.join(
                    f'<div class="tm-zeresima-row"><span>{esc(c["num"])} · {esc(c["nome"])} ({esc(c["partido"])})</span><span>0</span></div>'
                    for c in self.cands
                )
                body = (
                    '<div class="tm-body tm-zeresima-body">'
                    '<span class="tm-label">ZERÉSIMA — PRESIDENTE DA REPÚBLICA</span>'
                    '<div class="tm-zeresima-list">'
                    f'{rows}'
                    '<div class="tm-zeresima-row"><span>Brancos</span><span>0</span></div>'
                    '<div class="tm-zeresima-row"><span>Nulos</span><span>0</span></div>'
                    '</div>'
                    '<span class="tm-hint">Relatório impresso e conferido · CONFIRMA para abrir a votação</span>'
                    '</div>'
                )
        elif fase == 'registro_mesarios':
            lista = ''.join(
                f'<div class="tm-zeresima-row"><span>{esc(m["nome"])}</span><span>{esc(m["titulo"])}</span></div>'
                for m in self.mesarios_registrados
            )
            body = (
                '<div class="tm-body">'
                '<span class="tm-label">REGISTRO DE MESÁRIOS</span>'
                '<span class="tm-text">Digite o título de cada mesário presente e aperte CONFIRMA. Quando todos estiverem registrados, aperte CONFIRMA com o campo vazio.</span>'
                f'<div class="tm-field">{esc(fmt_titulo(campo))}<span class="tm-cursor"></span></div>'
                f'<div class="tm-zeresima-list">{lista}</div>'
                '<span class="tm-hint" style="margin-top:auto">CONFIRMA para registrar · CONFIRMA vazio para iniciar a votação</span>'
                '</div>'
            )
        elif fase == 'menu':
            opcoes = ''.join(
                f'<button type="button" class="tm-menu-item" data-action="menu:{o["id"]}">'
                f'<span class="tm-menu-num">{o["n"]}</span>{esc(o["label"])}'
                f'</button>'
                for o in MENU_OPCOES
            )
            body = (
                '<div class="tm-body tm-menu-body">'
                '<span class="tm-label">OUTRAS OPÇÕES</span>'
                f'<div class="tm-menu-list">{opcoes}</div>'
                '<span class="tm-hint" style="margin-top:auto">CORRIGE para voltar</span>'
                '</div>'
            )
        elif fase == 'contadores':
            body = (
                '<div class="tm-body">'
                '<span class="tm-label">CONTADORES</span>'
                '<div class="tm-zeresima-list">'
                f'<div class="tm-zeresima-row"><span>Comparecimento total</span><span>{self.comparecimento}</span></div>'
                f'<div class="tm-zeresima-row"><span>Por biometria</span><span>{self.comparecimento}</span></div>'
                f'<div class="tm-zeresima-row"><span>Por digitação (ano)</span><span>0</span></div>'
                f'<div class="tm-zeresima-row"><span>Votações suspensas</span><span>{self.suspensoes}</span></div>'
                '</div>'
                '<span class="tm-hint" style="margin-top:auto">CORRIGE para voltar</span>'
                '</div>'
            )
        elif fase == 'encerrar_fila':
            body = (
                '<div class="tm-body">'
                '<span class="tm-label">ENCERRAR VOTAÇÃO</span>'
                '<span class="tm-text">Confirme que não há nenhum eleitor na fila ou na cabine de votação.</span>'
                '<span class="tm-hint" style="margin-top:auto">CONFIRMA para prosseguir · CORRIGE para cancelar</span>'
                '</div>'
            )
        elif fase == 'encerrar_titulo':
            body = (
                '<div class="tm-body">'
                '<span class="tm-label">AUTORIZAÇÃO DO PRESIDENTE DE MESA</span>'
                '<span class="tm-text">Digite o título de eleitor do presidente de mesa para autorizar o encerramento:</span>'
                f'<div class="tm-field">{esc(fmt_titulo(campo))}<span class="tm-cursor"></span></div>'
                '<span class="tm-hint">CONFIRMA para encerrar e imprimir BU/BUJ/BIM</span>'
                '</div>'
            )
        elif fase == 'suspensao_titulo':
            body = (
                '<div class="tm-body">'
                '<span class="tm-label">SUSPENSÃO DA VOTAÇÃO</span>'
                '<span class="tm-text">O eleitor está demorando ou se ausentou sem votar. Digite o título do presidente de mesa para autorizar a suspensão:</span>'
                f'<div class="tm-field">{esc(fmt_titulo(campo))}<span class="tm-cursor"></span></div>'
                '<span class="tm-hint">CONFIRMA para suspender este voto</span>'
                '</div>'
            )
        elif fase == 'ident' and self.urna_encerrada:
            body = (
                '<div class="tm-body">'
                '<span class="tm-label">VOTAÇÃO ENCERRADA</span>'
                '<span class="tm-text">Boletim de Urna, BUJ e BIM impressos. Nenhum eleitor pode mais ser identificado nesta seção.</span>'
                '</div>'
            )
        elif fase == 'ident':
            body = (
                '<div class="tm-body">'
                '<span class="tm-label">IDENTIFICAÇÃO DO ELEITOR</span>'
                '<span class="tm-text">Digite o CPF ou o número do título:</span>'
                f'<div class="tm-field">{esc(fmt_titulo(campo))}<span class="tm-cursor"></span></div>'
                '<span class="tm-hint">CONFIRMA para prosseguir · CORRIGE para outras opções</span>'
                '</div>'
            )
        elif fase == 'bio':
            body = (
                '<div class="tm-body">'
                f'<span class="tm-nome">{esc(ELEITOR["nome"])}</span>'
                f'<span class="tm-sub">Título {esc(ELEITOR["titulo"])} · Seção {esc(eleicoes.SECAO["secao"])}</span>'
                '<span class="tm-badge">APTO A VOTAR</span>'
                '<div class="tm-bio-row">'
                '<i class="tm-fingerprint-icon">⚹</i>'
                '<div class="tm-bio-text">'
                '<span class="tm-bio-title">Posicione o dedo no leitor biométrico</span>'
                f'<span class="tm-sub">Tentativa {min(tentativa + 1, 4)} de 4</span>'
                '</div></div>'
                '<span class="tm-hint" style="margin-top:auto">CORRIGE para suspender esta votação</span>'
                '</div>'
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
                '<span class="tm-hint">CORRIGE para suspender esta votação</span>'
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

        audio_tag = ' · ÁUDIO ATIVO' if self.audio_ativo else ''
        screen_html = (
            '<div class="tm-screen" data-screen-label="Tela do terminal do mesário">'
            f'<div class="tm-topbar"><span>{esc(eleicoes.secao_label())} · {esc(eleicoes.SECAO["local"])}</span>'
            f'<span>{esc(self.eleicao["rotulo"])}{esc(audio_tag)}</span></div>'
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
            led_pronta = 'tm-led-on' if (fase not in ('zeresima', 'registro_mesarios') and not votando) else ''
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
        if self.teclado and fase == 'ident' and not self.urna_encerrada:
            below_html = (
                '<div class="below-row">'
                '<button type="button" class="btn btn-secondary" data-action="exemplo">Preencher título de exemplo</button>'
                '</div>'
            )
        elif self.teclado and fase == 'bio':
            below_html = (
                '<div class="below-row">'
                '<button type="button" class="btn btn-ghost" data-action="falha-digital">Simular falha na digital</button>'
                '</div>'
            )

        self.root.innerHTML = shell_html + below_html


def mount(selector, opts=None):
    root = document.querySelector(selector)
    kwargs = dict(opts) if opts else {}
    return Mesario(root, **kwargs)
