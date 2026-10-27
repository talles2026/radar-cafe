# Radar do Café

Cotação do café arábica e conilon com previsão em faixas para 3, 7 e 15 dias úteis. App web instalável no celular, sem custo.

- **App:** https://talles2026.github.io/radar-cafe/
- **Dados:** `data/quotes.json` (NY, dólar PTAX, CEPEA), `data/weather.json` (clima), `data/meta.json` (análise do dia e praças).
- **Coleta:** `.github/workflows/coleta.yml` roda `scripts/collect.py` em dias úteis e republica o site. Para rodar na hora: aba Actions → "Coleta e publicação" → Run workflow.
- **Análise do dia:** escrita por uma tarefa agendada do Claude, que atualiza `data/meta.json`.

A previsão é estatística (tendência recente e volatilidade de NY em reais) e não substitui o acompanhamento do mercado.
