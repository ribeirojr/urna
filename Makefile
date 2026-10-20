# A urna roda inteira no navegador, mas index.html busca os módulos Python
# com fetch('./urna.py') — abrir o arquivo direto (file://) esbarra no CORS.
# Por isso tudo aqui passa por um servidor HTTP local.

PORT ?= 8000
URL  := http://localhost:$(PORT)/

.DEFAULT_GOAL := run

## run: sobe o servidor e abre a urna no navegador
run:
	@echo "Urna em $(URL) — Ctrl+C para parar"
	@( sleep 1; $(call open_url,$(URL)) ) &
	@python3 -m http.server $(PORT)

## serve: igual ao run, sem abrir o navegador
serve:
	@echo "Urna em $(URL) — Ctrl+C para parar"
	@python3 -m http.server $(PORT)

## check: valida os módulos Python e o JS embutido no index.html
check:
	@python3 -m py_compile eleicoes.py urna.py mesario.py
	@python3 -c "import ast,re,sys; \
h=open('index.html').read(); \
m=re.search(r'<script>([\s\S]*?)</script>\s*</body>', h); \
sys.exit('index.html: script embutido não encontrado') if not m else None; \
ids=set(re.findall(r\"getElementById\('([^']+)'\)\", m.group(1))); \
miss=sorted(i for i in ids if ('id=\"%s\"' % i) not in h); \
sys.exit('ids ausentes no HTML: %s' % miss) if miss else None; \
print('ok — %d módulos, %d ids conferidos' % (3, len(ids)))"
	@$(MAKE) --no-print-directory candidatos

## candidatos: lista as eleições e os números válidos de cada uma
candidatos:
	@python3 -c "import eleicoes as e; \
[print('  %s  %s' % (e.ELEICOES[a]['rotulo'].ljust(16), \
'  '.join('%s %s (%s)' % (c['num'], c['nome'], c['partido']) for c in e.ELEICOES[a]['cands']))) \
for a in e.ORDEM]"

## clean: remove os caches do Python
clean:
	@rm -rf __pycache__ .pytest_cache
	@echo "limpo"

## help: esta lista
help:
	@grep -E '^## ' $(MAKEFILE_LIST) | sed 's/^## /  make /'

.PHONY: run serve check candidatos clean help

# Abre uma URL no navegador padrão (macOS: open, Linux: xdg-open).
open_url = (command -v open >/dev/null 2>&1 && open "$(1)") || \
           (command -v xdg-open >/dev/null 2>&1 && xdg-open "$(1)") || true
