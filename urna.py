"""
Urna Eletronica 2026 — voting-machine screen simulator (Presidente only),
driven entirely from Python running in Pyodide. Mirrors the design mockup's
state machine: digit entry -> candidate lookup / null vote / blank vote -> confirm -> fim.
"""
from js import document, window
from pyodide.ffi import create_proxy

CANDS = {
    '37': {'num': '37', 'nome': 'Helena Duarte Ramos', 'partido': 'PRV', 'vice': 'Otávio Lins Barreto'},
    '48': {'num': '48', 'nome': 'Marcos Tavares Albuquerque', 'partido': 'MNB', 'vice': 'Cecília Prado'},
    '61': {'num': '61', 'nome': 'Joana Sato Ferreira', 'partido': 'PDA', 'vice': 'Ricardo Menezes'},
    '84': {'num': '84', 'nome': 'Paulo Henrique Costa', 'partido': 'UCT', 'vice': 'Lúcia Andrade'},
}

STEPS = ['Dep. Federal', 'Dep. Estadual', 'Senador 1ª', 'Senador 2ª', 'Governador', 'Presidente']

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


def esc(s):
    return (str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))


class Urna:
    def __init__(self, root, theme='tse', teclado=True, teclas=True,
                 progresso='completa', libras=True, som=True):
        self.root = root
        self.theme = theme
        self.teclado = teclado
        self.teclas = teclas
        self.progresso = progresso
        self.libras = libras
        self.som = som

        self.num = ''
        self.branco = False
        self.fim = False

        self._ac = None
        self._kd_proxy = None
        self._click_proxy = None

        if self.teclas:
            self._kd_proxy = create_proxy(self._on_keydown)
            window.addEventListener('keydown', self._kd_proxy)

        self._click_proxy = create_proxy(self._on_click)
        self.root.addEventListener('click', self._click_proxy)

        self.render()

    def destroy(self):
        if self._kd_proxy:
            window.removeEventListener('keydown', self._kd_proxy)
            self._kd_proxy.destroy()
        if self._click_proxy:
            self.root.removeEventListener('click', self._click_proxy)
            self._click_proxy.destroy()

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
        if self.fim:
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
        self.render()

    def reset(self):
        self.num = ''
        self.branco = False
        self.fim = False
        self.render()

    # ---- render ----
    def render(self):
        theme = THEMES.get(self.theme, THEMES['tse'])
        num, branco, fim = self.num, self.branco, self.fim

        cand = CANDS.get(num) if len(num) == 2 else None
        is_cand = bool(cand) and not fim
        is_nulo = len(num) == 2 and not cand and not fim
        is_branco = branco and not fim

        labels = ['Presidente'] if self.progresso == 'presidente' else STEPS
        steps_html = []
        n = len(labels)
        for i, label in enumerate(labels):
            last = i == n - 1
            done = fim or not last
            current = (not fim) and last
            if done:
                bar = theme['--s-ink']
                txt = f'✓ {esc(label)}'
                extra = f"color:{theme['--s-muted']}"
            elif current:
                bar = theme['--s-accent']
                txt = f'● {esc(label)}'
                extra = f"color:{theme['--s-ink']};font-weight:700"
            else:
                bar = theme['--s-line']
                txt = esc(label)
                extra = f"color:{theme['--s-muted']}"
            steps_html.append(
                f'<div class="progress-col">'
                f'<div class="progress-bar" style="background:{bar}"></div>'
                f'<div class="progress-label" style="{extra}">{txt}</div>'
                f'</div>'
            )

        d1 = num[0] if len(num) > 0 else ''
        d2 = num[1] if len(num) > 1 else ''
        cur1 = (len(num) == 0 and not branco)
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

        if fim:
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
                right_html = (
                    '<div class="photos-col">'
                    '<div class="photo-item">'
                    f'<div class="photo-box photo-pres"><span>foto</span><span>{esc(cand["num"])}</span></div>'
                    '<span class="photo-caption">Presidente</span>'
                    '</div>'
                    '<div class="photo-item">'
                    '<div class="photo-box photo-vice">foto</div>'
                    '<span class="photo-caption">Vice-Presidente</span>'
                    '</div>'
                    '</div>'
                )

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
        if self.libras and not fim:
            libras_html = (
                '<div class="libras-box">'
                '<span class="libras-kicker">Intérprete Libras</span>'
                f'<span class="libras-label">{esc(libras_label)}</span>'
                '</div>'
            )

        screen_html = (
            f'<div class="screen" style="{screen_style_vars}" data-screen-label="Tela da urna">'
            f'<div class="progress-row">{"".join(steps_html)}</div>'
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

        shell_class = 'shell' if self.teclado else 'shell no-keyboard'
        shell_html = f'<div class="{shell_class}">{screen_html}{keyboard_html}</div>'

        below_html = ''
        if self.teclado:
            hint = ('Teclado físico: 0–9 · B = branco · ⌫ = corrige · Enter = confirma'
                    if self.teclas else 'Clique nas teclas para votar')
            below_html = (
                '<div class="below-row">'
                '<button type="button" class="btn" data-action="reset">Liberar nova votação</button>'
                f'<span>{esc(hint)}</span>'
                '</div>'
            )

        self.root.innerHTML = shell_html + below_html


def mount(selector, opts=None):
    """opts: a Python dict (pass pyodide.toPy({...}) from JS) with
    theme/teclado/teclas/progresso/libras/som."""
    root = document.querySelector(selector)
    kwargs = dict(opts) if opts else {}
    return Urna(root, **kwargs)
