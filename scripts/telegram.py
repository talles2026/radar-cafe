#!/usr/bin/env python3
"""Envia o resumo diário e os alertas do Radar do Café para um canal do Telegram.

Precisa de dois segredos no GitHub (Settings → Secrets and variables → Actions):
  TELEGRAM_TOKEN  token do bot criado no @BotFather
  TELEGRAM_CHAT   @nome_do_canal (o bot precisa ser administrador do canal)

Os limites dos alertas ficam em data/alertas.json. O que já foi enviado fica em
data/telegram_estado.json, para não repetir mensagem.
"""
import html
import json
import math
import os
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
BRT = timezone(timedelta(hours=-3))
LB_PER_SACA = 132.277
APP_URL = "https://talles2026.github.io/radar-cafe/"


def load(name, default):
    try:
        return json.loads((DATA / name).read_text("utf-8"))
    except Exception:
        return default


def br(v, d=2):
    s = f"{v:,.{d}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def pct(v):
    return ("+" if v > 0 else "") + br(v * 100, 2) + "%"


def dbr(iso):
    return f"{iso[8:10]}/{iso[5:7]}"


# ---------- modelo (o mesmo do app) ----------

def series(quotes):
    q = sorted((x for x in quotes if x.get("kc")), key=lambda x: x["date"])
    first = next((x["usd"] for x in q if x.get("usd")), None)
    last, out = None, []
    for x in q:
        if x.get("usd"):
            last = x["usd"]
        u = last or first
        if u:
            out.append({**x, "parity": x["kc"] / 100 * LB_PER_SACA * u})
    return out


def fit(p):
    r = [math.log(p[i] / p[i - 1]) for i in range(1, len(p))]
    if len(r) < 5:
        return None
    k = min(10, len(r))
    v = sum(x * x for x in r[:k]) / k
    for x in r:
        v = 0.94 * v + 0.06 * x * x
    sig = math.sqrt(v)
    mom = sum(r[-10:]) / min(10, len(r))
    mu = max(-0.25 * sig, min(0.25 * sig, 0.25 * mom))
    return mu, sig


def project(m, h):
    mu, sig = m
    mm, s = mu * h, sig * math.sqrt(h) * 1.1
    phi = 0.5 * (1 + math.erf(mm / s / math.sqrt(2)))
    return {"lo": math.exp(mm - 1.036 * s), "hi": math.exp(mm + 1.036 * s), "mid": math.exp(mm), "up": phi}


# ---------- mensagens ----------

def resumo(quotes, weather, meta, momento):
    S = series(quotes)
    q = sorted(quotes, key=lambda x: x["date"])
    cep = [x for x in q if x.get("cepeaArabica")]
    con = [x for x in q if x.get("cepeaConilon")]
    us = [x for x in q if x.get("usd")]
    L, P = S[-1], S[-2]
    hoje = datetime.now(BRT).date().isoformat()
    linhas = [f"☕ <b>Radar do Café · {momento}</b>"]
    if meta.get("headline"):
        linhas.append(f"<i>{html.escape(meta['headline'])}</i>")
    linhas.append("")
    if cep:
        c = cep[-1]
        var = f" ({pct(c['cepeaVar'] / 100)})" if c.get("cepeaVar") is not None else ""
        linhas.append(f"Arábica CEPEA ({dbr(c['date'])}): R$ {br(c['cepeaArabica'])}{var}")
    if con:
        linhas.append(f"Conilon CEPEA ({dbr(con[-1]['date'])}): R$ {br(con[-1]['cepeaConilon'])}")
    quando = "agora" if (L["date"] == hoje and L.get("kcHora")) else dbr(L["date"])
    linhas.append(f"NY {quando}: {br(L['kc'])} ¢/lb ({pct(L['kc'] / P['kc'] - 1)})")
    if us:
        u = us[-1]
        linhas.append(f"Dólar {'agora' if u.get('usdAoVivo') else 'PTAX ' + dbr(u['date'])}: R$ {br(u['usd'], 3)}")
    m = fit([x["parity"] for x in S])
    base = cep[-1]["cepeaArabica"] if cep else L["parity"]
    if m:
        linhas += ["", "<b>Previsão do arábica físico</b>"]
        for n in (7, 15):
            alvo = datetime.now(BRT).date() + timedelta(days=n)
            d0 = date.fromisoformat(L["date"])
            h = max(1, sum(1 for i in range(1, (alvo - d0).days + 1) if (d0 + timedelta(days=i)).weekday() < 5))
            f = project(m, h)
            linhas.append(f"• {n} dias: R$ {br(base * f['lo'], 0)} a R$ {br(base * f['hi'], 0)} ({round(f['up'] * 100)}% de chance de alta)")
    regs = (weather or {}).get("regioes") or []
    if regs:
        linhas += ["", "Chuva em 7 dias: " + " · ".join(f"{r['regiao'].split(' (')[0]} {br(r['chuva7d'], 0)} mm" for r in regs)]
    linhas += ["", f'<a href="{APP_URL}">Abrir o Radar do Café</a>']
    return "\n".join(linhas)


def alertas(quotes, weather, cfg, estado):
    """Lista de (chave, texto). A chave evita repetir o mesmo alerta no mesmo dia."""
    out = []
    hoje = datetime.now(BRT).date().isoformat()
    S = series(quotes)
    q = sorted(quotes, key=lambda x: x["date"])
    cep = [x for x in q if x.get("cepeaArabica")]
    if cep:
        c = cep[-1]["cepeaArabica"]
        if cfg.get("precoAcima") and c >= cfg["precoAcima"]:
            out.append((f"acima-{cfg['precoAcima']}-{cep[-1]['date']}", f"🔔 Arábica CEPEA chegou a R$ {br(c)}, acima do seu alvo de R$ {br(cfg['precoAcima'], 0)}."))
        if cfg.get("precoAbaixo") and c <= cfg["precoAbaixo"]:
            out.append((f"abaixo-{cfg['precoAbaixo']}-{cep[-1]['date']}", f"🔔 Arábica CEPEA caiu para R$ {br(c)}, abaixo do seu limite de R$ {br(cfg['precoAbaixo'], 0)}."))
    if len(S) >= 2 and S[-1]["date"] == hoje and cfg.get("nyVariacao"):
        v = S[-1]["kc"] / S[-2]["kc"] - 1
        if abs(v) * 100 >= cfg["nyVariacao"]:
            out.append((f"ny-{'alta' if v > 0 else 'baixa'}-{hoje}", f"📊 NY {'sobe' if v > 0 else 'cai'} {br(abs(v) * 100)}% hoje: {br(S[-1]['kc'])} ¢/lb."))
    us = [x for x in q if x.get("usd")]
    if len(us) >= 2 and us[-1]["date"] == hoje and cfg.get("dolarVariacao"):
        v = us[-1]["usd"] / us[-2]["usd"] - 1
        if abs(v) * 100 >= cfg["dolarVariacao"]:
            out.append((f"usd-{'alta' if v > 0 else 'baixa'}-{hoje}", f"💵 Dólar {'sobe' if v > 0 else 'cai'} {br(abs(v) * 100)}% hoje: R$ {br(us[-1]['usd'], 3)}."))
    for r in (weather or {}).get("regioes") or []:
        if cfg.get("tminGeada") is not None and r.get("tmin") is not None and r["tmin"] <= cfg["tminGeada"]:
            out.append((f"geada-{r['regiao']}-{hoje}", f"🥶 Risco de geada: mínima de {br(r['tmin'], 0)} °C prevista para {r['regiao']} nos próximos 7 dias."))
    return [(k, t) for k, t in out if k not in estado.get("enviados", [])]


def send(token, chat, text):
    body = urllib.parse.urlencode({"chat_id": chat, "text": text, "parse_mode": "HTML",
                                   "disable_web_page_preview": "true"}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=body)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())["ok"]


def main():
    token, chat = os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT")
    if not token or not chat:
        print("Telegram não configurado; nada a enviar.", file=sys.stderr)
        return
    quotes = load("quotes.json", [])
    if len(series(quotes)) < 6:
        return
    weather, meta = load("weather.json", {}), load("meta.json", {})
    cfg = load("alertas.json", {})
    estado = load("telegram_estado.json", {"enviados": []})
    agora = datetime.now(BRT)
    hoje = agora.date().isoformat()
    msgs = []
    if agora.weekday() < 5:
        if 9 <= agora.hour < 18 and estado.get("manha") != hoje:
            msgs.append(("manha", resumo(quotes, weather, meta, "abertura")))
        if agora.hour >= 18 and estado.get("tarde") != hoje:
            msgs.append(("tarde", resumo(quotes, weather, meta, "fechamento")))
    msgs += alertas(quotes, weather, cfg, estado)
    for chave, texto in msgs:
        try:
            if send(token, chat, texto):
                if chave in ("manha", "tarde"):
                    estado[chave] = hoje
                else:
                    estado.setdefault("enviados", []).append(chave)
                print("enviado:", chave, file=sys.stderr)
        except Exception as e:
            print("falha ao enviar", chave, e, file=sys.stderr)
    estado["enviados"] = estado.get("enviados", [])[-200:]
    (DATA / "telegram_estado.json").write_text(json.dumps(estado, ensure_ascii=False, indent=1), "utf-8")


if __name__ == "__main__":
    main()
