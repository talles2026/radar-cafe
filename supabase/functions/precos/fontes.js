// Radar de Preços — tipo do produto, leitura das lojas e escolha do menor preço.
// Lojas que bloqueiam leitura automática (Shopee, Google, Facebook, Mercado Livre direto) entram
// pelos comparadores quando aparecem lá, e sempre com o link da busca pronta, ordenada pelo menor preço.

const UA_PC = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36";
const CAB = { "User-Agent": UA_PC, "Accept-Language": "pt-BR,pt;q=0.9", "Accept": "text/html,application/xhtml+xml,*/*;q=0.8" };

// ---------------------------------------------------------------- texto
export const norm = (s) => String(s ?? "").replace(/\+/g, " plus ").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/[^a-z0-9.,/ -]+/g, " ").replace(/\s+/g, " ").trim();
const ent = (s) => String(s ?? "").replace(/&amp;/g, "&").replace(/&quot;/g, '"').replace(/&#39;|&#x27;|&apos;/g, "'").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&nbsp;|&#160;/g, " ").replace(/<[^>]+>/g, "").replace(/\s+/g, " ").trim();
export function valor(s) {
  const m = String(s ?? "").replace(/\s/g, "").match(/R\$?([\d.]+)(?:,(\d{1,2}))?/);
  if (!m) return null;
  const v = parseFloat(m[1].replace(/\./g, "") + "." + (m[2] ?? "0"));
  return isFinite(v) && v > 0 ? v : null;
}
const STOP = new Set("de da do das dos para com sem e o a os as um uma em no na por kit novo nova original lacrado promocao oferta".split(" "));
export const tokens = (q) => norm(q).replace(/[.,/]/g, " ").split(" ").filter((t) => t.length >= 2 && !STOP.has(t));

// ---------------------------------------------------------------- tipo do produto
const MARCAS_VEIC = "fiat volkswagen vw chevrolet gm ford toyota honda hyundai renault nissan jeep peugeot citroen mitsubishi kia bmw mercedes audi volvo chery caoa byd gwm ram dodge suzuki yamaha kawasaki harley triumph dafra shineray haojue iveco scania volvo".split(" ");
const MODELOS_FORTES = "hilux sw4 corolla etios yaris civic hrv hr-v wrv wr-v onix tracker s10 montana cobalt prisma celta corsa spin cruze ranger ecosport fiesta ka hb20 hb20s creta tucson renegade compass commander kwid sandero logan duster oroch frontier versa kicks l200 pajero outlander strada toro mobi argo cronos fastback palio siena uno fiorino saveiro voyage virtus nivus t-cross tcross taos amarok polo gol fox jetta tiguan titan biz bros xre nmax pcx lander crosser cg125 cg150 cg160 xtz cb300 cb500 twister hornet tenere dominar ducato master sprinter daily accelo".split(" ");
const MODELOS_FRACOS = "city fit fan pop pulse factor fazer up 208 2008 3008 c3 c4 cg cb march sentra golf up! hb captur".split(" ");
const PALAVRAS_VEIC = "carro moto motocicleta caminhonete picape pickup caminhao camionete utilitario suv sedan hatch trator".split(" ");
const PECAS = "pastilha disco filtro farol lanterna pneu roda calota bateria amortecedor mola retrovisor parachoque para-choque grade capo paralama porta vidro maçaneta macaneta correia tensor embreagem vela bobina radiador bomba sensor modulo injecao bico cabecote junta pistao anel biela virabrequim cambio semi-eixo homocinetica terminal pivo bandeja bucha coxim escapamento silencioso catalisador oleo aditivo palheta tapete capa banco volante alternador motor-de-partida chicote peca pecas kit miniatura carrinho brinquedo adesivo emblema chaveiro som multimidia central alarme insulfilm engate rack bagageiro".split(" ");
const CATS = [
  ["informatica", "Informática", "notebook|laptop|computador|pc gamer|desktop|ssd|hd externo|nvme|monitor|teclado|mouse|placa de video|placa mae|rtx|gtx|radeon|processador|ryzen|core i3|core i5|core i7|core i9|memoria ram|ddr4|ddr5|roteador|impressora|gabinete|fonte atx|webcam|pendrive|pen drive|cartao de memoria|nobreak|switch de rede|macbook|chromebook"],
  ["eletronicos", "Eletrônicos", "celular|smartphone|iphone|galaxy|redmi|xiaomi|poco|motorola|moto g|realme|tv|televisao|smart tv|fone|headset|caixa de som|jbl|tablet|ipad|smartwatch|relogio inteligente|console|playstation|ps5|ps4|xbox|nintendo|camera|gopro|drone|kindle|echo dot|alexa|projetor|soundbar"],
  ["eletrodomesticos", "Eletrodomésticos", "geladeira|refrigerador|fogao|cooktop|micro-ondas|microondas|forno eletrico|lavadora|maquina de lavar|lava e seca|secadora|freezer|air fryer|airfryer|fritadeira|liquidificador|batedeira|ar condicionado|ar-condicionado|split|ventilador|aspirador|cafeteira|purificador|bebedouro|lava-loucas|lava loucas|sanduicheira|panela eletrica|ferro de passar|depurador|coifa"],
  ["eletricos", "Material elétrico", "fio|cabo flexivel|disjuntor|tomada|interruptor|lampada|refletor|quadro de distribuicao|dps|contator|rele|motor eletrico|inversor solar|painel solar|placa solar|chuveiro|extensao|eletroduto|conduite|sensor de presenca"],
  ["ferramentas", "Ferramentas", "furadeira|parafusadeira|serra circular|serra tico-tico|esmerilhadeira|lixadeira|martelete|chave de impacto|alicate|compressor|gerador|solda|maquina de solda|motosserra|rocadeira|lavadora de alta pressao|jogo de chaves|trena|nivel a laser"],
  ["pecas", "Peças automotivas", "pneu|pneus|aro 13|aro 14|aro 15|aro 16|aro 17|bateria moura|bateria heliar|bateria automotiva|moura|heliar|oleo de motor|oleo motor|5w30|15w40|pastilha de freio|amortecedor|filtro de oleo|filtro de ar|vela de ignicao|kit embreagem|kit relacao|lampada h4|lampada h7|retrovisor|parachoque"],
  ["agro", "Agro", "adubo|fertilizante|ureia|calcario|semente|sementes|herbicida|pulverizador|arame farpado|mourao|cerca eletrica|racao|sal mineral|ordenhadeira|despolpador|secador de cafe|saco de cafe|lona|derricadeira|trator"],
  ["material", "Material de construção", "cimento|areia|brita|tijolo|bloco de concreto|telha|vergalhao|tinta|argamassa|rejunte|piso|porcelanato|revestimento|cano|tubo pvc|caixa d agua|caixa dagua|madeira|tabua|portao|janela|manta|impermeabilizante"],
];
export function detectarTipo(q) {
  const n = " " + norm(q) + " ";
  const tem = (lista) => lista.some((w) => n.includes(" " + w + " "));
  const ano = /\b(19[6-9]\d|20[0-3]\d)\b/.test(n);
  const marca = tem(MARCAS_VEIC), forte = tem(MODELOS_FORTES), fraco = tem(MODELOS_FRACOS), palavra = tem(PALAVRAS_VEIC);
  if ((forte || marca || palavra || (fraco && ano)) && tem(PECAS)) return { id: "pecas", nome: "Peças automotivas" };
  if (forte || palavra || (marca && (ano || fraco)) || (fraco && ano)) {
    const moto = /\b(moto|motocicleta|biz|bros|xre|nmax|pcx|lander|crosser|cg|cg125|cg150|cg160|xtz|cb300|cb500|twister|hornet|tenere|dominar|titan|fan|pop|factor|fazer|yamaha|kawasaki|harley|triumph|dafra|shineray|haojue)\b/.test(n);
    return { id: "veiculo", nome: moto ? "Veículo · moto" : "Veículo", moto };
  }
  let melhor = null, pts = 0;
  for (const [id, nome, lista] of CATS) {
    let p = 0;
    for (const w of lista.split("|")) if (n.includes(" " + w + " ")) p += w.includes(" ") ? 3 : w.length > 5 ? 2 : 1;
    if (p > pts) { pts = p; melhor = { id, nome }; }
  }
  if (melhor) return melhor;
  return { id: "outros", nome: "Produto" };
}

// ---------------------------------------------------------------- lojas
export const LOJAS = {
  ml: { nome: "Mercado Livre" }, shopee: { nome: "Shopee" }, amazon: { nome: "Amazon" }, ali: { nome: "AliExpress" },
  google: { nome: "Google" }, olx: { nome: "OLX" }, fb: { nome: "Facebook Marketplace" },
};
export function lojasDoTipo(tipo) { return tipo.id === "veiculo" ? ["olx", "ml", "fb", "google"] : ["ml", "shopee", "amazon", "ali", "google"]; }

const slug = (q) => norm(q).replace(/[.,/]/g, " ").trim().replace(/\s+/g, "-");
export function linkBusca(loja, q, tipo) {
  const e = encodeURIComponent(q), veic = tipo.id === "veiculo";
  switch (loja) {
    case "ml": return veic ? `https://lista.mercadolivre.com.br/veiculos/${slug(q)}_OrderId_PRICE` : `https://lista.mercadolivre.com.br/${slug(q)}_OrderId_PRICE_NoIndex_True`;
    case "shopee": return `https://shopee.com.br/search?keyword=${e}&order=asc&sortBy=price`;
    case "amazon": return `https://www.amazon.com.br/s?k=${e}&s=price-asc-rank`;
    case "ali": return `https://pt.aliexpress.com/w/wholesale-${slug(q)}.html?SortType=price_asc`;
    case "google": return veic ? `https://www.google.com/search?q=${e}+%C3%A0+venda&hl=pt-BR&gl=br` : `https://www.google.com/search?q=${e}&udm=28&tbs=mr:1,p_ord:p&hl=pt-BR&gl=br`;
    case "olx": return veic ? `https://www.olx.com.br/autos-e-pecas/${tipo.moto ? "motos" : "carros-vans-e-utilitarios"}?q=${e}&sp=1` : `https://www.olx.com.br/brasil?q=${e}&sp=1`;
    case "fb": return `https://www.facebook.com/marketplace/category/search?query=${e}&sortBy=price_ascend`;
  }
  return "";
}
const lojaDoVendedor = (v) => {
  const s = norm(v);
  if (/mercado ?livre|mercadolivre/.test(s)) return "ml";
  if (/shopee/.test(s)) return "shopee";
  if (/amazon/.test(s)) return "amazon";
  if (/aliexpress/.test(s)) return "ali";
  if (/\bolx\b/.test(s)) return "olx";
  return null;
};

async function pegar(url, cab = CAB, ms = 14000, tentativa = 0) {
  const r = await fetch(url, { headers: cab, redirect: "follow", signal: AbortSignal.timeout(ms) });
  if ((r.status === 503 || r.status === 429) && tentativa < 1) { await new Promise((ok) => setTimeout(ok, 1500)); return pegar(url, cab, ms, 1); }
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  const t = await r.text();
  if (/account-verification|verify\/traffic|captcha/i.test(r.url)) throw new Error("bloqueado");
  return t;
}
const abs = (u, base) => { u = ent(u); if (!u) return ""; if (u.startsWith("//")) return "https:" + u; if (u.startsWith("/")) return base + u; return u; };

// Amazon: resultados da busca
function lerAmazon(html) {
  const out = [], partes = html.split(/data-component-type="s-search-result"/);
  for (let i = 1; i < partes.length; i++) {
    const antes = partes[i - 1].slice(-700), seg = partes[i].slice(0, 9000);
    const asin = (antes.match(/data-asin="([A-Z0-9]{10})"/g) || []).pop()?.slice(11, 21);
    const tit = seg.match(/<h2[^>]*aria-label="([^"]+)"/)?.[1] ?? seg.match(/<h2[^>]*>(?:\s*<a[^>]*>)?\s*<span[^>]*>([^<]+)<\/span>/)?.[1];
    const preco = valor(seg.match(/class="a-offscreen">([^<]+)</)?.[1]);
    if (asin && tit && preco) out.push({ loja: "amazon", titulo: ent(tit).replace(/^Anúncio patrocinado – /i, ""), preco, link: `https://www.amazon.com.br/dp/${asin}`, vendedor: "Amazon" });
  }
  return out;
}
// AliExpress: cartões da busca
function lerAli(html) {
  const out = [], re = /<h3 class="[^"]*titleText[^"]*">([\s\S]*?)<\/h3>/g; let m;
  while ((m = re.exec(html))) {
    const antes = html.slice(Math.max(0, m.index - 6000), m.index), depois = html.slice(m.index, m.index + 2500);
    const id = (antes.match(/aliexpress\.com\/item\/(\d+)\.html/g) || []).pop()?.match(/(\d+)\.html/)?.[1];
    const preco = valor(depois.match(/aria-label="(R\$[^"]+)"/)?.[1]);
    if (id && preco) out.push({ loja: "ali", titulo: ent(m[1]), preco, link: `https://pt.aliexpress.com/item/${id}.html`, vendedor: "AliExpress" });
  }
  return out;
}
// Bing Shopping: ofertas de várias lojas (Mercado Livre aparece bastante aqui)
function lerBing(html) {
  const out = [], re = /class="br-offInfo[\s\S]*?br-offTtl[^>]*>\s*<span title="([^"]*)"[\s\S]*?class="br-price">([^<]+)<[\s\S]*?br-offSlrTxt">([^<]+)</g; let m;
  while ((m = re.exec(html))) {
    const antes = html.slice(Math.max(0, m.index - 5000), m.index);
    const hrefs = antes.match(/href="([^"]+)"/g) || [];
    let link = hrefs.length ? abs(hrefs[hrefs.length - 1].slice(6, -1), "https://www.bing.com") : "";
    // anúncio do Bing: o endereço real da loja vem codificado no parâmetro u=
    try { const u = new URL(link).searchParams.get("u"); if (u) { const real = decodeURIComponent(atob(u.replace(/-/g, "+").replace(/_/g, "/"))); if (/^https:\/\//.test(real)) link = real; } } catch (_) { /* fica o link do Bing */ }
    const preco = valor(m[2]);
    if (preco) out.push({ loja: lojaDoVendedor(m[3]), titulo: ent(m[1]), preco, link, vendedor: ent(m[3]), via: "Bing Shopping" });
  }
  return out;
}
// Buscapé: produtos com a loja do menor preço
function lerBuscape(html) {
  const out = [], partes = html.split(/data-testid="product-card::card"/);
  for (let i = 1; i < partes.length; i++) {
    const antes = partes[i - 1].slice(-1500), seg = partes[i].slice(0, 6000);
    const href = (antes.match(/href="([^"]+)"/g) || []).pop()?.slice(6, -1);
    const tit = seg.match(/product-card::name"[^>]*>([^<]+)</)?.[1];
    const via = seg.match(/BestOfferMerchant[^>]*>\s*<span>([^<]+)</)?.[1] ?? "";
    const preco = valor(seg.match(/product-card::price"[^>]*>\s*<strong>([^<]+)</)?.[1]);
    if (tit && preco) out.push({ loja: lojaDoVendedor(via), titulo: ent(tit), preco, link: href ? abs(href.split("?")[0], "https://www.buscape.com.br") : "", vendedor: ent(via).replace(/^Via /, ""), via: "Buscapé" });
  }
  return out;
}
// OLX lida por um leitor de páginas (a OLX bloqueia acesso direto do servidor)
function lerOlx(md) {
  const out = [], partes = md.split(/\n## \[/);
  for (let i = 1; i < partes.length; i++) {
    const seg = partes[i].slice(0, 1500);
    const tit = seg.slice(0, seg.indexOf("]("));
    const link = seg.match(/\]\((https:\/\/[^\s)]+)/)?.[1] ?? "";
    const pr = seg.match(/\n### (R\$ ?[\d.,]+)/)?.[1] ?? seg.match(/\n(R\$ ?[\d.,]+)\n/)?.[1];
    const local = seg.match(/sem juros\n\n([^\n]+)\n/)?.[1] ?? "";
    const preco = valor(pr);
    if (tit && preco && /olx\.com\.br/.test(link)) out.push({ loja: "olx", titulo: ent(tit), preco, link, vendedor: local ? `OLX · ${local}` : "OLX" });
  }
  return out;
}

// ---------------------------------------------------------------- relevância
const ACESSORIOS = "capa capinha case pelicula protetor suporte adesivo skin cabo carregador fonte adaptador controle remoto refil peca pecas reparo conserto manual caixa vazia miniatura chaveiro decal compativel compatível replica réplica".split(" ");
const RUINS_VEIC = "sucata batido leilao leilão retirada pecas peça peças documento doc so motor só motor aluguel alugo locacao locação consorcio consórcio carta credito repasse assumir financiado parcelas miniatura brinquedo".split(" ");
const SUFIXOS = new Set("gb tb bt mm cm m l lt w v a mah hz pol kg g ml k x p hp cv cc v2 ah".split(" "));
const VARIANTES = "pro max plus ultra mini lite fe neo prime".split(" ");
export function relevante(it, q, tipo) {
  const t = " " + norm(it.titulo) + " ", tq = tokens(q), nq = " " + norm(q) + " ";
  if (!tq.length) return true;
  const comDigito = tq.filter((w) => /\d/.test(w)), resto = tq.filter((w) => !/\d/.test(w));
  const achou = (w) => t.includes(w) || t.replace(/[ -]/g, "").includes(w.replace(/-/g, ""));
  if (!comDigito.every(achou)) return false;
  // modelo diferente: "520" não é "520C", "13" não é "13 Pro"
  for (const w of comDigito) {
    for (const m of t.matchAll(new RegExp("(^|[^a-z0-9])" + w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "([a-z]+)", "g")))
      if (!SUFIXOS.has(m[2]) && !nq.includes(" " + w + m[2] + " ")) return false;
  }
  if (VARIANTES.some((v) => t.includes(" " + v + " ") && !nq.includes(" " + v + " ")) && ["eletronicos", "informatica"].includes(tipo.id)) return false;
  if (resto.length && resto.filter(achou).length / resto.length < (resto.length <= 2 ? 1 : 0.67)) return false;
  const ruins = tipo.id === "veiculo" ? RUINS_VEIC : ACESSORIOS;
  if (ruins.some((w) => t.includes(" " + norm(w) + " ") && !nq.includes(" " + norm(w) + " "))) return false;
  if (!/\busad|\brecondicion|\bvitrine|\bseminov/.test(nq) && /\b(usado|usada|recondicionado|recondicionada|vitrine|seminovo|seminova|defeito)\b/.test(t) && tipo.id !== "veiculo") return false;
  return true;
}
// tira preços muito abaixo do normal (acessório ou anúncio enganoso que passou no filtro de texto)
function semAberracao(itens, tipo) {
  if (itens.length < 4) return itens;
  const ord = itens.map((x) => x.preco).sort((a, b) => a - b), med = ord[ord.length >> 1];
  const piso = med * (tipo.id === "veiculo" ? 0.55 : 0.4);
  return itens.filter((x) => x.preco >= piso && (tipo.id !== "veiculo" || x.preco >= 2500));
}

// ---------------------------------------------------------------- busca completa
export async function buscar(q, tipoForcado, debug = false) {
  const tipo = tipoForcado ?? detectarTipo(q);
  const e = encodeURIComponent(q), veic = tipo.id === "veiculo";
  const tarefas = veic
    ? { olx: () => pegar(`https://r.jina.ai/${linkBusca("olx", q, tipo)}`, { Accept: "text/plain", "X-Return-Format": "markdown" }, 25000).then(lerOlx) }
    : {
      amazon: () => pegar(`https://www.amazon.com.br/s?k=${e}`).then(lerAmazon),
      ali: () => pegar(`https://pt.aliexpress.com/w/wholesale-${slug(q)}.html`).then(lerAli),
      bing: () => pegar(`https://www.bing.com/shop?q=${e}&setmkt=pt-BR&cc=BR`).then(lerBing),
      buscape: () => pegar(`https://www.buscape.com.br/search?q=${e}`).then(lerBuscape),
    };
  const brutos = [], falhas = {};
  await Promise.all(Object.entries(tarefas).map(async ([k, f]) => {
    try { brutos.push(...(await f())); } catch (err) { falhas[k] = String(err?.message ?? err).slice(0, 80); }
  }));
  const bons = semAberracao(brutos.filter((x) => x.preco >= 1 && relevante(x, q, tipo)), tipo).sort((a, b) => a.preco - b.preco);
  // muito abaixo do normal: avisa (em veículo, preço assim costuma ser golpe ou problema)
  if (bons.length >= 4) {
    const med = bons[bons.length >> 1].preco;
    for (const x of bons) if (x.preco < med * (veic ? 0.75 : 0.6)) x.suspeito = true;
  }
  const ids = lojasDoTipo(tipo);
  const lojas = ids.map((id) => {
    const itens = bons.filter((x) => x.loja === id);
    const motivo = id === "google" ? "O Google não deixa ler preços automaticamente."
      : id === "fb" ? "O Facebook só mostra anúncios com login."
      : id === "shopee" ? "A Shopee bloqueia leitura automática; aparece aqui quando um comparador traz oferta dela."
      : id === "ml" ? (veic ? "O Mercado Livre bloqueia leitura automática de veículos." : "Nenhuma oferta do Mercado Livre nos comparadores agora.")
      : falhas[id] ? "A loja não respondeu agora; tento de novo na próxima atualização." : "Nenhum anúncio igual ao buscado.";
    return { id, nome: LOJAS[id].nome, link: linkBusca(id, q, tipo), melhor: itens[0] ?? null, mais: itens.slice(1, 3), qtd: itens.length, motivo: itens.length ? null : motivo };
  });
  const daLista = bons.filter((x) => ids.includes(x.loja));
  const outras = bons.filter((x) => !x.loja).slice(0, 3);
  return {
    q, tipo, quando: new Date().toISOString(),
    melhor: daLista[0] ?? null, lojas, outras,
    lidas: brutos.length, relevantes: bons.length, falhas,
    ...(debug ? { amostra: brutos.slice(0, 60).map((x) => [x.loja, x.preco, x.titulo.slice(0, 80), relevante(x, q, tipo)]) } : {}),
  };
}
