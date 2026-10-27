import json
import re
import os
from pathlib import Path

# Carrega a lista de links ruins
ruins = set()
if Path("links_ruins.txt").exists():
    with open("links_ruins.txt", "r", encoding="utf-8-sig") as f:
        for linha in f:
            partes = linha.strip().split("\t")
            if len(partes) >= 2:
                ruins.add(partes[1].strip()) # Pega a URL

print(f"Links ruins carregados: {len(ruins)}")

deletados = 0
for arq in Path('.').glob('*.json'):
    try:
        texto = arq.read_text(encoding='utf-8-sig')
        
        # Extrai o link de dentro do JSON (que está dentro do HTML)
        match = re.search(r'<script type="application/ld\+json">(.*?)</script>', texto, re.S)
        if match:
            dados = json.loads(match.group(1))
        else:
            dados = json.loads(texto)
            
        url_video = dados.get("contentUrl", "").strip()
        
        # Se o link estiver na lista de ruins, apaga o arquivo
        if url_video in ruins:
            arq.unlink()
            deletados += 1
            
    except Exception:
        pass

print(f"Total de arquivos apagados: {deletados}")
