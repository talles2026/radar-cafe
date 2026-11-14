# Radar do Café

Cotação do café arábica e conilon com previsão em faixas para 3, 7 e 15 dias úteis. App web instalável no celular, sem custo.

- **App:** https://talles2026.github.io/radar-cafe/
- **Dados:** `data/quotes.json` (NY, dólar PTAX, CEPEA), `data/weather.json` (clima), `data/meta.json` (manchete, resumo e praças), `data/pracas.json` (praças de Minas).
- **Coleta:** `.github/workflows/coleta.yml` roda `scripts/collect.py` em dias úteis e republica o site. Para rodar na hora: aba Actions → "Coleta e publicação" → Run workflow.
- **Fontes:** NY e dólar na CNBC, Londres no TradingView (reserva: Notícias Agrícolas), PTAX no Banco Central, CEPEA na planilha oficial, praças de Minas no Agrolink, clima no Open-Meteo/met.no.
- **Análise do dia:** `scripts/resumo.py` monta a manchete, o resumo e os motivos só com os números do dia, a cada coleta. Não usa IA, então não tem custo.

A previsão é estatística (tendência recente e volatilidade de NY em reais) e não substitui o acompanhamento do mercado.


## Radar de Preços

Mudou para o repositório próprio `radar-precos` (https://talles2026.github.io/radar-precos/). O endereço antigo `precos/` só redireciona.
