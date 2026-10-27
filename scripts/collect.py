#!/usr/bin/env python3
"""Coleta de dados do Radar do Café.

Roda no GitHub Actions (grátis). Busca:
  - Café arábica NY (ICE KC, contrato contínuo) no Yahoo Finance, com Stooq como reserva
  - Dólar PTAX (venda) na API SGS do Banco Central
  - Indicadores CEPEA/Esalq arábica e conilon no Notícias Agrícolas (melhor esforço)
  - Previsão de chuva e temperatura mínima (7 dias) no Open-Meteo

Grava data/quotes.json e data/weather.json. Cada fonte é independente:
se uma falhar, as outras continuam e o histórico já salvo é mantido.
"""
import csv
import io
import json
import re
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
QUOTES = DATA / "quotes.json"
WEATHER = DATA / "weather.json"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
KEEP_DAYS = 400

REGIONS = [
    ("Chapada de Minas (Angelândia)", -17.73, -42.26),
    ("Sul de Minas (Varginha)", -21.55, -45.43),
    ("Cerrado Mineiro (Patrocínio)", -18.94, -46.99),
    ("Conilon ES (Linhares)", -19.39, -40.07),
]


def log(*a):
    print(*a, file=sys.stderr)


def get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        charset = r.headers.get_content_charset() or "utf-8"
    return raw.decode(charset, errors="replace")


def br_num(s):
    s = s.strip().replace(".", "").replace(",", ".")
    return float(s)


def is_weekday(iso):
    return date.fromisoformat(iso).weekday() < 5


# ---------------- fontes ----------------

def fetch_kc():
    """Fechamentos diários do café arábica NY em ¢/lb -> {data: valor}."""
    out = {}
    try:
        js = json.loads(get("https://query1.finance.yahoo.com/v8/finance/chart/KC=F?range=1y&interval=1d"))
        res = js["chart"]["result"][0]
        ts = res["timestamp"]
        closes = res["indicators"]["quote"][0]["close"]
        # o timestamp do Yahoo é a abertura do pregão em Nova York
        for t, c in zip(ts, closes):
            if c is None:
                continue
            d = datetime.fromtimestamp(t, tz=timezone(timedelta(hours=-5))).date().isoformat()
            out[d] = round(float(c), 2)
        log(f"KC Yahoo: {len(out)} pregões")
        return out
    except Exception as e:
        log("KC Yahoo falhou:", e)
    try:
        txt = get("https://stooq.com/q/d/l/?s=kc.f&i=d")
        for row in csv.DictReader(io.StringIO(txt)):
            if row.get("Close"):
                out[row["Date"]] = round(float(row["Close"]), 2)
        log(f"KC Stooq: {len(out)} pregões")
    except Exception as e:
        log("KC Stooq falhou:", e)
    return out


def fetch_usd():
    """Dólar PTAX venda (SGS série 1) -> {data: valor}."""
    out = {}
    try:
        ini = (date.today() - timedelta(days=KEEP_DAYS)).strftime("%d/%m/%Y")
        js = json.loads(get(f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.1/dados?formato=json&dataInicial={ini}"))
        for item in js:
            d = datetime.strptime(item["data"], "%d/%m/%Y").date().isoformat()
            out[d] = float(item["valor"])
        log(f"PTAX: {len(out)} dias")
    except Exception as e:
        log("PTAX falhou:", e)
    return out


def parse_cepea_table(html):
    """Extrai pares (data, valor, variação) de tabelas do Notícias Agrícolas."""
    text = re.sub(r"<[^>]+>", "|", html)
    text = re.sub(r"\s+", " ", text)
    rows = {}
    pat = re.compile(r"(\d{2}/\d{2}/\d{4})\s*\|[\s|]*([\d.]+,\d{2})[\s|]*([+-]?\d+,\d+)?")
    for m in pat.finditer(text):
        try:
            d = datetime.strptime(m.group(1), "%d/%m/%Y").date().isoformat()
            v = br_num(m.group(2))
            var = br_num(m.group(3)) if m.group(3) else None
        except ValueError:
            continue
        if 100 < v < 10000 and d not in rows:
            rows[d] = (v, var)
    return rows


def fetch_cepea():
    """{data: {cepeaArabica, cepeaVar, cepeaConilon, conilonVar}} — melhor esforço."""
    out = {}
    pages = [
        ("cepeaArabica", "cepeaVar", "https://www.noticiasagricolas.com.br/cotacoes/cafe/indicador-cepea-esalq-cafe-arabica"),
        ("cepeaConilon", "conilonVar", "https://www.noticiasagricolas.com.br/cotacoes/cafe/indicador-cepea-esalq-cafe-conillon"),
    ]
    for key, vkey, url in pages:
        try:
            rows = parse_cepea_table(get(url))
            for d, (v, var) in rows.items():
                out.setdefault(d, {})[key] = v
                if var is not None:
                    out[d][vkey] = var
            log(f"{key}: {len(rows)} dias")
        except Exception as e:
            log(f"{key} falhou:", e)
    return out


def fetch_weather():
    out = []
    for nome, lat, lon in REGIONS:
        try:
            js = json.loads(get(
                "https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s"
                "&daily=precipitation_sum,temperature_2m_min,temperature_2m_max"
                "&timezone=America%%2FSao_Paulo&forecast_days=7" % (lat, lon)))
            d = js["daily"]
            chuva = round(sum(x or 0 for x in d["precipitation_sum"]), 1)
            tmin = round(min(x for x in d["temperature_2m_min"] if x is not None), 1)
            tmax = round(max(x for x in d["temperature_2m_max"] if x is not None), 1)
            if tmin <= 3:
                nota = "Risco de geada nos próximos dias"
            elif chuva >= 40:
                nota = "Chuva boa para a florada e o pegamento"
            elif chuva >= 10:
                nota = "Chuva moderada prevista"
            elif tmax >= 33:
                nota = "Calor e pouca chuva: atenção à florada"
            else:
                nota = "Pouca chuva prevista"
            out.append({"regiao": nome, "chuva7d": chuva, "tmin": tmin, "tmax": tmax,
                        "dias": d["time"], "chuvaDia": d["precipitation_sum"], "nota": nota})
        except Exception as e:
            log(f"clima {nome} falhou:", e)
    return out


# ---------------- gravação ----------------

def main():
    DATA.mkdir(exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        quotes = {q["date"]: q for q in json.loads(QUOTES.read_text("utf-8"))}
    except Exception:
        quotes = {}

    kc, usd, cep = fetch_kc(), fetch_usd(), fetch_cepea()
    changed = 0
    for src, field in ((kc, "kc"), (usd, "usd")):
        for d, v in src.items():
            if not is_weekday(d):
                continue
            q = quotes.setdefault(d, {"date": d})
            if q.get(field) != v:
                q[field] = v
                q["updatedAt"] = now
                changed += 1
    for d, fields in cep.items():
        if not is_weekday(d):
            continue
        q = quotes.setdefault(d, {"date": d})
        for k, v in fields.items():
            if q.get(k) != v:
                q[k] = v
                q["updatedAt"] = now
                changed += 1

    cutoff = (date.today() - timedelta(days=KEEP_DAYS)).isoformat()
    rows = sorted((q for d, q in quotes.items() if d >= cutoff), key=lambda q: q["date"])
    QUOTES.write_text(json.dumps(rows, ensure_ascii=False, indent=1), "utf-8")
    log(f"quotes.json: {len(rows)} dias, {changed} campos alterados")

    w = fetch_weather()
    if w:
        WEATHER.write_text(json.dumps({"updatedAt": now, "regioes": w}, ensure_ascii=False, indent=1), "utf-8")
        log(f"weather.json: {len(w)} regiões")


if __name__ == "__main__":
    main()
