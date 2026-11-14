import json, urllib.request, pathlib, re
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
H={"User-Agent":UA,"Accept":"text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8","Accept-Language":"pt-BR,pt;q=0.9,en;q=0.8"}
out=pathlib.Path("sonda/out"); out.mkdir(exist_ok=True)
G=[
("na_cafe","https://www.noticiasagricolas.com.br/cotacoes/cafe"),
("na_fisico","https://www.noticiasagricolas.com.br/cotacoes/cafe/cafe-arabica-mercado-fisico-tipo-6-7"),
("agrolink","https://www.agrolink.com.br/cotacoes/graos/cafe/"),
("agrolink_arab","https://www.agrolink.com.br/cotacoes/graos/cafe/cafe-arabica-tipo-6-bebida-dura-sc-60kg"),
("canalrural","https://www.canalrural.com.br/cotacao/cafe/"),
("cafepoint","https://www.cafepoint.com.br/cotacoes/"),
("cooxupe","https://www.cooxupe.com.br/"),
("minasul","https://minasul.com.br/"),
("expocaccer","https://www.expocaccer.com.br/"),
("cccmg","https://www.cccmg.com.br/"),
("yahoo_rc","https://query1.finance.yahoo.com/v8/finance/chart/RC=F?range=1mo&interval=1d"),
("yahoo_rm","https://query1.finance.yahoo.com/v8/finance/chart/RM=F?range=1mo&interval=1d"),
("stooq_rc","https://stooq.com/q/d/l/?s=rc.f&i=d"),
("investing","https://br.investing.com/commodities/london-coffee"),
("mw","https://www.marketwatch.com/investing/future/rm00?countrycode=uk"),
("cnbc_rc","https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol?symbols=@RC.1|@RM.1|LRC.1|@LRC.1|RC.1&requestMethod=itv&noform=1&partnerId=2&fund=1&exthrs=1&output=json"),
]
res={}
def save(n,code,body):
    (out/f"{n}.txt").write_text(body[:400000],"utf-8"); res[n]=[code,len(body)]
for n,u in G:
    try:
        with urllib.request.urlopen(urllib.request.Request(u,headers=H),timeout=30) as r:
            save(n,r.status,r.read().decode(r.headers.get_content_charset() or "utf-8","replace"))
    except Exception as e:
        save(n,str(e)[:120],"")
# TradingView scanner (POST)
for n,mk,syms in (("tv_fut","futures",["ICEEUR:RC1!","ICEEUR:RC2!","ICEUS:KC1!"]),):
    try:
        body=json.dumps({"symbols":{"tickers":syms},"columns":["close","change","name","description","update_mode","expiration"]}).encode()
        req=urllib.request.Request(f"https://scanner.tradingview.com/{mk}/scan",data=body,headers={**H,"Content-Type":"application/json","Origin":"https://www.tradingview.com"})
        with urllib.request.urlopen(req,timeout=30) as r: save(n,r.status,r.read().decode())
    except Exception as e: save(n,str(e)[:120],"")
json.dump(res,open("sonda/out/_resumo.json","w"),indent=1)
print(json.dumps(res,indent=1))
