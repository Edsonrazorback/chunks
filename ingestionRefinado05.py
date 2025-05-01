import re
import json
import logging
from typing import List, Dict, Tuple, Optional, Any

# --- Configuração do Logging ---
# Configura o logging para exibir mensagens informativas.
# O formato inclui timestamp, nível da mensagem e a própria mensagem.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler() # Envia logs para o console
        # logging.FileHandler("processamento_decreto.log") # Descomente para salvar logs em arquivo
    ]
)

# --- Constantes ---
# Define constantes para nomes de arquivos e parâmetros, facilitando a modificação.
INPUT_MARKDOWN_FILE = "D23569.md"
OUTPUT_STRUCTURE_FILE = "estrutura_documento.json"
OUTPUT_CHUNKS_FILE = "decreto_chunks_metadados.json"
CHUNK_SIZE = 1500 # Tamanho alvo para cada chunk (em caracteres)
CHUNK_OVERLAP = 200 # Sobreposição entre chunks consecutivos
MAX_CHUNKS = 500 # Limite de segurança para evitar loops infinitos no chunking
MIN_CHUNK_ADVANCE = 50 # Avanço mínimo garantido a cada iteração do chunking

# --- Funções de Limpeza ---

def remover_padroes_repetidos(texto: str) -> str:
    """Remove blocos de texto repetitivos (links, datas, rodapés)."""
    # Padrão para remover o bloco de link/data/nome do arquivo
    # Mais robusto para diferentes espaçamentos e presença opcional de 'D23569'
    padrao_rodape = r"^\s*https?://www\.planalto\.gov\.br/ccivil_03/decreto/1930-1949/d23569\.htm\s*---\s*\d{1,2}/\d{1,2}/\d{4},\s*\d{1,2}:\d{2}(?:\s+D23569)?\s*$"
    texto = re.sub(padrao_rodape, "", texto, flags=re.MULTILINE | re.IGNORECASE)

    # Remover linha "Link para o Decreto" e separador ---
    texto = re.sub(r"^\s*Link para o Decreto\s*---\s*$", "", texto, flags=re.MULTILINE | re.IGNORECASE)

    # Remover texto após a assinatura final (ajustar se necessário)
    assinatura_final = "GETULIO VARGAS." # Ponto de referência
    indice_assinatura = texto.rfind(assinatura_final)
    if indice_assinatura != -1:
        # Encontra a próxima quebra de linha após a assinatura para cortar
        proxima_quebra = texto.find('\n', indice_assinatura)
        if proxima_quebra != -1:
            texto = texto[:proxima_quebra]
        else: # Se for a última linha
             texto = texto[:indice_assinatura + len(assinatura_final)]

    # Remover nota sobre substituição do DOU no final
    texto = re.sub(r"Este texto não substitui o publicado.*$", "", texto, flags=re.IGNORECASE | re.DOTALL).strip()

    return texto

def normalizar_espacos_quebras(texto: str) -> str:
    """Normaliza espaços em branco e quebras de linha."""
    # Remover espaços extras no início/fim das linhas
    linhas = [line.strip() for line in texto.splitlines()]
    # Remover linhas completamente vazias resultantes do strip
    linhas = [line for line in linhas if line]
    texto = "\n".join(linhas)
    # Normalizar multiplas quebras de linha para no máximo duas (um parágrafo em branco)
    texto = re.sub(r'\n{3,}', '\n\n', texto)
    # Opcional: Normalizar espaços múltiplos entre palavras
    # texto = re.sub(r'[ \t]+', ' ', texto)
    return texto

def remover_anotacoes_parenteticas(texto: str) -> str:
    """Remove anotações como (Vide...), (Redação...), (Revogado...)."""
    # Remove parênteses que contenham palavras-chave comuns em anotações legais
    padrao_anotacao = r'\((?:Vide|Redação dada|Revogado)[^)]*\)\s*'
    texto = re.sub(padrao_anotacao, '', texto, flags=re.IGNORECASE)
    return texto

def limpar_texto_markdown(texto_bruto: str) -> str:
    """Função principal de limpeza que aplica várias etapas."""
    logging.debug("Iniciando limpeza do texto Markdown.")
    texto = remover_padroes_repetidos(texto_bruto)
    texto = remover_anotacoes_parenteticas(texto) # Aplicar antes da normalização de espaços
    texto = normalizar_espacos_quebras(texto)
    logging.debug("Limpeza do texto Markdown concluída.")
    return texto

# --- Funções de Extração de Metadados ---

# Pré-compila regex para performance
RE_DECRETO_NUM = re.compile(r"DECRETO Nº ([^\n]+)")
RE_LINK = re.compile(r"(https://www\.planalto\.gov\.br/[^\s]+)")
RE_CAPITULO = re.compile(r"^#+ CAPÍTULO ([IVXLCDM]+)\b(.*)", re.MULTILINE) # Captura número e título opcional
RE_ARTIGO = re.compile(r"^(?:#+\s*)?Art\.?\s*(\d+[\.\ºª]?)", re.MULTILINE | re.IGNORECASE) # Mais flexível com Art. Artº Artª etc.

def extrair_metadados_decreto(texto: str) -> Dict[str, Any]:
    """Extrai metadados estruturais (número, link, capítulos, artigos) do texto."""
    logging.debug("Iniciando extração de metadados.")
    # Extrair informações básicas
    match_num = RE_DECRETO_NUM.search(texto)
    decreto_num = match_num.group(1).strip() if match_num else "N/A"

    match_link = RE_LINK.search(texto)
    link_documento = match_link.group(1).strip() if match_link else "N/A"

    # Extrair estrutura de capítulos e artigos
    capitulos: Dict[str, Dict[str, Any]] = {}
    artigos_posicoes: List[Tuple[int, str, str]] = [] # (pos_inicio, cap_num, art_num)
    capitulo_atual_num = None
    capitulo_atual_titulo = ""

    # Primeira passada para encontrar capítulos e artigos com suas posições
    for match_cap in RE_CAPITULO.finditer(texto):
        cap_num = match_cap.group(1).strip()
        cap_titulo = match_cap.group(2).strip().lstrip('- ') # Pega o título opcional
        capitulo_atual_num = cap_num
        capitulo_atual_titulo = cap_titulo
        if cap_num not in capitulos:
             capitulos[cap_num] = {"titulo": cap_titulo, "artigos": [], "pos_inicio": match_cap.start()}

    for match_art in RE_ARTIGO.finditer(texto):
        art_num_raw = match_art.group(1).strip()
        # Normaliza o número do artigo (remove ., º, ª)
        art_num_norm = re.sub(r"[\.ºª]$", "", art_num_raw)
        art_label = f"Art. {art_num_norm}" # Cria um label consistente

        # Encontra a qual capítulo este artigo pertence baseado na posição
        cap_pertencente = None
        menor_distancia = float('inf')
        for num, data in capitulos.items():
            distancia = match_art.start() - data["pos_inicio"]
            if 0 <= distancia < menor_distancia:
                 menor_distancia = distancia
                 cap_pertencente = num

        if cap_pertencente:
            if art_label not in capitulos[cap_pertencente]["artigos"]:
                capitulos[cap_pertencente]["artigos"].append(art_label)
            artigos_posicoes.append((match_art.start(), cap_pertencente, art_label))
        else:
             logging.warning(f"Artigo '{art_label}' encontrado na posição {match_art.start()} mas não foi possível associar a um capítulo.")

    # Ordena artigos dentro de cada capítulo (opcional, mas bom para consistência)
    for cap_data in capitulos.values():
        cap_data["artigos"].sort(key=lambda x: int(re.search(r'\d+', x).group()))

    metadados = {
        "documento": {
            "tipo": "Decreto",
            "numero": decreto_num,
            "link_oficial": link_documento,
        },
        "estrutura": capitulos,
        "_artigos_posicoes": sorted(artigos_posicoes) # Guarda posições para chunking contextual
    }
    logging.debug(f"Metadados extraídos: {len(capitulos)} capítulos.")
    return metadados

# --- Funções de Chunking ---

def encontrar_melhor_corte(texto: str, pos_inicial: int, tamanho_max: int) -> int:
    """Tenta encontrar um bom ponto de corte (fim de frase, parágrafo) perto do tamanho máximo."""
    pos_final_ideal = pos_inicial + tamanho_max
    if pos_final_ideal >= len(texto):
        return len(texto)

    # Procurar por fim de parágrafo (duas quebras) ou fim de frase (.) perto do ideal
    melhor_corte = pos_final_ideal
    indices_corte = []

    # Fim de parágrafo (prioridade maior)
    for match in re.finditer(r"\n\n", texto[pos_inicial:min(len(texto), pos_final_ideal + 100)]):
         indices_corte.append(pos_inicial + match.start() + 2) # Inclui as quebras

    # Fim de frase (prioridade menor)
    for match in re.finditer(r"\.\s", texto[pos_inicial:min(len(texto), pos_final_ideal + 100)]):
         indices_corte.append(pos_inicial + match.start() + 1) # Inclui o ponto

    if indices_corte:
         # Escolhe o corte mais próximo do ideal, mas que não seja muito pequeno
         candidatos_validos = [c for c in indices_corte if c > pos_inicial + tamanho_max * 0.7] # Evita chunks muito curtos
         if candidatos_validos:
              melhor_corte = min(candidatos_validos, key=lambda c: abs(c - pos_final_ideal))
         else: # Se nenhum for bom, usa o corte mais próximo possível
             melhor_corte = min(indices_corte, key=lambda c: abs(c - pos_final_ideal))

    # Garante que o corte não ultrapasse o limite do texto
    return min(melhor_corte, len(texto))


def criar_chunks_texto(texto: str, tamanho_chunk: int, sobreposicao: int, max_chunks: int, avanco_minimo: int) -> List[str]:
    """Divide o texto em chunks com sobreposição e lógica de corte aprimorada."""
    logging.debug(f"Iniciando chunking: tamanho={tamanho_chunk}, sobreposicao={sobreposicao}")
    chunks = []
    posicao_atual = 0
    contador_chunks = 0

    while posicao_atual < len(texto) and contador_chunks < max_chunks:
        fim_chunk = encontrar_melhor_corte(texto, posicao_atual, tamanho_chunk)
        chunk = texto[posicao_atual:fim_chunk].strip()

        if chunk: # Só adiciona se não estiver vazio
            chunks.append(chunk)
            contador_chunks += 1
            if contador_chunks % 50 == 0:
                 logging.debug(f"Criados {contador_chunks} chunks...")

        # Calcula próximo início com sobreposição, garantindo avanço mínimo
        proximo_inicio = fim_chunk - sobreposicao
        # Garante que o avanço seja de pelo menos 'avanco_minimo' caracteres
        proximo_inicio = max(proximo_inicio, posicao_atual + avanco_minimo)
        # Garante que não fiquemos presos no mesmo lugar
        if proximo_inicio <= posicao_atual:
             proximo_inicio = posicao_atual + avanco_minimo

        # Condição de parada para evitar loop infinito no final
        if proximo_inicio >= len(texto):
            break

        posicao_atual = proximo_inicio

    if contador_chunks >= max_chunks:
         logging.warning(f"Atingido o limite máximo de {max_chunks} chunks.")

    logging.debug(f"Chunking concluído. Total de {len(chunks)} chunks.")
    return chunks

# --- Função de Associação de Metadados ---

def associar_metadados_aos_chunks(
    chunks: List[str],
    metadados_gerais: Dict[str, Any],
    texto_completo: str
) -> List[Dict[str, Any]]:
    """Associa metadados contextuais a cada chunk."""
    logging.debug("Iniciando associação de metadados aos chunks.")
    chunks_com_metadados = []
    posicao_texto = 0 # Rastreia a posição no texto original

    artigos_pos = metadados_gerais.get("_artigos_posicoes", [])
    idx_artigo_atual = 0

    for i, chunk in enumerate(chunks):
        # Encontra a posição real do chunk no texto original (aproximado devido ao strip/overlap)
        # Para uma associação precisa, seria ideal guardar o start/end original de cada chunk
        # Aqui, faremos uma busca simples, pode não ser perfeita com overlaps grandes
        inicio_chunk_original = texto_completo.find(chunk[:50], posicao_texto) # Busca início do chunk
        if inicio_chunk_original == -1:
             inicio_chunk_original = posicao_texto # Fallback
        fim_chunk_original = inicio_chunk_original + len(chunk)
        posicao_texto = inicio_chunk_original + MIN_CHUNK_ADVANCE # Avança a busca para o próximo

        # Encontra o capítulo e artigo "ativos" no início do chunk
        capitulo_ativo = None
        artigo_ativo = None

        # Itera pelas posições dos artigos ordenadas
        temp_idx = idx_artigo_atual
        while temp_idx < len(artigos_pos):
            pos_art, cap_num, art_num = artigos_pos[temp_idx]
            if pos_art <= inicio_chunk_original:
                capitulo_ativo = cap_num
                artigo_ativo = art_num
                idx_artigo_atual = temp_idx # Atualiza o índice para otimizar próxima busca
                temp_idx += 1
            else:
                 break # Já passou da posição do chunk

        # Monta os metadados para este chunk
        meta_chunk = {
            "documento": metadados_gerais["documento"],
            "estrutura_contextual": {}
        }
        if capitulo_ativo and artigo_ativo:
            meta_chunk["estrutura_contextual"] = {
                 "capitulo_ativo": capitulo_ativo,
                 "titulo_capitulo": metadados_gerais["estrutura"].get(capitulo_ativo, {}).get("titulo", ""),
                 "artigo_ativo": artigo_ativo
            }
        elif capitulo_ativo: # Se só achou capítulo (ex: chunk começa entre o título do cap e o 1º art)
             meta_chunk["estrutura_contextual"] = {
                 "capitulo_ativo": capitulo_ativo,
                 "titulo_capitulo": metadados_gerais["estrutura"].get(capitulo_ativo, {}).get("titulo", ""),
                 "artigo_ativo": None
            }


        chunks_com_metadados.append({
            "id": i,
            "texto": chunk,
            "metadados": meta_chunk,
            # "_debug_pos": (inicio_chunk_original, fim_chunk_original) # Para depuração
        })

    logging.debug("Associação de metadados concluída.")
    return chunks_com_metadados


# --- Bloco Principal de Execução ---

def main():
    """Função principal que orquestra o processo."""
    try:
        # Carregar o arquivo
        logging.info(f"Carregando arquivo: {INPUT_MARKDOWN_FILE}")
        with open(INPUT_MARKDOWN_FILE, "r", encoding="utf-8") as arquivo:
            texto_decreto_bruto = arquivo.read()
        logging.info(f"Arquivo carregado: {len(texto_decreto_bruto)} caracteres")

        # Limpar o texto
        texto_decreto = limpar_texto_markdown(texto_decreto_bruto)
        logging.info(f"Texto limpo: {len(texto_decreto)} caracteres")
        # Optional: Save cleaned text for inspection
        # with open("D23569_limpo.md", "w", encoding="utf-8") as f_limpo:
        #     f_limpo.write(texto_decreto)

        # Extrair metadados estruturais
        logging.info("Extraindo metadados estruturais...")
        metadados = extrair_metadados_decreto(texto_decreto)

        # Salvar a estrutura geral (similar ao Filtro.jpg)
        logging.info(f"Salvando estrutura geral em {OUTPUT_STRUCTURE_FILE}...")
        # Remove a chave interna _artigos_posicoes antes de salvar
        estrutura_para_salvar = {k: v for k, v in metadados.items() if k != "_artigos_posicoes"}
        with open(OUTPUT_STRUCTURE_FILE, "w", encoding="utf-8") as f_meta:
            json.dump(estrutura_para_salvar, f_meta, indent=2, ensure_ascii=False)
        logging.info("Estrutura geral salva.")

        # Criar chunks
        logging.info("Criando chunks...")
        chunks = criar_chunks_texto(
            texto_decreto, CHUNK_SIZE, CHUNK_OVERLAP, MAX_CHUNKS, MIN_CHUNK_ADVANCE
        )
        logging.info(f"Total de {len(chunks)} chunks criados.")

        # Associar metadados aos chunks
        logging.info("Associando metadados contextuais aos chunks...")
        chunks_com_metadados = associar_metadados_aos_chunks(chunks, metadados, texto_decreto)

        # Salvar o resultado final dos chunks com metadados
        logging.info(f"Salvando resultado final em {OUTPUT_CHUNKS_FILE}...")
        with open(OUTPUT_CHUNKS_FILE, "w", encoding="utf-8") as f_out:
            json.dump(chunks_com_metadados, f_out, indent=2, ensure_ascii=False)

        logging.info(
            f"Processamento concluído! Arquivo '{OUTPUT_CHUNKS_FILE}' criado com {len(chunks_com_metadados)} chunks."
        )

    except FileNotFoundError:
        logging.error(f"Erro Crítico: Arquivo de entrada '{INPUT_MARKDOWN_FILE}' não encontrado.")
    except Exception as e:
        logging.exception(f"Erro inesperado durante o processamento: {e}") # Loga o traceback completo

if __name__ == "__main__":
    main()