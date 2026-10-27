// Radar do Café: envia notificações no celular (Web Push) para quem ativou no app.
// É chamada pelo robô do GitHub depois de cada coleta. Lê os dados publicados no site,
// descobre o que há de novo e avisa cada celular conforme as escolhas dele.
import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "npm:@supabase/supabase-js@2.45.4";
import webpush from "npm:web-push@3.6.7";

const SITE = "https://talles2026.github.io/radar-cafe/";
const NOMES: Record<string, string> = { arabica: "Arábica", conilon: "Conilon" };
const CEP: Record<string, string> = { arabica: "cepeaArabica", conilon: "cepeaConilon" };
const VAR: Record<string, string> = { arabica: "cepeaVar", conilon: "conilonVar" };
const BOLSA: Record<string, [string, string, string, number]> = {
  arabica: ["kc", "NY", "¢/lb", 2],
  conilon: ["rc", "Londres", "US$/t", 0],
};
const SINAL: Record<string, string> = { vender: "Vender parte", segurar: "Segurar", aguardar: "Aguardar" };

type Q = Record<string, any>;
const br = (v: number, d = 2) => v.toLocaleString("pt-BR", { minimumFractionDigits: d, maximumFractionDigits: d });
const pct = (v: number) => (v > 0 ? "+" : "") + br(v * 100) + "%";
const dbr = (iso: string) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}`;
const hojeBR = () => new Date(Date.now() - 3 * 3600e3).toISOString().slice(0, 10);

async function json(path: string) {
  const r = await fetch(SITE + path + "?t=" + Date.now(), { headers: { "cache-control": "no-cache" } });
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}

const CORS = {
  "Access-Control-Allow-Origin": "https://talles2026.github.io",
  "Access-Control-Allow-Headers": "authorization, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Content-Type": "application/json",
};

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  const db = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
  const { data: est } = await db.from("radar_estado").select("chave,valor");
  const E = Object.fromEntries((est ?? []).map((x: any) => [x.chave, x.valor]));
  webpush.setVapidDetails("mailto:talleseugenio@gmail.com", E.vapid_public, E.vapid_private);

  // ---- aviso de teste pedido pelo próprio celular (só para inscrição já cadastrada) ----
  const corpo = await req.json().catch(() => ({}));
  if (corpo?.teste) {
    const { data: s } = await db.from("radar_inscricoes").select("endpoint,p256dh,auth").eq("endpoint", String(corpo.teste)).maybeSingle();
    if (!s) return new Response(JSON.stringify({ ok: false, erro: "inscrição não encontrada" }), { status: 404, headers: CORS });
    try {
      await webpush.sendNotification({ endpoint: s.endpoint, keys: { p256dh: s.p256dh, auth: s.auth } },
        JSON.stringify({ title: "Radar do Café", body: "Teste: as notificações estão funcionando neste celular. ☕", url: SITE, tag: "teste-" + Date.now() }), { TTL: 600, urgency: "high" });
      return new Response(JSON.stringify({ ok: true }), { headers: CORS });
    } catch (err: any) {
      return new Response(JSON.stringify({ ok: false, erro: String(err?.statusCode ?? err) }), { status: 500, headers: CORS });
    }
  }

  const quotes: Q[] = (await json("data/quotes.json")).sort((a: Q, b: Q) => (a.date < b.date ? -1 : 1));
  const recs = await json("data/recomendacoes.json").catch(() => ({ itens: [] }));
  const hoje = hojeBR();

  // ---- eventos do momento ----
  const ev: { chave: string; prod: string; tipo: string; titulo: string; texto: string }[] = [];
  const ultimoCep: Record<string, Q | undefined> = {};
  for (const prod of ["arabica", "conilon"]) {
    const cs = quotes.filter((x) => x[CEP[prod]]);
    const c = cs[cs.length - 1];
    ultimoCep[prod] = c;
    if (c) {
      const v = c[VAR[prod]];
      ev.push({ chave: `cepea-${prod}-${c.date}`, prod, tipo: "cepea", titulo: `${NOMES[prod]} CEPEA ${dbr(c.date)}`,
        texto: `R$ ${br(c[CEP[prod]])} por saca${v != null ? ` (${pct(v / 100)})` : ""}` });
    }
    const [campo, nome, un, dec] = BOLSA[prod];
    const bs = quotes.filter((x) => x[campo]);
    if (bs.length >= 2 && bs[bs.length - 1].date === hoje) {
      const a = bs[bs.length - 2], b = bs[bs.length - 1];
      const ref = b[campo + "Virada"] ? a[campo + "2"] : a[campo];
      const v = ref ? b[campo] / ref - 1 : 0;
      if (Math.abs(v) >= 0.02) {
        const s = v > 0 ? "alta" : "baixa";
        ev.push({ chave: `forte-${prod}-${s}-${hoje}`, prod, tipo: "forte", titulo: `${nome} em forte ${s}`,
          texto: `${v > 0 ? "Sobe" : "Cai"} ${br(Math.abs(v) * 100)}% hoje: ${br(b[campo], dec)} ${un}` });
      }
    }
  }
  const ult: Record<string, Q> = {};
  for (const r of recs.itens ?? []) {
    const u = ult[r.produto];
    if (!u || r.data + r.hora > u.data + u.hora) ult[r.produto] = r;
  }
  for (const [prod, r] of Object.entries(ult)) {
    const ant = E["sinal_" + prod];
    if (ant && ant !== r.sinal) {
      ev.push({ chave: `sinal-${r.id}`, prod, tipo: "sinal", titulo: `Sinal do Radar mudou: ${NOMES[prod]}`,
        texto: `${SINAL[ant] ?? ant} → ${SINAL[r.sinal] ?? r.sinal}. ${r.resumo}` });
    }
    await db.from("radar_estado").upsert({ chave: "sinal_" + prod, valor: r.sinal, atualizado: new Date().toISOString() });
  }

  // ---- abertura do mercado (uma vez por dia, entre 6h e 11h de Brasília, quando NY já negociou hoje) ----
  const horaBR = new Date(Date.now() - 3 * 3600e3).getUTCHours();
  const ind = await json("data/indicadores.json").catch(() => null);
  const A = ind?.arabica;
  if (A && A.bolsaData === hoje && horaBR >= 6 && horaBR < 11) {
    const partes = [`NY ${br(A.bolsaUltimo)} ¢/lb (${pct(A.bolsaVar1d ?? 0)})`];
    if (ind.dolar?.ultimo) partes.push(`dólar R$ ${br(ind.dolar.ultimo, 3)}`);
    if (A.fisicoEstimadoHoje) partes.push(`arábica físico estimado R$ ${br(A.fisicoEstimadoHoje, 0)}`);
    ev.push({ chave: `abertura-${hoje}`, prod: "*", tipo: "abertura", titulo: `Abertura do café · ${dbr(hoje)}`, texto: partes.join(" · ") });
  }

  // ---- manutenção: dado parado há 2 dias úteis ou mais (só para quem marcou a opção de manutenção) ----
  const saude = await json("data/saude.json").catch(() => null);
  for (const k of saude?.problemas ?? []) {
    const it = saude.itens?.[k] ?? {};
    const desde = it.ultimo ? ` desde ${dbr(String(it.ultimo).slice(0, 10))}` : "";
    ev.push({ chave: `manut-${k}-${hoje}`, prod: "*", tipo: "manutencao", titulo: "⚠️ Radar do Café: dado parado",
      texto: `${k} sem atualizar${desde}. O vigia automático vai tentar corrigir; o app mostra o último dado bom.` });
  }

  // ---- envio por celular ----
  const { data: subs } = await db.from("radar_inscricoes").select("id,endpoint,p256dh,auth,prefs,visto");
  let enviados = 0, removidos = 0;
  for (const s of subs ?? []) {
    const p = s.prefs ?? {};
    const sid = s.id.slice(0, 8);
    const msgs: { chave: string; titulo: string; texto: string }[] = [];
    for (const e of ev) if ((e.prod === "*" || p[e.prod]) && p[e.tipo]) msgs.push({ chave: `${e.chave}:${sid}`, titulo: e.titulo, texto: e.texto });
    for (const prod of ["arabica", "conilon"]) {
      const c = ultimoCep[prod], alvo = p.alvos?.[prod] ?? {};
      if (!p[prod] || !c) continue;
      const v = c[CEP[prod]];
      if (alvo.acima && v >= alvo.acima)
        msgs.push({ chave: `alvo-acima-${prod}-${alvo.acima}-${c.date}:${sid}`, titulo: `🔔 ${NOMES[prod]} acima de R$ ${br(alvo.acima, 0)}`, texto: `CEPEA ${dbr(c.date)}: R$ ${br(v)} por saca` });
      if (alvo.abaixo && v <= alvo.abaixo)
        msgs.push({ chave: `alvo-abaixo-${prod}-${alvo.abaixo}-${c.date}:${sid}`, titulo: `🔔 ${NOMES[prod]} abaixo de R$ ${br(alvo.abaixo, 0)}`, texto: `CEPEA ${dbr(c.date)}: R$ ${br(v)} por saca` });
    }
    if (!msgs.length) continue;
    const { data: ja } = await db.from("radar_avisos_enviados").select("chave").in("chave", msgs.map((m) => m.chave));
    const jaSet = new Set((ja ?? []).map((x: any) => x.chave));
    const novos = msgs.filter((m) => !jaSet.has(m.chave));
    if (!novos.length) continue;
    // celular recém-inscrito: não recebe avisos que já tinham saído antes de ele ativar
    if (!s.visto) {
      await db.from("radar_avisos_enviados").upsert(novos.map((m) => ({ chave: m.chave })));
      await db.from("radar_inscricoes").update({ visto: true }).eq("id", s.id);
      continue;
    }
    for (const m of novos.slice(0, 4)) {
      try {
        await webpush.sendNotification({ endpoint: s.endpoint, keys: { p256dh: s.p256dh, auth: s.auth } },
          JSON.stringify({ title: m.titulo, body: m.texto, url: SITE, tag: m.chave.split(":")[0] }), { TTL: 6 * 3600, urgency: "high" });
        enviados++;
      } catch (err: any) {
        if (err?.statusCode === 404 || err?.statusCode === 410) { // celular cancelou
          await db.from("radar_inscricoes").delete().eq("id", s.id); removidos++; break;
        }
        console.error("falha no envio", err?.statusCode, err?.body ?? String(err));
      }
    }
    await db.from("radar_avisos_enviados").upsert(novos.map((m) => ({ chave: m.chave })));
  }
  await db.rpc("radar_limpar_avisos");
  return new Response(JSON.stringify({ inscricoes: subs?.length ?? 0, eventos: ev.length, enviados, removidos }),
    { headers: { "Content-Type": "application/json" } });
});
