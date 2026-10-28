import asyncio
import re
import json
import requests
import sys
from bs4 import BeautifulSoup
from pathlib import Path
from playwright.async_api import async_playwright

BASE_URL = "https://www.vini7xgrave.site"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

ARQ_FILA = Path("filmes_fila.txt")
ARQ_FEITAS = Path("filmes_feitos.txt")
ARQ_PENDENTES = Path("filmes_pendentes.json")
ARQ_DESCARTADOS = Path("filmes_descartados.txt")

FILMES_MORTOS = [] 
MAX_TENTATIVAS = 5

def log(*args):
    print(*args, flush=True)
    sys.stdout.flush()

if not ARQ_FILA.exists():
    log("Criando fila de filmes...")
    urls = []
    start_index = 1
    while True:
        url_feed = f"{BASE_URL}/feeds/posts/default?alt=json&max-results=150&start-index={start_index}"
        try:
            r = requests.get(url_feed, headers=HEADERS, timeout=15)
            if r.status_code != 200: break
            data = r.json()
            entries = data.get("feed", {}).get("entry", [])
            if not entries: break
            for entry in entries:
                link = next((l["href"] for l in entry.get("link", []) if l.get("rel") == "alternate"), None)
                if link: urls.append(link.split("?")[0])
            start_index += 150
            if len(entries) < 150: break
        except: break
    ARQ_FILA.write_text("\n".join(urls), encoding="utf-8")

feitas = set()
if ARQ_FEITAS.exists():
    feitas = set(ARQ_FEITAS.read_text(encoding="utf-8").splitlines())

pendentes_dict = {}
if ARQ_PENDENTES.exists():
    try:
        raw_pendentes = json.loads(ARQ_PENDENTES.read_text(encoding="utf-8"))
        for p in raw_pendentes:
            if any(morta in p.get('url', '').lower() for morta in FILMES_MORTOS): continue
            if p['arquivo'] not in pendentes_dict:
                pendentes_dict[p['arquivo']] = p
            else:
                pendentes_dict[p['arquivo']]['tentativas'] = max(
                    pendentes_dict[p['arquivo']].get('tentativas', 1),
                    p.get('tentativas', 1)
                )
    except: pass

pendentes = list(pendentes_dict.values())

fila = [u for u in ARQ_FILA.read_text(encoding="utf-8").splitlines() if u.strip() and u not in feitas]
lote = fila[:500]

log(f"Faltam {len(fila)} itens na fila. Pendentes (limpos): {len(pendentes)}.")

async def extrair_video_playwright(context, url_ep):
    page = await context.new_page()
    capturados = []
    def on_response(res):
        u = res.url
        if re.search(r"[.](mp4|m3u8)([?]|$)", u, re.I) or 'tankie' in u or 'oneplayer' in u:
            capturados.append(u)
    page.on("response", on_response)
    try:
        await page.goto(url_ep, wait_until="domcontentloaded", timeout=20000)
        try: await page.wait_for_selector("iframe", timeout=10000) 
        except: pass 
        await asyncio.sleep(3.0) 
        html = await page.content()
        if not capturados:
            soup = BeautifulSoup(html, 'html.parser')
            for iframe in soup.find_all('iframe'):
                src = iframe.get('src', '')
                if 'google' not in src.lower() and 'ads' not in src.lower():
                    capturados.append(src)
        if not capturados:
            match = re.search(r'(https?://[^"\']+(?:tankie|oneplayer)[^"\']+)', html)
            if match: capturados.append(match.group(1))
    except Exception: pass
    finally: await page.close()
    if capturados: return list(dict.fromkeys(capturados))[0]
    return None

def limpar_titulo_pagina(soup_title):
    if not soup_title: return "Filme Desconhecido"
    titulo = re.sub(r'^.*?-\s*', '', soup_title)
    titulo = re.sub(r'-\s*viniseries.*$', '', titulo, flags=re.I)
    titulo = titulo.split('-')[0].strip()
    # Remove o ano do final do título para não duplicar com o que vamos adicionar
    return re.sub(r'\s*\(\d{4}\)$', '', titulo).strip()

def salvar_json(nome_arquivo, nome_json, link_video):
    dados = {
        "@context": "https://schema.org", "@type": "VideoObject",
        "name": nome_json, "description": f"Assista {nome_json}",
        "thumbnailUrl": ["https://via.placeholder.com/500x750?text=Sem+Capa"],
        "uploadDate": "2020-01-01T00:00:00+00:00", "inLanguage": "pt",
        "contentUrl": link_video, "embedUrl": link_video
    }
    json_str = json.dumps(dados, ensure_ascii=False, indent=2)
    html = f"<!DOCTYPE html>\n<html lang=\"pt-BR\">\n<head>\n<script type=\"application/ld+json\">\n{json_str}\n</script>\n<title>{nome_json}</title>\n</head>\n<body>\n<h1>{nome_json}</h1>\n</body>\n</html>"
    Path(nome_arquivo).write_text(html, encoding='utf-8')

async def processar_item(context, url_pagina):
    if any(morta in url_pagina.lower() for morta in FILMES_MORTOS):
        log(f"\n--> [BYPASS] Ignorando filme morto: {url_pagina}")
        with open(ARQ_FEITAS, "a", encoding="utf-8") as f:
            f.write(url_pagina + "\n")
        return

    log(f"\n--> Verificando: {url_pagina}")
    try:
        r = await asyncio.to_thread(requests.get, url_pagina, headers=HEADERS, timeout=20)
        soup = BeautifulSoup(r.text, 'html.parser')
        
        # Verifica se é série
        tem_episodio = any('episódio' in tag.get_text().lower() for tag in soup.find_all('a'))
        if tem_episodio:
            log(f"    (É uma série. Pulando...)")
            with open(ARQ_FEITAS, "a", encoding="utf-8") as f:
                f.write(url_pagina + "\n")
            return

        titulo_filme = limpar_titulo_pagina(soup.title.text if soup.title else "")
        
        # --- AQUI ESTÁ A CORREÇÃO DO ANO ---
        # Tenta achar um ano de 4 dígitos (1900 a 2099) na URL
        match_ano = re.search(r'\b(19|20)\d{2}\b', url_pagina)
        ano = match_ano.group(0) if match_ano else ""
        
        slug = re.sub(r'[^a-z0-9]', '_', titulo_filme.lower())
        slug = re.sub(r'_+', '_', slug).strip('_')
        
        # Se achou o ano, adiciona no nome do arquivo e no título
        if ano:
            nome_arquivo = f"{slug}_{ano}.json"
            nome_json_final = f"{titulo_filme} ({ano}) - 🍿Clau"
        else:
            nome_arquivo = f"{slug}.json"
            nome_json_final = f"{titulo_filme} - 🍿Clau"
        # -----------------------------------

        with open(ARQ_FEITAS, "a", encoding="utf-8") as f:
            f.write(url_pagina + "\n")

        if Path(nome_arquivo).exists(): 
            log(f"    (Já existe: {nome_arquivo})")
            return

        log(f"    É um filme: '{nome_json_final}'.")
        link_video = await extrair_video_playwright(context, url_pagina)
        
        if not link_video: 
            log(f"      [-] Falhou. Adicionando à fila de pendentes.")
            ja_existe = any(p['arquivo'] == nome_arquivo for p in pendentes)
            if not ja_existe:
                pendentes.append({
                    "arquivo": nome_arquivo,
                    "nome_json": nome_json_final,
                    "url": url_pagina,
                    "tentativas": 1
                })
            return
            
        salvar_json(nome_arquivo, nome_json_final, link_video)
        log(f"      [+] Salvo: {nome_arquivo}")
            
    except Exception as e:
        log(f"    Erro na URL {url_pagina}: {e}")

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=HEADERS["User-Agent"])
        
        for url in lote:
            await processar_item(context, url)

        if pendentes:
            log(f"\n=== TENTANDO NOVAMENTE {len(pendentes)} FILMES PENDENTES ===")
            ainda_pendentes = []
            for item in pendentes:
                if Path(item['arquivo']).exists(): continue
                if any(morta in item.get('url', '').lower() for morta in FILMES_MORTOS): continue
                
                if item.get("tentativas", 0) >= MAX_TENTATIVAS:
                    log(f"--> [DESISTINDO E SALVANDO NO TXT] {item['arquivo']}")
                    with open(ARQ_DESCARTADOS, "a", encoding="utf-8") as f_desc:
                        f_desc.write(f"{item['arquivo']}\t{item['url']}\t{item.get('tentativas')} falhas\n")
                    continue

                log(f"--> Tentando ({item.get('tentativas', 1)}/{MAX_TENTATIVAS}): {item['arquivo']}")
                link_video = await extrair_video_playwright(context, item['url'])
                if link_video:
                    salvar_json(item['arquivo'], item['nome_json'], link_video)
                    log(f"    [+] SUCESSO AO RETENTAR: {item['arquivo']}")
                else:
                    log(f"    [-] Ainda falhando: {item['arquivo']}")
                    item["tentativas"] = item.get("tentativas", 1) + 1
                    ainda_pendentes.append(item)
            pendentes.clear()
            pendentes.extend(ainda_pendentes)

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
    ARQ_PENDENTES.write_text(json.dumps(pendentes, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"\nProgresso salvo. {len(pendentes)} filmes pendentes.")
