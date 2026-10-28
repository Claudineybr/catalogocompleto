import json
import re
import os
from pathlib import Path

def gerar_nome_bonito(nome_completo, nome_antigo):
    # Remove a marca d'água
    nome = nome_completo.replace(" - 🍿Clau", "").replace(" - Clau", "").strip()
    
    # Verifica se é episódio (T1E2)
    match_ep = re.search(r'^(.*?)\s*-\s*T(\d+)E(\d+)', nome, re.I)
    if match_ep:
        serie = match_ep.group(1).strip()
        temp = match_ep.group(2)
        ep = match_ep.group(3)
        # Limpa o nome da série (tira acentos, espaços, etc)
        serie_slug = re.sub(r'[^a-z0-9]', '_', serie.lower())
        serie_slug = re.sub(r'_+', '_', serie_slug).strip('_')
        return f"{serie_slug}_t{temp}e{ep}.json"
        
    # Se for filme
    # Tenta remover o ano do final para ficar limpo
    nome_filme = re.sub(r'\s*\(\d{4}\)', '', nome).strip()
    filme_slug = re.sub(r'[^a-z0-9]', '_', nome_filme.lower())
    filme_slug = re.sub(r'_+', '_', filme_slug).strip('_')
    
    # Se o slug ficou vazio, usa o nome antigo
    if not filme_slug:
        return nome_antigo
        
    return f"{filme_slug}.json"

arquivos = list(Path('.').glob('*.json'))
print(f"Verificando {len(arquivos)} arquivos...")

renomeados = 0

for arq in arquivos:
    try:
        texto = arq.read_text(encoding='utf-8-sig')
        
        # Pega o JSON
        match = re.search(r'<script type="application/ld\+json">(.*?)</script>', texto, re.S)
        if match:
            dados = json.loads(match.group(1))
        else:
            dados = json.loads(texto)
            
        nome_completo = dados.get("name", "")
        if not nome_completo:
            continue
            
        novo_nome = gerar_nome_bonito(nome_completo, arq.name)
        
        if novo_nome != arq.name:
            # Se o nome já existe (dois filmes com mesmo nome), adiciona um número
            contador = 1
            nome_final = novo_nome
            while Path(nome_final).exists() and nome_final != arq.name:
                nome_final = novo_nome.replace(".json", f"_{contador}.json")
                contador += 1
                
            if nome_final != arq.name:
                os.rename(arq, nome_final)
                renomeados += 1
                
    except Exception as e:
        pass

print(f"Concluído! {renomeados} arquivos renomeados.")
