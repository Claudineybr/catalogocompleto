import requests
import re
import json
from bs4 import BeautifulSoup
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

# Vamos ler o seu catálogo para achar as séries que já temos
# (Aqui eu chuto que o seu catalogo_completo.txt ou o csv tenha os links das séries)
# Para não perder tempo, vamos varrer os arquivos que já existem e ver se o link da página original tá lá.

# Como não temos o arquivo com os links das séries, vamos usar as URLs fixas do site do print
# E na vida real, a gente pode puxar do seu catalogo_completo.txt se ele ainda existir.

series_para_verificar = [
    "https://www.vini7xgrave.site/2025/09/inix-arqueiro-verde-arrow-2012.html",
    # Adicione outras séries aqui se quiser
]

HEADERS = {"User-Agent": "Mozilla/5.0"}

def extrair_serie(url_pagina):
    try:
        r = requests.get(url_pagina, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, 'html.parser')
        
        temporada_atual = 1
        episodios = []
        
        # O site do Blogger coloca os títulos e links dentro de tags <b>, <h2> ou <div>
        # Vamos varrer o texto da página inteira
        for tag in soup.find_all(['b', 'h2', 'h3', 'div', 'p']):
            texto = tag.get_text(strip=True)
            
            # Encontra o título da temporada (ex: "Arqueiro Verde - 2ª Temporada")
            match_temp = re.search(r'(\d+)ª\s*Temporada', texto, re.I)
            if match_temp:
                temporada_atual = int(match_temp.group(1))
                continue
                
            # Se a tag for um link e tiver "Episódio", extrai
            if tag.name == 'a' and 'episódio' in texto.lower():
                href = tag.get('href')
                if href:
                    # Se o link for relativo, completa
                    if href.startswith('/'):
                        href = "https://www.vini7xgrave.site" + href
                        
                    # Limpa o título do episódio
                    titulo_ep = texto.replace('Episódio', '').strip()
                    
                    episodios.append({
                        'temporada': temporada_atual,
                        'titulo': titulo_ep,
                        'url_pagina_ep': href
                    })
                    
        return episodios
    except Exception as e:
        print(f"Erro ao ler a página {url_pagina}: {e}")
        return []

def extrair_video_ep(url_ep):
    try:
        r = requests.get(url_ep, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, 'html.parser')
        
        # Procura o iframe do player
        iframe = soup.find('iframe')
        if iframe and iframe.get('src'):
            return iframe.get('src')
        return None
    except Exception:
        return None

print("Iniciando varredura das séries...")

# 1. Pega todos os episódios de todas as temporadas
todos_episodios = []
for url in series_para_verificar:
    eps = extrair_serie(url)
    todos_episodios.extend(eps)

print(f"Encontrados {len(todos_episodios)} episódios no total.")

# 2. Para cada episódio, pega o link do vídeo e cria o JSON
cont = 0
for ep in todos_episodios:
    link_video = extrair_video_ep(ep['url_pagina_ep'])
    if not link_video:
        continue
        
    # Monta o nome igual o app gosta
    nome_limpo = ep['titulo'].replace(' - ', ' - ').strip()
    nome_json = f"Arqueiro Verde (Arrow) - T{ep['temporada']}E{ep['titulo'].split('-')[0].strip()} - {nome_limpo} - 🍿Clau"
    
    # Gera o JSON
    dados = {
        "@context": "https://schema.org",
        "@type": "VideoObject",
        "name": nome_json,
        "description": f"Assista {nome_json}",
        "thumbnailUrl": ["https://via.placeholder.com/500x750?text=Sem+Capa"],
        "uploadDate": "2012-01-01T00:00:00+00:00",
        "inLanguage": "pt",
        "contentUrl": link_video,
        "embedUrl": link_video
    }
    
    json_str = json.dumps(dados, ensure_ascii=False, indent=2)
    html = f"<!DOCTYPE html>\n<html lang=\"pt-BR\">\n<head>\n<script type=\"application/ld+json\">\n{json_str}\n</script>\n<title>{nome_json}</title>\n</head>\n<body>\n<h1>{nome_json}</h1>\n</body>\n</html>"
    
    # Salva o arquivo
    nome_arquivo = f"arrow_t{ep['temporada']}e{cont}.json"
    Path(nome_arquivo).write_text(html, encoding='utf-8')
    cont += 1
    print(f"Salvo: {nome_arquivo}")

print(f"Concluído! {cont} arquivos gerados.")
