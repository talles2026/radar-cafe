#!/usr/bin/env python3
"""Resume os números do dia em data/indicadores.json.

Serve de base para a recomendação escrita pelo Claude: assim ele parte dos mesmos
cálculos do app, sem refazer contas à mão."""
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from telegram import BRT, DATA, LB_PER_SACA, fit, load, project  # noqa: E402

REPASSE = 0.7  # parte do movimento da bolsa em reais que chega ao físico no mesmo dia


def serie(quotes, campo, conv):
    todos = sorted(quotes, key=lambda x: x["date"])
    usd, ult = {}, None
    for x in todos:
        if x.get("usd"):
            ult = x["usd"]
        usd[x["date"]] = ult
    out = []
    for x in todos:
        if x.get(campo) and usd.get(x["date"]):
            out.append({"date": x["date"], "par": conv(x[campo]) * usd[x["date"]], "bolsa": x[campo]})
    return out


def var(seq, campo, n):
    return seq[-1][campo] / seq[-1 - n][campo] - 1 if len(seq) > n else None


def produto(quotes, campo, conv, cep):
    S = serie(quotes, campo, conv)
    if len(S) < 8:
        return None
    cs = [x for x in sorted(quotes, key=lambda x: x["date"]) if x.get(cep)]
    if not cs:
        return None
    c = cs[-1]
    ref = next((x for x in reversed(S) if x["date"] <= c["date"]), S[0])
    fis = c[cep] * math.exp(REPASSE * math.log(S[-1]["par"] / ref["par"]))
    m = fit([x["par"] for x in S])
    prev = {}
    for n, h in (("7d", 5), ("15d", 11)):
        f = project(m, h)
        prev[n] = {"centro": round(fis * f["mid"]), "faixa70": [round(fis * f["lo"]), round(fis * f["hi"])],
                   "chanceAlta": round(f["up"], 2)}
    # físico x bolsa em reais: hoje e média dos dias com CEPEA
    pares = [(x[cep] / p["par"] - 1) for x in cs for p in S if p["date"] == x["date"]]
    return {
        "cepea": c[cep], "cepeaData": c["date"], "fisicoEstimadoHoje": round(fis),
        "bolsaUltimo": S[-1]["bolsa"], "bolsaData": S[-1]["date"],
        "bolsaVar1d": var(S, "bolsa", 1), "bolsaVar5d": var(S, "bolsa", 5), "bolsaVar20d": var(S, "bolsa", 20),
        "previsao": prev,
        "fisicoVsBolsa": {"hoje": round(pares[-1], 4) if pares else None,
                          "media": round(sum(pares) / len(pares), 4) if pares else None, "dias": len(pares)},
    }


def main():
    quotes = load("quotes.json", [])
    us = [x for x in sorted(quotes, key=lambda x: x["date"]) if x.get("usd")]
    out = {
        "geradoEm": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "arabica": produto(quotes, "kc", lambda v: v / 100 * LB_PER_SACA, "cepeaArabica"),
        "conilon": produto(quotes, "rc", lambda v: v * 0.06, "cepeaConilon"),
        "dolar": {"ultimo": us[-1]["usd"], "data": us[-1]["date"], "var1d": var(us, "usd", 1), "var5d": var(us, "usd", 5)} if us else None,
        "clima": [{k: r.get(k) for k in ("regiao", "chuva7d", "tmin", "tmax", "nota")}
                  for r in (load("weather.json", {}).get("regioes") or [])],
    }
    (DATA / "indicadores.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), "utf-8")


if __name__ == "__main__":
    main()
