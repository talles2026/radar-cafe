// Radar de Preços — servidor (função "precos" no projeto Supabase radar-clima).
// Busca o menor preço de qualquer produto, guarda o histórico, faz a previsão e manda alerta no celular.
// Roda sozinho a cada 30 minutos (pg_cron) e também quando o app é aberto.
import { createClient } from "npm:@supabase/supabase-js@2.45.4";
import webpush from "npm:web-push@3.6.7";
import { buscar, detectarTipo } from "./fontes.js";
import { previsao, porDia } from "./previsao.js";

const SITE = "https://talles2026.github.io/radar-cafe/precos/";
const CORS = { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "authorization, apikey, content-type, x-cron", "Access-Control-Allow-Methods": "GET, POST, OPTIONS" };
const db = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!, { auth: { persistSession: false } });
type J = Record<string, any>;
const resp = (d: unknown, status = 200) => new Response(JSON.stringify(d), { status, headers: { ...CORS, "Content-Type": "application/json" } });
const brl = (v: number) => v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
const donoOk = (d: unknown) => typeof d === "string" && /^[a-z0-9-]{16,64}$/.test(d);

let vapidPronto = false;
async function vapid() {
  if (vapidPronto) return;
  const { data } = await db.from("estado").select("chave,valor").in("chave", ["vapid_public", "vapid_private"]);
  const E = Object.fromEntries((data ?? []).map((x: J) => [x.chave, x.valor]));
  webpush.setVapidDetails("mailto:radar-precos@users.noreply.github.com", E.vapid_public, E.vapid_private);
  vapidPronto = true;
}
async function avisar(dono: string, payload: J) {
  const { data: s } = await db.from("precos_inscricoes").select("*").eq("dono", dono).maybeSingle();
  if (!s) return false;
  await vapid();
  try {
    await webpush.sendNotification({ endpoint: s.endpoint, keys: { p256dh: s.p256dh, auth: s.auth } }, JSON.stringify(payload), { TTL: 3600, urgency: "high" });
    return true;
  } catch (e: any) {
    if (e?.statusCode === 404 || e?.statusCode === 410) await db.from("precos_inscricoes").delete().eq("dono", dono);
    return false;
  }
}

// ---------------------------------------------------------------- produto
async function historico(id: string) {
  const { data } = await db.from("precos_hist").select("quando,menor,loja").eq("produto", id).gte("quando", new Date(Date.now() - 180 * 864e5).toISOString()).order("quando");
  return data ?? [];
}
function resumoHist(h: J[]) {
  const vs = h.map((x) => +x.menor).filter((v) => v > 0);
  return { dias: porDia(h), min: vs.length ? Math.min(...vs) : null, max: vs.length ? Math.max(...vs) : null, pontos: vs.length };
}

async function alertar(p: J, res: J, h: J[]) {
  const m = res.melhor; if (!m) return;
  const antes = h.slice(0, -1).map((x) => +x.menor).filter((v) => v > 0);
  const minAntes = antes.length ? Math.min(...antes) : null;
  const recente = p.alerta_em && Date.now() - Date.parse(p.alerta_em) < 20 * 3600e3;
  let titulo = "", corpo = "";
  if (p.alvo && m.preco <= +p.alvo) {
    if (recente && p.alerta_preco && m.preco >= +p.alerta_preco * 0.99) return;
    titulo = `🔔 ${p.termo}: ${brl(m.preco)}`;
    corpo = `Chegou no seu alvo (${brl(+p.alvo)}) na ${m.lojaNome}. Toque para abrir a oferta.`;
  } else if (!p.alvo && minAntes && antes.length >= 6 && m.preco < minAntes * 0.97) {
    if (recente && p.alerta_preco && m.preco >= +p.alerta_preco * 0.99) return;
    titulo = `📉 Menor preço já visto: ${p.termo}`;
    corpo = `${brl(m.preco)} na ${m.lojaNome} (antes o menor era ${brl(minAntes)}).`;
  } else return;
  const ok = await avisar(p.dono, { title: titulo, body: corpo, tag: `preco-${p.id}`, url: `${SITE}?p=${p.id}` });
  if (ok) await db.from("precos_produtos").update({ alerta_preco: m.preco, alerta_em: new Date().toISOString() }).eq("id", p.id);
}

async function atualizar(p: J) {
  const res: J = await buscar(p.termo, p.tipo ?? undefined);
  if (res.melhor) res.melhor.lojaNome = res.lojas.find((l: J) => l.id === res.melhor.loja)?.nome ?? "";
  const agora = new Date().toISOString();
  await db.from("precos_produtos").update({ ultimo: res, atualizado: agora, tipo: res.tipo }).eq("id", p.id);
  if (res.melhor) {
    const porLoja = Object.fromEntries(res.lojas.filter((l: J) => l.melhor).map((l: J) => [l.id, l.melhor.preco]));
    await db.from("precos_hist").insert({ produto: p.id, quando: agora, menor: res.melhor.preco, loja: res.melhor.loja, por_loja: porLoja });
  }
  const h = await historico(p.id);
  try { await alertar({ ...p, ultimo: res }, res, h); } catch (_) { /* alerta não derruba a busca */ }
  return { ...p, ultimo: res, atualizado: agora, h };
}

async function emLotes<T>(lista: T[], n: number, f: (x: T) => Promise<unknown>, prazo: number) {
  const fila = [...lista];
  await Promise.all(Array.from({ length: n }, async () => {
    while (fila.length && Date.now() < prazo) { const x = fila.shift()!; try { await f(x); } catch (_) { /* segue */ } }
  }));
}

async function meus(dono: string, forcar: boolean) {
  const { data } = await db.from("precos_produtos").select("*").eq("dono", dono).order("criado");
  const lista: J[] = data ?? [];
  const prazo = Date.now() + 90e3;
  const velhos = lista.filter((p) => forcar ? !p.atualizado || Date.now() - Date.parse(p.atualizado) > 3 * 60e3 : !p.atualizado);
  const novos: Record<string, J> = {};
  await emLotes(velhos, 3, async (p) => { novos[p.id] = await atualizar(p); }, prazo);
  const out = [];
  for (const p of lista) {
    const atual = novos[p.id] ?? p;
    const h = novos[p.id]?.h ?? await historico(p.id);
    out.push({ id: p.id, termo: p.termo, tipo: atual.tipo, alvo: p.alvo, criado: p.criado, atualizado: atual.atualizado, ultimo: atual.ultimo, hist: resumoHist(h), previsao: previsao(h, atual.tipo) });
  }
  return { produtos: out, agora: new Date().toISOString() };
}

async function rodar() {
  const limite = new Date(Date.now() - 25 * 60e3).toISOString();
  const { data } = await db.from("precos_produtos").select("*").or(`atualizado.is.null,atualizado.lt.${limite}`).order("atualizado", { ascending: true, nullsFirst: true }).limit(60);
  let n = 0;
  await emLotes(data ?? [], 4, async (p: J) => { await atualizar(p); n++; }, Date.now() + 120e3);
  await db.from("precos_hist").delete().lt("quando", new Date(Date.now() - 365 * 864e5).toISOString());
  return { atualizados: n, pendentes: (data?.length ?? 0) - n };
}

// ---------------------------------------------------------------- rotas
Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  const u = new URL(req.url);
  try {
    if (req.method === "GET") {
      if (u.searchParams.get("acao") === "chave") {
        const { data } = await db.from("estado").select("valor").eq("chave", "vapid_public").maybeSingle();
        return resp({ chave: data?.valor ?? null });
      }
      if (u.searchParams.get("acao") === "tipo") return resp(detectarTipo(String(u.searchParams.get("q") ?? "")));
      return resp({ ok: true });
    }
    const c: J = await req.json().catch(() => ({}));
    if (c.acao === "rodar") {
      const t = req.headers.get("x-cron");
      const { data } = await db.from("estado").select("valor").eq("chave", "cron_token").maybeSingle();
      if (!t || t !== data?.valor) return resp({ erro: "não autorizado" }, 401);
      return resp(await rodar());
    }
    if (c.acao === "buscar") {
      const q = String(c.q ?? "").trim().slice(0, 120);
      if (q.length < 2) return resp({ erro: "Digite o nome do produto." }, 400);
      const r: J = await buscar(q, undefined, !!c.debug);
      if (r.melhor) r.melhor.lojaNome = r.lojas.find((l: J) => l.id === r.melhor.loja)?.nome ?? "";
      return resp(r);
    }
    if (!donoOk(c.dono)) return resp({ erro: "código do aparelho inválido" }, 400);
    const dono = c.dono as string;
    if (c.acao === "meus") return resp(await meus(dono, !!c.atualizar));
    if (c.acao === "adicionar") {
      const q = String(c.q ?? "").trim().slice(0, 120);
      if (q.length < 2) return resp({ erro: "Digite o nome do produto." }, 400);
      const { count } = await db.from("precos_produtos").select("id", { count: "exact", head: true }).eq("dono", dono);
      if ((count ?? 0) >= 40) return resp({ erro: "Limite de 40 produtos. Remova algum para adicionar." }, 400);
      const alvo = +c.alvo > 0 ? +c.alvo : null;
      const ultimo = c.resultado?.q === q ? c.resultado : null;
      const { data: p, error } = await db.from("precos_produtos").insert({ dono, termo: q, alvo, tipo: ultimo?.tipo ?? detectarTipo(q), ultimo, atualizado: ultimo ? ultimo.quando : null }).select().single();
      if (error) throw error;
      if (ultimo?.melhor) {
        const porLoja = Object.fromEntries((ultimo.lojas ?? []).filter((l: J) => l.melhor).map((l: J) => [l.id, l.melhor.preco]));
        await db.from("precos_hist").insert({ produto: p.id, quando: ultimo.quando, menor: ultimo.melhor.preco, loja: ultimo.melhor.loja, por_loja: porLoja });
      } else await atualizar(p);
      return resp({ ok: true, id: p.id });
    }
    if (c.acao === "alvo") {
      const alvo = +c.alvo > 0 ? +c.alvo : null;
      await db.from("precos_produtos").update({ alvo, alerta_preco: null, alerta_em: null }).eq("id", c.id).eq("dono", dono);
      return resp({ ok: true });
    }
    if (c.acao === "remover") {
      await db.from("precos_produtos").delete().eq("id", c.id).eq("dono", dono);
      return resp({ ok: true });
    }
    if (c.acao === "inscrever") {
      const s = c.sub ?? {};
      if (!s.endpoint || !s.keys?.p256dh || !s.keys?.auth) return resp({ erro: "inscrição inválida" }, 400);
      await db.from("precos_inscricoes").upsert({ dono, endpoint: s.endpoint, p256dh: s.keys.p256dh, auth: s.keys.auth });
      return resp({ ok: true });
    }
    if (c.acao === "desinscrever") { await db.from("precos_inscricoes").delete().eq("dono", dono); return resp({ ok: true }); }
    if (c.acao === "teste") return resp({ ok: await avisar(dono, { title: "Radar de Preços", body: "Teste: os alertas estão funcionando neste celular. 🔔", tag: "teste", url: SITE }) });
    return resp({ erro: "ação desconhecida" }, 400);
  } catch (e: any) {
    return resp({ erro: String(e?.message ?? e).slice(0, 200) }, 502);
  }
});
