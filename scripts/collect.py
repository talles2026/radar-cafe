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
import urllib.parse
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

STATUS = {}


def status(fonte, ok, detalhe=""):
    STATUS[fonte] = {"ok": ok, "detalhe": str(detalhe)[:200]}
    log(fonte, "OK" if ok else "FALHOU", detalhe)


def cnbc_num(v):
    return float(str(v).replace(",", "").replace("%", "").strip())


def fetch_kc():
    """Café arábica NY em ¢/lb -> ({data: fechamento}, {data, preco, hora} do pregão em andamento)."""
    hist, live = {}, None
    # 1) CNBC: histórico de 1 ano
    try:
        js = json.loads(get("https://ts-api.cnbc.com/harmony/app/charts/1Y.json?symbol=%40KC.1"))
        for b in js["barData"]["priceBars"]:
            t = str(b.get("tradeTime") or "")
            if len(t) >= 8 and b.get("close") not in (None, ""):
                hist[f"{t[:4]}-{t[4:6]}-{t[6:8]}"] = round(cnbc_num(b["close"]), 2)
        status("NY histórico (CNBC)", bool(hist), f"{len(hist)} pregões")
    except Exception as e:
        status("NY histórico (CNBC)", False, e)
    # 2) Yahoo como reserva do histórico (e às vezes traz o dia corrente)
    if len(hist) < 20:
        for host in ("query2", "query1"):
            try:
                js = json.loads(get(f"https://{host}.finance.yahoo.com/v8/finance/chart/KC=F?range=1y&interval=1d"))
                res = js["chart"]["result"][0]
                for t, c in zip(res["timestamp"], res["indicators"]["quote"][0]["close"]):
                    if c is not None:
                        d = datetime.fromtimestamp(t, tz=timezone(timedelta(hours=-5))).date().isoformat()
                        hist[d] = round(float(c), 2)
                status("NY histórico (Yahoo)", True, f"{len(hist)} pregões")
                break
            except Exception as e:
                status("NY histórico (Yahoo)", False, e)
    # 3) Cotação do momento (CNBC)
    try:
        js = json.loads(get("https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol"
                            "?symbols=%40KC.1&requestMethod=itv&noform=1&partnerId=2&fund=1&exthrs=1&output=json"))
        q = js["FormattedQuoteResult"]["FormattedQuote"][0]
        preco = cnbc_num(q["last"])
        hora = q.get("last_time") or q.get("last_timedate") or ""
        try:
            d = datetime.fromisoformat(hora.replace("Z", "+00:00")[:25]).date().isoformat()
        except ValueError:
            d = datetime.now(timezone(timedelta(hours=-5))).date().isoformat()
        live = {"date": d, "preco": round(preco, 2), "hora": hora, "contrato": q.get("altSymbol") or q.get("symbol")}
        status("NY agora (CNBC)", True, f"{preco} em {hora}")
    except Exception as e:
        status("NY agora (CNBC)", False, e)
    return hist, live


def fetch_rc():
    """Café robusta Londres (ICE Europe), primeiro vencimento, em US$/tonelada -> ({data: fechamento}, None).

    Fonte: Notícias Agrícolas (dados Barchart), que mostra os últimos ~10 pregões, cada um
    com o rótulo "Fechamento: dd/mm/aaaa" antes da tabela de contratos."""
    hist = {}
    try:
        html = get("https://www.noticiasagricolas.com.br/cotacoes/cafe/cafe-bolsa-de-londres-liffe")
        text = re.sub(r"<[^>]+>", "|", html)
        text = re.sub(r"\s+", " ", text)
        blocos = re.split(r"Fechamento:\s*", text)[1:]
        for b in blocos:
            md = re.match(r"(\d{2}/\d{2}/\d{4})", b)
            mc = re.search(r"([A-Za-zçÇ]+/\d{2})\s*\|[\s|]*([\d.]+,\d{2})", b)
            if md and mc:
                d = datetime.strptime(md.group(1), "%d/%m/%Y").date().isoformat()
                v = br_num(mc.group(2))
                if 1000 < v < 15000 and d not in hist:
                    hist[d] = round(v, 0)
        status("Londres (Notícias Agrícolas)", bool(hist), f"{len(hist)} pregões até {max(hist) if hist else '-'}")
    except Exception as e:
        status("Londres (Notícias Agrícolas)", False, e)
    return hist, None


def fetch_usd():
    """Dólar PTAX venda (SGS série 1) -> {data: valor}; mais o comercial do momento."""
    out, live = {}, None
    try:
        ini = (date.today() - timedelta(days=KEEP_DAYS)).strftime("%d/%m/%Y")
        js = json.loads(get(f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.1/dados?formato=json&dataInicial={ini}"))
        for item in js:
            d = datetime.strptime(item["data"], "%d/%m/%Y").date().isoformat()
            out[d] = float(item["valor"])
        status("Dólar PTAX (Banco Central)", True, f"{len(out)} dias")
    except Exception as e:
        status("Dólar PTAX (Banco Central)", False, e)
    try:
        js = json.loads(get("https://economia.awesomeapi.com.br/json/last/USD-BRL"))["USDBRL"]
        d = datetime.fromtimestamp(int(js["timestamp"]), tz=timezone(timedelta(hours=-3))).date().isoformat()
        live = {"date": d, "valor": float(js["bid"]), "hora": js.get("create_date", "")}
        status("Dólar agora (AwesomeAPI)", True, f"{js['bid']} em {live['hora']}")
    except Exception as e:
        status("Dólar agora (AwesomeAPI)", False, e)
    if live is None:
        try:
            js = json.loads(get("https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol"
                                "?symbols=BRL%3D&requestMethod=itv&noform=1&partnerId=2&fund=1&exthrs=1&output=json"))
            q = js["FormattedQuoteResult"]["FormattedQuote"][0]
            hora = q.get("last_time") or ""
            try:
                d = datetime.fromisoformat(hora[:19]).date().isoformat()
            except ValueError:
                d = datetime.now(timezone(timedelta(hours=-3))).date().isoformat()
            live = {"date": d, "valor": round(cnbc_num(q["last"]), 4), "hora": hora}
            status("Dólar agora (CNBC)", True, f"{q['last']} em {hora}")
        except Exception as e:
            status("Dólar agora (CNBC)", False, e)
    return out, live


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
            status(f"CEPEA {'arábica' if key == 'cepeaArabica' else 'conilon'} (Notícias Agrícolas)", bool(rows), f"{len(rows)} dias")
        except Exception as e:
            status(f"CEPEA {'arábica' if key == 'cepeaArabica' else 'conilon'} (Notícias Agrícolas)", False, e)
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
    status("Clima (Open-Meteo)", bool(out), f"{len(out)} regiões")
    return out


# ---------------- gravação ----------------

def main():
    DATA.mkdir(exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        quotes = {q["date"]: q for q in json.loads(QUOTES.read_text("utf-8"))}
    except Exception:
        quotes = {}

    (kc, kc_live), (rc, rc_live), (usd, usd_live), cep = fetch_kc(), fetch_rc(), fetch_usd(), fetch_cepea()
    changed = 0

    def put(d, field, v):
        nonlocal changed
        if not is_weekday(d):
            return
        q = quotes.setdefault(d, {"date": d})
        if q.get(field) != v:
            q[field] = v
            q["updatedAt"] = now
            changed += 1

    for d, v in kc.items():
        put(d, "kc", v)
    # pregão em andamento: guarda o preço do momento até sair o fechamento
    if kc_live:
        put(kc_live["date"], "kc", kc_live["preco"])
        quotes.get(kc_live["date"], {})["kcHora"] = kc_live["hora"]
    for d, v in rc.items():
        put(d, "rc", v)
    if rc_live:
        put(rc_live["date"], "rc", rc_live["preco"])
        quotes.get(rc_live["date"], {})["rcHora"] = rc_live["hora"]
    for d, v in usd.items():
        put(d, "usd", v)
        quotes.get(d, {}).pop("usdAoVivo", None)
    # dólar do dia: usa o comercial do momento até sair a PTAX
    if usd_live and usd_live["date"] not in usd:
        put(usd_live["date"], "usd", usd_live["valor"])
        if usd_live["date"] in quotes:
            quotes[usd_live["date"]]["usdAoVivo"] = True
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
    (DATA / "status.json").write_text(json.dumps({"updatedAt": now, "fontes": STATUS}, ensure_ascii=False, indent=1), "utf-8")


if __name__ == "__main__":
    main()
