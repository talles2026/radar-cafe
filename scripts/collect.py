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
import math
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


def get(url, timeout=30, ua=None):
    req = urllib.request.Request(url, headers={"User-Agent": ua or UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        charset = r.headers.get_content_charset() or "utf-8"
    return raw.decode(charset, errors="replace")


def br_num(s):
    s = s.strip().replace(".", "").replace(",", ".")
    return float(s)


def ultimo_dia_util(atras=0, ref=None):
    """Data ISO do dia útil `atras` dias úteis antes de hoje (0 = hoje, se for dia útil)."""
    d = ref or datetime.now(timezone(timedelta(hours=-3))).date()
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    n = 0
    while n < atras:
        d -= timedelta(days=1)
        if d.weekday() < 5:
            n += 1
    return d.isoformat()


def dias_uteis_entre(a, b):
    """Dias úteis depois de a até b (b >= a)."""
    da, db = date.fromisoformat(a), date.fromisoformat(b)
    n = 0
    while da < db:
        da += timedelta(days=1)
        if da.weekday() < 5:
            n += 1
    return n


def is_weekday(iso):
    return date.fromisoformat(iso).weekday() < 5


# ---------------- fontes ----------------

STATUS = {}


def status(fonte, ok, detalhe=""):
    STATUS[fonte] = {"ok": ok, "detalhe": str(detalhe)[:200]}
    log(fonte, "OK" if ok else "FALHOU", detalhe)


def cnbc_num(v):
    return float(str(v).replace(",", "").replace("%", "").strip())


def cnbc_hist(sym):
    js = json.loads(get("https://ts-api.cnbc.com/harmony/app/charts/1Y.json?symbol=" + urllib.parse.quote(sym)))
    out = {}
    for b in js["barData"]["priceBars"]:
        t = str(b.get("tradeTime") or "")
        if len(t) >= 8 and b.get("close") not in (None, ""):
            out[f"{t[:4]}-{t[4:6]}-{t[6:8]}"] = cnbc_num(b["close"])
    return out


def cnbc_quote(sym, tz_horas):
    js = json.loads(get("https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol"
                        "?symbols=" + urllib.parse.quote(sym) + "&requestMethod=itv&noform=1&partnerId=2&fund=1&exthrs=1&output=json"))
    q = js["FormattedQuoteResult"]["FormattedQuote"][0]
    hora = q.get("last_time") or ""
    try:
        d = datetime.fromisoformat(hora[:19]).date().isoformat()
    except ValueError:
        d = datetime.now(timezone(timedelta(hours=tz_horas))).date().isoformat()
    return {"date": d, "preco": cnbc_num(q["last"]), "hora": hora, "contrato": q.get("altSymbol") or q.get("symbol")}


def fetch_kc():
    """Café arábica NY em ¢/lb, 1º e 2º vencimentos -> (hist1, hist2, live1, live2)."""
    h1, h2, l1, l2 = {}, {}, None, None
    try:
        h1 = {d: round(v, 2) for d, v in cnbc_hist("@KC.1").items()}
        status("NY histórico (CNBC)", bool(h1), f"{len(h1)} pregões")
    except Exception as e:
        status("NY histórico (CNBC)", False, e)
    try:
        h2 = {d: round(v, 2) for d, v in cnbc_hist("@KC.2").items()}
        status("NY 2º vencimento (CNBC)", bool(h2), f"{len(h2)} pregões")
    except Exception as e:
        status("NY 2º vencimento (CNBC)", False, e)
    try:
        l1 = cnbc_quote("@KC.1", -5)
        l1["preco"] = round(l1["preco"], 2)
        status("NY agora (CNBC)", True, f"{l1['preco']} ({l1['contrato']}) em {l1['hora']}")
    except Exception as e:
        status("NY agora (CNBC)", False, e)
    try:
        l2 = cnbc_quote("@KC.2", -5)
        l2["preco"] = round(l2["preco"], 2)
        if not h2:
            status("NY 2º vencimento (CNBC)", True, f"cotação do dia {l2['preco']} ({l2['contrato']}); suficiente para a emenda")
    except Exception as e:
        if not h2:
            status("NY 2º vencimento (CNBC)", False, e)
    return h1, h2, l1, l2


def parse_londres(html):
    """Blocos "Fechamento: dd/mm/aaaa" seguidos da tabela de contratos -> {data: (c1, v1, c2, v2)}."""
    hist = {}
    text = re.sub(r"<[^>]+>", "|", html)
    text = re.sub(r"\s+", " ", text)
    for b in re.split(r"Fechamento:\s*", text)[1:]:
        md = re.match(r"(\d{2}/\d{2}/\d{4})", b)
        rows = re.findall(r"([A-Za-zçÇ]+/\d{2})\s*\|[\s|]*([\d.]+,\d{2})", b[:1500])
        if md and rows:
            d = datetime.strptime(md.group(1), "%d/%m/%Y").date().isoformat()
            v1 = br_num(rows[0][1])
            if 1000 < v1 < 15000 and d not in hist:
                c2, v2 = (rows[1][0], br_num(rows[1][1])) if len(rows) > 1 else (None, None)
                hist[d] = (rows[0][0], round(v1, 0), c2, round(v2, 0) if v2 and 1000 < v2 < 15000 else None)
    return hist


def fetch_rc():
    """Café robusta Londres (ICE Europe) em US$/t: 1º e 2º contratos -> {data: (c1, v1, c2, v2)}.
    Fonte principal: página de Londres do Notícias Agrícolas; reserva: página geral de café do mesmo site."""
    hist = {}
    for nome, url in (("Londres (Notícias Agrícolas)", "https://www.noticiasagricolas.com.br/cotacoes/cafe/cafe-bolsa-de-londres-liffe"),
                      ("Londres reserva (Notícias Agrícolas, página geral)", "https://www.noticiasagricolas.com.br/cotacoes/cafe")):
        try:
            h = parse_londres(get(url))
            for d, v in h.items():
                hist.setdefault(d, v)
            status(nome, bool(h), f"{len(h)} pregões até {max(h) if h else '-'}")
            if h and max(h) >= ultimo_dia_util(1):
                break
        except Exception as e:
            status(nome, False, e)
    return hist


def fetch_usd_comercial():
    """Dólar comercial (fechamento diário e agora), usado nos cálculos: série única, sem misturar com a PTAX."""
    hist, live = {}, None
    try:
        hist = {d: round(v, 4) for d, v in cnbc_hist("BRL=").items() if 2 < v < 10}
        status("Dólar comercial histórico (CNBC)", bool(hist), f"{len(hist)} dias")
    except Exception as e:
        status("Dólar comercial histórico (CNBC)", False, e)
    try:
        live = cnbc_quote("BRL=", -3)
        live["preco"] = round(live["preco"], 4)
        status("Dólar agora (CNBC)", True, f"{live['preco']} em {live['hora']}")
    except Exception as e:
        status("Dólar agora (CNBC)", False, e)
    return hist, live


def fetch_cepea_hist():
    """Série completa dos indicadores CEPEA no site do CEPEA (planilha). Melhor esforço."""
    out = {}
    for campo, cid in (("cepeaArabica", 23), ("cepeaConilon", 24)):
        try:
            req = urllib.request.Request(f"https://www.cepea.org.br/br/indicador/series/cafe.aspx?id={cid}", headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read()
            linhas = []
            if raw[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":  # planilha .xls antiga
                import xlrd
                sh = xlrd.open_workbook(file_contents=raw, ignore_workbook_corruption=True).sheet_by_index(0)
                linhas = [[str(c.value) for c in sh.row(i)] for i in range(sh.nrows)]
            elif raw[:2] == b"PK":  # .xlsx
                import openpyxl
                wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True)
                linhas = [[str(c) if c is not None else "" for c in row] for row in wb.active.iter_rows(values_only=True)]
            else:
                txt = raw.decode("utf-8", errors="replace")
                for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", txt, re.S | re.I):
                    linhas.append([re.sub(r"<[^>]+>", "", td).strip() for td in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S | re.I)])
            n = 0
            for ln in linhas:
                if len(ln) < 2:
                    continue
                m = re.match(r"(\d{2})/(\d{2})/(\d{4})", ln[0])
                if not m:
                    continue
                try:
                    v = float(ln[1]) if re.match(r"^\d+(\.\d+)?$", ln[1]) else br_num(ln[1])
                except ValueError:
                    continue
                if 50 < v < 10000:
                    out.setdefault(f"{m.group(3)}-{m.group(2)}-{m.group(1)}", {})[campo] = round(v, 2)
                    n += 1
            status(f"CEPEA série completa ({'arábica' if cid == 23 else 'conilon'})", n > 0, f"{n} dias")
        except Exception as e:
            status(f"CEPEA série completa ({'arábica' if cid == 23 else 'conilon'})", False, e)
    return out


def fetch_usd():
    """Dólar PTAX venda (SGS série 1) -> {data: valor}. Só para exibir; os cálculos usam o comercial."""
    out = {}
    try:
        ini = (date.today() - timedelta(days=KEEP_DAYS)).strftime("%d/%m/%Y")
        js = json.loads(get(f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.1/dados?formato=json&dataInicial={ini}"))
        for item in js:
            d = datetime.strptime(item["data"], "%d/%m/%Y").date().isoformat()
            out[d] = float(item["valor"])
        status("Dólar PTAX (Banco Central)", True, f"{len(out)} dias")
    except Exception as e:
        status("Dólar PTAX (Banco Central)", False, e)
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
    if not out:
        out = fetch_weather_metno()
    return out


def fetch_weather_metno():
    """Reserva do clima: serviço meteorológico da Noruega (met.no), gratuito, cobre o mundo todo."""
    out = []
    for nome, lat, lon in REGIONS:
        try:
            js = json.loads(get(f"https://api.met.no/weatherapi/locationforecast/2.0/compact?lat={lat}&lon={lon}",
                               ua="radar-cafe/1.0 github.com/talles2026/radar-cafe"))
            dias = {}
            for t in js["properties"]["timeseries"]:
                d = (datetime.fromisoformat(t["time"].replace("Z", "+00:00")) - timedelta(hours=3)).date().isoformat()
                inst = t["data"]["instant"]["details"]
                chuva = ((t["data"].get("next_1_hours") or t["data"].get("next_6_hours") or {}).get("details") or {}).get("precipitation_amount", 0)
                x = dias.setdefault(d, {"chuva": 0.0, "tmin": 99.0, "tmax": -99.0})
                x["chuva"] += chuva if t["data"].get("next_1_hours") else chuva / 6
                x["tmin"] = min(x["tmin"], inst["air_temperature"])
                x["tmax"] = max(x["tmax"], inst["air_temperature"])
            ds = sorted(dias)[:7]
            chuva = round(sum(dias[d]["chuva"] for d in ds), 1)
            tmin = round(min(dias[d]["tmin"] for d in ds), 1)
            tmax = round(max(dias[d]["tmax"] for d in ds), 1)
            out.append({"regiao": nome, "chuva7d": chuva, "tmin": tmin, "tmax": tmax, "dias": ds,
                        "chuvaDia": [round(dias[d]["chuva"], 1) for d in ds], "nota": ""})
        except Exception as e:
            log(f"clima reserva {nome} falhou:", e)
    status("Clima reserva (met.no)", bool(out), f"{len(out)} regiões")
    return out


# ---------------- gravação ----------------

def ajustar(quotes, f1, f2, contrato=None, meses_virada=()):
    """Emenda os vencimentos: na troca de contrato, o retorno do dia é medido contra o 2º vencimento
    da véspera (que vira o 1º), e o histórico é ajustado para trás. Grava f1+"Adj" e marca a virada."""
    ds = sorted(d for d, q in quotes.items() if q.get(f1))
    if len(ds) < 2:
        return 0
    rets, viradas = {}, 0
    for a, b in zip(ds, ds[1:]):
        qa, qb = quotes[a], quotes[b]
        r_front = math.log(qb[f1] / qa[f1])
        virada = False
        if contrato and qa.get(contrato) and qb.get(contrato):
            virada = qa[contrato] != qb[contrato]
        elif qa.get(f2):
            m, dia = int(b[5:7]), int(b[8:10])
            perto = m in meses_virada or ((m - 1) in meses_virada and dia <= 10)
            r_sw = math.log(qb[f1] / qa[f2])
            virada = perto and abs(r_sw) + 0.015 < abs(r_front)
        qb.pop(f1 + "Virada", None)
        if virada and qa.get(f2):
            rets[b] = math.log(qb[f1] / qa[f2])
            qb[f1 + "Virada"] = True
            viradas += 1
        else:
            rets[b] = r_front
    adj = {ds[-1]: quotes[ds[-1]][f1]}
    for a, b in reversed(list(zip(ds, ds[1:]))):
        adj[a] = adj[b] / math.exp(rets[b])
    for d in ds:
        quotes[d][f1 + "Adj"] = round(adj[d], 4)
    return viradas


def escrever_saude(rows, weather, now):
    agora = datetime.now(timezone(timedelta(hours=-3)))
    hora = agora.hour
    def ult(campo):
        ds = [q["date"] for q in rows if q.get(campo)]
        return max(ds) if ds else None
    try:
        meta = json.loads((DATA / "meta.json").read_text("utf-8"))
    except Exception:
        meta = {}
    hoje_util = ultimo_dia_util(0)
    # data que cada dado deveria ter agora (sem contar feriados)
    esperado = {
        "NY": hoje_util if hora >= 7 and agora.weekday() < 5 else ultimo_dia_util(1),
        "Dólar": hoje_util if hora >= 9 and agora.weekday() < 5 else ultimo_dia_util(1),
        "Londres": hoje_util if hora >= 17 and agora.weekday() < 5 else ultimo_dia_util(1),
        "CEPEA arábica": ultimo_dia_util(1),
        "CEPEA conilon": ultimo_dia_util(1),
    }
    ultimo = {"NY": ult("kc"), "Dólar": ult("usdCom") or ult("usd"), "Londres": ult("rc"),
              "CEPEA arábica": ult("cepeaArabica"), "CEPEA conilon": ult("cepeaConilon")}
    itens = {}
    for k, u in ultimo.items():
        atraso = dias_uteis_entre(u, esperado[k]) if u and u < esperado[k] else (0 if u else 99)
        itens[k] = {"ultimo": u, "esperado": esperado[k], "atrasoDiasUteis": atraso,
                    "estado": "ok" if atraso == 0 else ("atencao" if atraso == 1 else "falha")}
    def idade_h(iso):
        try:
            return (datetime.now(timezone.utc) - datetime.fromisoformat(iso.replace("Z", "+00:00"))).total_seconds() / 3600
        except Exception:
            return 999
    wa = idade_h((weather and now) or (json.loads((DATA / "weather.json").read_text("utf-8")).get("updatedAt") if WEATHER.exists() else "")) if not weather else 0
    itens["Clima"] = {"ultimo": now if weather else None, "estado": "ok" if weather or wa < 30 else "falha"}
    pa = meta.get("pracasDate")
    itens["Praças"] = {"ultimo": pa, "estado": "ok" if pa and dias_uteis_entre(pa, ultimo_dia_util(1)) <= 1 else ("atencao" if pa and dias_uteis_entre(pa, ultimo_dia_util(1)) <= 2 else "falha")}
    an = idade_h(meta.get("updatedAt") or "")
    itens["Análise do dia"] = {"ultimo": meta.get("updatedAt"), "estado": "ok" if an < 30 or agora.weekday() >= 5 else ("atencao" if an < 54 else "falha")}
    problemas = [k for k, v in itens.items() if v["estado"] == "falha"]
    (DATA / "saude.json").write_text(json.dumps({"verificadoEm": now, "itens": itens, "problemas": problemas},
                                                 ensure_ascii=False, indent=1), "utf-8")


def main():
    DATA.mkdir(exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        quotes = {q["date"]: q for q in json.loads(QUOTES.read_text("utf-8"))}
    except Exception:
        quotes = {}

    kc1, kc2, kl1, kl2 = fetch_kc()
    rc = fetch_rc()
    ptax = fetch_usd()
    ucom, ulive = fetch_usd_comercial()
    cep = fetch_cepea()
    atrasado = not cep or max(cep) < ultimo_dia_util(1)
    if atrasado:
        status("CEPEA (Notícias Agrícolas)", False, "sem o dia útil anterior; usando a planilha do CEPEA como reserva")
    if atrasado or sum(1 for q in quotes.values() if q.get("cepeaArabica")) < 150:
        for d, f in fetch_cepea_hist().items():
            for k, v in f.items():
                cep.setdefault(d, {}).setdefault(k, v)
    changed = 0

    LIMITE = {"kc": 0.15, "rc": 0.15, "cepeaArabica": 0.15, "cepeaConilon": 0.15, "usdCom": 0.12, "usd": 0.12}
    rejeitados = []

    def plausivel(d, field, v):
        if field not in LIMITE:
            return True
        ant = [q for dd, q in quotes.items() if dd < d and q.get(field)]
        if not ant:
            return True
        ref = max(ant, key=lambda q: q["date"])[field]
        dias = max(1, dias_uteis_entre(max(ant, key=lambda q: q["date"])["date"], d))
        return abs(v / ref - 1) <= LIMITE[field] * min(3, dias) ** 0.5 or field in ("kc", "rc") and abs(v / ref - 1) <= 0.25

    def put(d, field, v):
        nonlocal changed
        if not is_weekday(d) or v is None:
            return
        if isinstance(v, (int, float)) and not plausivel(d, field, v):
            rejeitados.append(f"{field} {d}={v}")
            return
        q = quotes.setdefault(d, {"date": d})
        if q.get(field) != v:
            q[field] = v
            q["updatedAt"] = now
            changed += 1

    # limpa o formato antigo (dólar do momento gravado no campo da PTAX)
    for q in quotes.values():
        if q.pop("usdAoVivo", None):
            q.pop("usd", None)

    for d, v in kc1.items():
        put(d, "kc", v)
    for d, v in kc2.items():
        put(d, "kc2", v)
    if kl1:  # pregão em andamento: preço do momento até sair o fechamento
        put(kl1["date"], "kc", kl1["preco"])
        quotes.get(kl1["date"], {})["kcHora"] = kl1["hora"]
        if kl2:
            put(kl2["date"], "kc2", kl2["preco"])
    for d, (c1, v1, c2, v2) in rc.items():
        put(d, "rc", v1)
        put(d, "rcContrato", c1)
        put(d, "rc2", v2)
    for d, v in ptax.items():
        put(d, "usd", v)
    for d, v in ucom.items():
        put(d, "usdCom", v)
    if ulive:
        put(ulive["date"], "usdCom", ulive["preco"])
        quotes.get(ulive["date"], {})["usdComHora"] = ulive["hora"]
    for d, fields in cep.items():
        for k, v in fields.items():
            put(d, k, v)

    cutoff = (date.today() - timedelta(days=KEEP_DAYS)).isoformat()
    quotes = {d: q for d, q in quotes.items() if d >= cutoff}
    vk = ajustar(quotes, "kc", "kc2", meses_virada=(2, 4, 6, 8, 11))
    vr = ajustar(quotes, "rc", "rc2", contrato="rcContrato", meses_virada=(12, 2, 4, 6, 8, 10))
    status("Emenda de contratos", True, f"NY: {vk} virada(s); Londres: {vr} virada(s)")
    status("Conferência de valores", not rejeitados, ("rejeitados por salto impossível: " + ", ".join(rejeitados[:6])) if rejeitados else "nenhum valor estranho")
    rows = sorted(quotes.values(), key=lambda q: q["date"])
    # uma linha por dia: arquivo menor para o celular baixar e ainda legível no histórico do GitHub
    QUOTES.write_text("[\n" + ",\n".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in rows) + "\n]\n", "utf-8")
    log(f"quotes.json: {len(rows)} dias, {changed} campos alterados")

    w = fetch_weather()
    if w:
        WEATHER.write_text(json.dumps({"updatedAt": now, "regioes": w}, ensure_ascii=False, indent=1), "utf-8")
        log(f"weather.json: {len(w)} regiões")
    escrever_saude(rows, w, now)
    (DATA / "status.json").write_text(json.dumps({"updatedAt": now, "fontes": STATUS}, ensure_ascii=False, indent=1), "utf-8")


if __name__ == "__main__":
    main()
