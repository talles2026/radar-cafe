#!/usr/bin/env python3
"""Envia notificações no celular (Web Push) para quem ativou no app.

As inscrições ficam numa tabela do Supabase (radar_inscricoes). Precisa de três segredos no GitHub:
  VAPID_PRIVATE         chave privada das notificações (par da chave pública que está no app)
  SUPABASE_URL          endereço do projeto Supabase
  SUPABASE_SERVICE_KEY  chave service_role do projeto (só o robô usa; nunca vai para o app)

O que já foi avisado fica em data/push_estado.json, para não repetir.
"""
import hashlib
import json
import os
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from telegram import BRT, DATA, br, dbr, load, pct  # noqa: E402

APP_URL = "https://talles2026.github.io/radar-cafe/"
NOMES = {"arabica": "Arábica", "conilon": "Conilon"}
CEP = {"arabica": "cepeaArabica", "conilon": "cepeaConilon"}
VAR = {"arabica": "cepeaVar", "conilon": "conilonVar"}
BOLSA = {"arabica": ("kc", "NY", "¢/lb", 2), "conilon": ("rc", "Londres", "US$/t", 0)}
SINAL = {"vender": "Vender parte", "segurar": "Segurar", "aguardar": "Aguardar"}


def supabase(path, method="GET", body=None):
    url = os.environ["SUPABASE_URL"].rstrip("/") + "/rest/v1/" + path
    key = os.environ["SUPABASE_SERVICE_KEY"]
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"apikey": key, "Authorization": f"Bearer {key}",
                                          "Content-Type": "application/json", "Prefer": "return=minimal"})
    with urllib.request.urlopen(req, timeout=30) as r:
        txt = r.read().decode()
        return json.loads(txt) if txt else None


def eventos(quotes, recs, estado):
    """Eventos do momento: [(chave, produto, tipo, título, texto)]. A chave evita repetição."""
    out = []
    q = sorted(quotes, key=lambda x: x["date"])
    hoje = datetime.now(BRT).date().isoformat()
    for prod in ("arabica", "conilon"):
        cs = [x for x in q if x.get(CEP[prod])]
        if cs:
            c = cs[-1]
            var = f" ({pct(c[VAR[prod]] / 100)})" if c.get(VAR[prod]) is not None else ""
            out.append((f"cepea-{prod}-{c['date']}", prod, "cepea", f"{NOMES[prod]} CEPEA {dbr(c['date'])}",
                        f"R$ {br(c[CEP[prod]])} por saca{var}"))
        campo, nome, un, dec = BOLSA[prod]
        bs = [x for x in q if x.get(campo)]
        if len(bs) >= 2 and bs[-1]["date"] == hoje:
            a, b = bs[-2], bs[-1]
            ref = a.get(campo + "2") if b.get(campo + "Virada") else a[campo]
            v = b[campo] / ref - 1 if ref else 0
            if abs(v) >= 0.02:
                sent = "alta" if v > 0 else "baixa"
                out.append((f"forte-{prod}-{sent}-{hoje}", prod, "forte", f"{nome} em forte {sent}",
                            f"{'Sobe' if v > 0 else 'Cai'} {br(abs(v) * 100)}% hoje: {br(b[campo], dec)} {un}"))
    ult = {}
    for r in (recs or {}).get("itens", []):
        if r["produto"] not in ult or (r["data"] + r["hora"]) > (ult[r["produto"]]["data"] + ult[r["produto"]]["hora"]):
            ult[r["produto"]] = r
    for prod, r in ult.items():
        ant = estado.get("sinal", {}).get(prod)
        if ant and ant != r["sinal"]:
            out.append((f"sinal-{r['id']}", prod, "sinal", f"Sinal do Radar mudou: {NOMES[prod]}",
                        f"{SINAL.get(ant, ant)} → {SINAL.get(r['sinal'], r['sinal'])}. {r['resumo']}"))
        estado.setdefault("sinal", {})[prod] = r["sinal"]
    return out, {p: [x for x in q if x.get(CEP[p])] for p in CEP}


def main():
    if not all(os.environ.get(k) for k in ("VAPID_PRIVATE", "SUPABASE_URL", "SUPABASE_SERVICE_KEY")):
        print("Notificações não configuradas; nada a enviar.", file=sys.stderr)
        return
    from pywebpush import WebPushException, webpush

    quotes, recs = load("quotes.json", []), load("recomendacoes.json", {})
    estado = load("push_estado.json", {"enviados": []})
    primeira = not estado.get("iniciado")
    evs, cepeas = eventos(quotes, recs, estado)
    try:
        subs = supabase("radar_inscricoes?select=id,endpoint,p256dh,auth,prefs,falhas") or []
    except Exception as e:
        print("falha ao ler inscrições:", e, file=sys.stderr)
        return

    enviados = set(estado.get("enviados", []))
    novos = []
    for s in subs:
        p = s.get("prefs") or {}
        sid = hashlib.sha1(s["endpoint"].encode()).hexdigest()[:12]
        msgs = []
        for chave, prod, tipo, titulo, texto in evs:
            if p.get(prod) and p.get(tipo) and f"{chave}:{sid}" not in enviados:
                msgs.append((f"{chave}:{sid}", titulo, texto))
        # preço-alvo, conferido no CEPEA mais recente de cada produto
        for prod in ("arabica", "conilon"):
            alvo = (p.get("alvos") or {}).get(prod) or {}
            cs = cepeas[prod]
            if not p.get(prod) or not cs:
                continue
            c = cs[-1]
            v = c[CEP[prod]]
            if alvo.get("acima") and v >= alvo["acima"]:
                msgs.append((f"alvo-acima-{prod}-{alvo['acima']}-{c['date']}:{sid}", f"🔔 {NOMES[prod]} acima de R$ {br(alvo['acima'], 0)}",
                             f"CEPEA {dbr(c['date'])}: R$ {br(v)} por saca"))
            if alvo.get("abaixo") and v <= alvo["abaixo"]:
                msgs.append((f"alvo-abaixo-{prod}-{alvo['abaixo']}-{c['date']}:{sid}", f"🔔 {NOMES[prod]} abaixo de R$ {br(alvo['abaixo'], 0)}",
                             f"CEPEA {dbr(c['date'])}: R$ {br(v)} por saca"))
        msgs = [m for m in msgs if m[0] not in enviados]
        conhecidos = estado.setdefault("subs", [])
        if primeira or sid not in conhecidos:  # inscrição nova: não manda avisos que já tinham saído
            novos += [m[0] for m in msgs]
            if sid not in conhecidos:
                conhecidos.append(sid)
            continue
        for chave, titulo, texto in msgs[:4]:
            try:
                webpush({"endpoint": s["endpoint"], "keys": {"p256dh": s["p256dh"], "auth": s["auth"]}},
                        json.dumps({"title": titulo, "body": texto, "url": APP_URL, "tag": chave.split(":")[0]}),
                        vapid_private_key=os.environ["VAPID_PRIVATE"],
                        vapid_claims={"sub": "mailto:talleseugenio@gmail.com"}, ttl=6 * 3600)
                novos.append(chave)
            except WebPushException as e:
                code = getattr(e.response, "status_code", None)
                if code in (404, 410):  # celular cancelou a inscrição
                    supabase(f"radar_inscricoes?id=eq.{s['id']}", "DELETE")
                    break
                print("falha no envio:", code, e, file=sys.stderr)
            except Exception as e:
                print("falha no envio:", e, file=sys.stderr)
        novos += [m[0] for m in msgs[4:]]  # no máximo 4 avisos por rodada; o resto é dado como visto
    estado["iniciado"] = True
    estado["enviados"] = (list(enviados) + novos)[-3000:]
    (DATA / "push_estado.json").write_text(json.dumps(estado, ensure_ascii=False, indent=1), "utf-8")
    print(f"{len(subs)} inscrições, {len(novos)} avisos registrados", file=sys.stderr)


if __name__ == "__main__":
    main()
