import asyncio
import re
import json
import requests
from bs4 import BeautifulSoup
from pathlib import Path
from playwright.async_api import async_playwright

BASE_URL = "https://www.vini7xgrave.site"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

ARQ_FILA = Path("series_fila.txt")
ARQ_FEITAS = Path("series_feitas.txt")

if not ARQ_FILA.exists():
    print("Criando fila...", flush=True)
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

fila = [u for u in ARQ_FILA.read_text(encoding="utf-8").splitlines() if u.strip() and u not in feitas]

lote = fila[:300]

if not lote:
    print("Todas as séries da fila já foram processadas!", flush=True)
    exit(0)

print(f"Iniciando lote de 300 URLs. Faltam {len(fila)} no total.", flush=True)

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
    if not soup_title:
        return "Serie Desconhecida"
    titulo = re.sub(r'^.*?-\s*', '', soup_title)
    titulo = re.sub(r'-\s*viniseries.*$', '', titulo, flags=re.I)
    titulo = titulo.split('-')[0].strip()
    titulo = re.sub(r'\s*\d{4}$', '', titulo).strip()
    return titulo if titulo else "Serie Desconhecida"

async def processar_serie(context, url_serie):
    print(f"\n--> Verificando: {url_serie}", flush=True)
    try:
        r = requests.get(url_serie, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, 'html.parser')
        
        titulo_serie = limpar_titulo_pagina(soup.title.text if soup.title else "")
        slug = re.sub(r'[^a-z0-9]', '_', titulo_serie.lower())
        slug = re.sub(r'_+', '_', slug).strip('_')
        
        temporada_atual = 1
        episodios = []
        
        for tag in soup.find_all(['b', 'h2', 'h3', 'p', 'a', 'div']):
            texto = tag.get_text(strip=True)
            match_temp = re.search(r'(\d+)\s*[ªº]\s*Temporada', texto, re.I)
            if match_temp:
                temporada_atual = int(match_temp.group(1))
                continue
            if tag.name == 'a' and 'episódio' in texto.lower():
                href = tag.get('href')
                if href:
                    if href.startswith('/'): href = BASE_URL + href
                    match_ep = re.search(r'Episódio\s*(\d+)', texto, re.I)
                    num_ep = match_ep.group(1) if match_ep else "0"
                    titulo_limpo = re.sub(r'Episódio\s*\d+\s*-?\s*', '', texto, flags=re.I).strip()
                    episodios.append({'temp': temporada_atual, 'ep': num_ep, 'titulo': titulo_limpo, 'url': href})
                    
        if not episodios:
            print(f"    (É um filme. Pulando...)", flush=True)
            return

        print(f"    Encontrados {len(episodios)} episódios de '{titulo_serie}'.", flush=True)
        
        falhas = 0
        for item in episodios:
            nome_arquivo = f"{slug}_t{item['temp']}e{item['ep']}.json"
            if Path(nome_arquivo).exists(): continue
                
            link_video = await extrair_video_playwright(context, item['url'])
            if not link_video: 
                print(f"      [-] Falhou: {nome_arquivo}", flush=True)
                falhas += 1
                continue
                
            nome_json = f"{titulo_serie} - T{item['temp']}E{item['ep']} - {item['titulo']} - 🍿Clau"
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
            print(f"      [+] Salvo: {nome_arquivo}", flush=True)
        
        if falhas == 0:
            with open(ARQ_FEITAS, "a", encoding="utf-8") as f:
                f.write(url_serie + "\n")
            print(f"    Série '{titulo_serie}' completa e marcada como feita.", flush=True)
        else:
            print(f"    Série '{titulo_serie}' teve {falhas} falhas. Não será marcada como feita.", flush=True)
            
    except Exception as e:
        print(f"    Erro na URL {url_serie}: {e}", flush=True)

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=HEADERS["User-Agent"])
        for url in lote:
            await processar_serie(context, url)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
