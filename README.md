# Radar do Café

Cotação do café arábica e conilon com previsão em faixas para 3, 7 e 15 dias úteis. App web instalável no celular, sem custo.

- **App:** https://talles2026.github.io/radar-cafe/
- **Dados:** `data/quotes.json` (NY, dólar PTAX, CEPEA), `data/weather.json` (clima), `data/meta.json` (análise do dia e praças).
- **Coleta:** `.github/workflows/coleta.yml` roda `scripts/collect.py` em dias úteis e republica o site. Para rodar na hora: aba Actions → "Coleta e publicação" → Run workflow.
- **Análise do dia:** escrita por uma tarefa agendada do Claude, que atualiza `data/meta.json`.

A previsão é estatística (tendência recente e volatilidade de NY em reais) e não substitui o acompanhamento do mercado.

## Radar de Preços (`precos/`)

App separado, instalável no celular: https://talles2026.github.io/radar-cafe/precos/

- Digite qualquer produto; o tipo é identificado sozinho. Veículos: OLX, Mercado Livre, Facebook Marketplace e Google. Demais: Mercado Livre, Shopee, Amazon, AliExpress e Google.
- Preços lidos direto na Amazon, AliExpress e OLX, e pelos comparadores Bing Shopping e Buscapé (onde aparece o Mercado Livre). Shopee, Google, Facebook e o Mercado Livre direto bloqueiam leitura automática: o app mostra o atalho da busca já ordenada pelo menor preço.
- Acompanhar produto, remover, alerta de preço no celular, histórico e previsão. Atualiza ao abrir e a cada 30 minutos.
- Servidor: função `precos` no Supabase (projeto radar-clima), código em `supabase/functions/precos/`; tabelas `precos_produtos`, `precos_hist`, `precos_inscricoes`; agendamento `precos-atualizar` (pg_cron, minutos 7 e 37).
