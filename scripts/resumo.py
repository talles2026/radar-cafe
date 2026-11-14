#!/usr/bin/env python3
"""Escreve data/meta.json (manchete, resumo, motivos e praças) só com os números do dia.

Roda no GitHub Actions depois de collect.py e indicadores.py. Não usa IA: é texto montado
a partir de data/indicadores.json, data/quotes.json e data/pracas.json, então não tem custo."""
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
LIMIAR = 0.003  # abaixo de 0,3% conta como estável


def load(nome, padrao):
    try:
        return json.loads((DATA / nome).read_text("utf-8"))
    except Exception:
        return padrao


def num(v, casas=2):
    s = f"{abs(v):,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ("-" if v < 0 else "") + s


def pct(v, casas=1):
    return ("+" if v > 0 else "") + num(v * 100, casas) + "%"


def dbr(iso):
    return f"{iso[8:10]}/{iso[5:7]}"


def mov(nome, v):
    """'NY subiu 1,2%' / 'NY caiu 0,8%' / 'NY ficou quase estável (-0,2%)'."""
    if v > LIMIAR:
        return f"{nome} subiu {num(v * 100, 1)}%"
    if v < -LIMIAR:
        return f"{nome} caiu {num(-v * 100, 1)}%"
    return f"{nome} ficou quase estável ({pct(v)})"


def dia_util_anterior(d):
    d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.isoformat()


def direcao(v):
    return "alta" if v > LIMIAR else "baixa" if v < -LIMIAR else "neutro"


def ultimo_cepea(quotes, campo):
    xs = [q for q in sorted(quotes, key=lambda q: q["date"]) if q.get(campo)]
    if not xs:
        return None, None, None
    v = xs[-1][campo] / xs[-2][campo] - 1 if len(xs) > 1 else None
    return xs[-1]["date"], xs[-1][campo], v


def main():
    ind = load("indicadores.json", {})
    quotes = load("quotes.json", [])
    hoje = datetime.now(timezone(timedelta(hours=-3))).date()
    recente = (hoje - timedelta(days=4)).isoformat()
    ar, co, us = ind.get("arabica") or {}, ind.get("conilon") or {}, ind.get("dolar") or {}

    kc1, kc5 = ar.get("bolsaVar1d"), ar.get("bolsaVar5d")
    u1 = us.get("var1d")
    frases, drivers = [], []

    # manchete: o que aconteceu com o café em reais (NY x dólar)
    if kc1 is not None and u1 is not None:
        par = (1 + kc1) * (1 + u1) - 1
        estado = "mais caro" if par > 0.005 else "mais barato" if par < -0.005 else "estável"
        headline = f"Café em reais {estado}: NY {pct(kc1)} e dólar {pct(u1)}"
    else:
        headline = "Números do café atualizados"

    if ar.get("bolsaUltimo"):
        f = f"Em Nova York, o arábica está em {num(ar['bolsaUltimo'])} ¢/lb"
        if kc1 is not None:
            f += f", {pct(kc1)} no dia" + (f" e {pct(kc5)} em 5 pregões" if kc5 is not None else "")
        frases.append(f + ".")
        if kc1 is not None:
            drivers.append({"dir": direcao(kc1), "t": mov("NY", kc1) + " no dia"
                            + (f" ({pct(kc5)} na semana)." if kc5 is not None else ".")})
    if us.get("ultimo"):
        frases.append(f"O dólar comercial está em R$ {num(us['ultimo'], 3)}" + (f" ({pct(u1)} no dia)." if u1 is not None else "."))
        if u1 is not None:
            efeito = "café em reais tende a subir" if u1 > LIMIAR else "café em reais tende a cair" if u1 < -LIMIAR else "sem efeito no preço em reais"
            drivers.append({"dir": direcao(u1), "t": mov("Dólar", u1) + f": {efeito}."})

    da, va, vva = ultimo_cepea(quotes, "cepeaArabica")
    dc, vc, vvc = ultimo_cepea(quotes, "cepeaConilon")
    if va:
        f = f"O CEPEA arábica de {dbr(da)} ficou em R$ {num(va)} por saca" + (f" ({pct(vva)})" if vva is not None else "")
        if vc:
            f += f", e o conilon em R$ {num(vc)}" + (f" ({pct(vvc)})" if vvc is not None else "")
        frases.append(f + ".")

    if co.get("bolsaUltimo") and (co.get("bolsaData") or "") >= dia_util_anterior(hoje):
        r1 = co.get("bolsaVar1d")
        frases.append(f"Em Londres, o robusta está em US$ {num(co['bolsaUltimo'], 0)} por tonelada"
                      + (f" ({pct(r1)} no dia)." if r1 is not None else "."))
        if r1 is not None:
            drivers.append({"dir": direcao(r1), "t": mov("Londres (robusta)", r1) + " no dia."})

    p15 = (ar.get("previsao") or {}).get("15d")
    if p15:
        ch = p15["chanceAlta"]
        frases.append(f"Para os próximos 15 dias, a previsão do arábica aponta R$ {num(p15['centro'], 0)}, "
                      f"numa faixa provável de R$ {num(p15['faixa70'][0], 0)} a R$ {num(p15['faixa70'][1], 0)}.")
        drivers.append({"dir": "alta" if ch >= 0.55 else "baixa" if ch <= 0.45 else "neutro",
                        "t": f"Previsão de 15 dias: {round(ch * 100)}% de chance de alta para o arábica."})

    fb = ar.get("fisicoVsBolsa") or {}
    if fb.get("hoje") is not None and fb.get("media") is not None and abs(fb["hoje"] - fb["media"]) >= 0.03:
        lado = "mais barato" if fb["hoje"] < fb["media"] else "mais caro"
        drivers.append({"dir": "neutro", "t": f"Físico (CEPEA) está {lado} que o normal em relação a NY: "
                                              f"{pct(fb['hoje'])} contra {pct(fb['media'])} na média."})

    meta = {
        "updatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "automatico": True,
        "headline": headline,
        "summary": " ".join(frases),
        "drivers": drivers[:6],
        "sources": [
            {"nome": "CNBC (NY e dólar)", "url": "https://www.cnbc.com/quotes/@KC.1"},
            {"nome": "TradingView (Londres)", "url": "https://www.tradingview.com/symbols/ICEEUR-RC1!/"},
            {"nome": "Banco Central (PTAX)", "url": "https://www.bcb.gov.br/estabilidadefinanceira/historicocotacoes"},
            {"nome": "CEPEA/Esalq", "url": "https://www.cepea.org.br/br/indicador/cafe.aspx"},
            {"nome": "Agrolink (praças)", "url": "https://www.agrolink.com.br/cotacoes/graos/cafe"},
            {"nome": "Open-Meteo e met.no (clima)", "url": "https://open-meteo.com/"},
        ],
    }
    pr = [x for x in (load("pracas.json", {}).get("pracas") or []) if x.get("data", "") >= recente]
    if pr:  # preço velho não aparece: sem praças recentes, o app mostra o aviso padrão
        meta["pracasDate"] = max(x["data"] for x in pr)
        meta["pracas"] = [{k: x[k] for k in ("praca", "tipo", "preco", "var")} for x in pr]
    (DATA / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), "utf-8")
    print(meta["headline"])


if __name__ == "__main__":
    main()
