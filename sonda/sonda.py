import json, urllib.request, pathlib, re
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
H={"User-Agent":UA,"Accept":"text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8","Accept-Language":"pt-BR,pt;q=0.9,en;q=0.8"}
out=pathlib.Path("sonda/out"); out.mkdir(exist_ok=True)
G=[
("al_uf","https://www.agrolink.com.br/cotacoes/graos/cafe?uf=mg"),
("al_busca_uf","https://www.agrolink.com.br/cotacoes/busca?cultura=cafe&uf=mg"),
("al_busca_estado","https://www.agrolink.com.br/cotacoes/busca?cultura=cafe&estado=mg"),
("al_p2","https://www.agrolink.com.br/cotacoes/graos/cafe?pagina=2"),
("al_hoje","https://www.agrolink.com.br/cotacoes/graos/cafe?periodo=hoje"),
("al_ir","https://www.agrolink.com.br/api/cotacoes/historico/ir?cod=2110&uf=mg"),
("al_prod_safra","https://www.agrolink.com.br/cotacoes/graos/cafe/cafe-arabica-bebida-dura-tipo-6-safra-nova-sc-60kg"),
("al_prod_t6","https://www.agrolink.com.br/cotacoes/graos/cafe/cafe-arabica-tipo-6-sc-60kg"),
("al_prod_t6_mg","https://www.agrolink.com.br/cotacoes/graos/cafe/cafe-arabica-tipo-6-sc-60kg?uf=mg"),
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
for n,mk,syms in (("tv_fut","futures",["ICEEUR:RC1!","ICEEUR:RC2!","ICEEUR:RCF2027","ICEEUR:RCH2027","ICEEUR:RCX2026","ICEUS:KCH2027"]),):
    try:
        body=json.dumps({"symbols":{"tickers":syms},"columns":["close","change","name","description","update_mode","expiration"]}).encode()
        req=urllib.request.Request(f"https://scanner.tradingview.com/{mk}/scan",data=body,headers={**H,"Content-Type":"application/json","Origin":"https://www.tradingview.com"})
        with urllib.request.urlopen(req,timeout=30) as r: save(n,r.status,r.read().decode())
    except Exception as e: save(n,str(e)[:120],"")
json.dump(res,open("sonda/out/_resumo.json","w"),indent=1)
print(json.dumps(res,indent=1))
