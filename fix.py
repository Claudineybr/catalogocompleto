import json
import re
from pathlib import Path

def corrigir(caminho):
    try:
        txt = caminho.read_text(encoding='utf-8-sig')
        if txt.strip().lower().startswith('<!doctype'):
            match = re.search(r'<script type="application/ld\+json">(.*?)</script>', txt, re.S)
            if not match: return False
            txt = match.group(1)
        
        dados = json.loads(txt)
        
        # 1. Remove os campos que confundiram o Rave
        for campo in ['episodeNumber', 'partOfSeason', 'partOfSeries']:
            if campo in dados:
                del dados[campo]
                
        # 2. Força o tipo correto
        dados['@type'] = "VideoObject"
        
        # 3. Atualiza a descrição
        nome = dados.get('name', 'Sem Nome')
        dados['description'] = f"Assista {nome}"
        
        capa = dados.get('thumbnailUrl', [''])[0]
        if not capa:
            capa = 'https://via.placeholder.com/500x750?text=Sem+Capa'
        
        # 4. MUITO IMPORTANTE: indent=2 para o JSON ter quebras de linha e espaços
        json_final = json.dumps(dados, ensure_ascii=False, indent=2)
        
        # 5. Monta o HTML exatamente igual ao que funcionava
        html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<script type="application/ld+json">
{json_final}
</script>
<title>{nome}</title>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
</head>
<body>
<img src="{capa}" alt="{nome}" style="width:100%;max-height:220px;object-fit:cover;border-radius:8px">
<h1>{nome}</h1>
</body>
</html>"""
        
        caminho.write_text(html, encoding='utf-8')
        return True
    except Exception as e:
        print(f"Erro em {caminho.name}: {e}")
        return False

print("Corrigindo arquivos...")
cont = 0
for arq in Path('.').glob('*.json'):
    if corrigir(arq):
        cont += 1
print(f"Total corrigido: {cont}")
