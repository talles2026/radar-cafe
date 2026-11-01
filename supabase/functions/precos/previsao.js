// Radar de Preços — histórico por dia e previsão simples (tendência dos últimos 30 dias).
const dia = (iso) => new Date(Date.parse(iso) - 3 * 3600e3).toISOString().slice(0, 10); // horário de Brasília

// menor preço de cada dia
export function porDia(h) {
  const m = new Map();
  for (const x of h) { const v = +x.menor; if (!(v > 0)) continue; const d = dia(x.quando); if (!m.has(d) || v < m.get(d).v) m.set(d, { d, v, loja: x.loja }); }
  return [...m.values()].sort((a, b) => a.d.localeCompare(b.d));
}

// Black Friday: última sexta-feira de novembro
function blackFriday(ano) { const d = new Date(Date.UTC(ano, 10, 30)); while (d.getUTCDay() !== 5) d.setUTCDate(d.getUTCDate() - 1); return d; }

export function previsao(h, tipo) {
  const dias = porDia(h).slice(-30);
  const hoje = new Date();
  const bf = blackFriday(hoje.getUTCFullYear()), faltam = Math.ceil((bf - hoje) / 864e5);
  const dica = tipo?.id !== "veiculo" && faltam >= 0 && faltam <= 30
    ? `Black Friday em ${bf.getUTCDate()}/11 (faltam ${faltam} dias): as lojas costumam baixar preços nessa semana. Se não tiver pressa, deixe o alerta ligado.`
    : null;
  if (dias.length < 3) return { status: "pouco", texto: `A previsão aparece com 3 dias de histórico (tem ${dias.length}).`, dica };
  // regressão no log do preço contra o tempo (dias)
  const t0 = Date.parse(dias[0].d);
  const xs = dias.map((p) => (Date.parse(p.d) - t0) / 864e5), ys = dias.map((p) => Math.log(p.v));
  const n = xs.length, mx = xs.reduce((s, v) => s + v, 0) / n, my = ys.reduce((s, v) => s + v, 0) / n;
  let sxy = 0, sxx = 0; for (let i = 0; i < n; i++) { sxy += (xs[i] - mx) * (ys[i] - my); sxx += (xs[i] - mx) ** 2; }
  // pouco histórico: puxa a tendência para zero (evita projetar uma queda de poucos dias para o mês inteiro)
  const b = (sxx ? sxy / sxx : 0) * (n / (n + 10)), a = my - b * mx;
  const res = ys.map((y, i) => y - (a + b * xs[i])), dp = Math.sqrt(res.reduce((s, r) => s + r * r, 0) / Math.max(1, n - 2));
  const xh = xs[n - 1], ult = dias[n - 1].v;
  const proj = (k) => { const v = ult * Math.exp(b * k); return Math.min(ult * 1.25, Math.max(ult * 0.75, v)); };
  const p7 = proj(7), p30 = proj(30), var30 = p30 / ult - 1;
  const conf = n >= 14 && dp < 0.05 ? "boa" : n >= 7 ? "média" : "baixa";
  const rumo = var30 <= -0.03 ? "queda" : var30 >= 0.03 ? "alta" : "estável";
  const pct = (v) => (v > 0 ? "+" : "") + (v * 100).toFixed(1).replace(".", ",") + "%";
  const conselho = rumo === "queda" ? "Preço em queda: vale esperar um pouco, com o alerta ligado."
    : rumo === "alta" ? "Preço subindo: se precisa, comprar logo tende a sair mais barato."
    : "Preço estável: compre quando chegar perto do menor já visto.";
  return {
    status: "ok", rumo, conf, p7, p30, faixa30: [p30 * Math.exp(-1.3 * dp * Math.sqrt(30 / Math.max(1, n))), p30 * Math.exp(1.3 * dp * Math.sqrt(30 / Math.max(1, n)))],
    texto: `${rumo === "estável" ? "Preço estável" : "Tendência de " + rumo} (${pct(var30)} em 30 dias), confiança ${conf}. ${conselho}`, dica, dias: n,
  };
}
