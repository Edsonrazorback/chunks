# chunks
TécnicadeChunks

**Principais Melhorias e Explicações neste Código Refinado:**

1.  **Limpeza Mais Agressiva (`limpar_texto_markdown`)**:
    * Funções separadas para cada tipo de limpeza (`remover_padroes_repetidos`, `normalizar_espacos_quebras`, `remover_anotacoes_parenteticas`).
    * Remove também as anotações como `(Vide Decreto...)` que estavam no texto.
    * Tenta remover o bloco de assinatura e notas do DOU no final de forma mais robusta.
    * Normaliza espaços e quebras de linha de forma mais consistente.

2.  **Extração de Metadados Aprimorada (`extrair_metadados_decreto`)**:
    * Pré-compila todas as expressões regulares usadas para melhor performance.
    * Tenta capturar o *título* do capítulo junto com o número (`RE_CAPITULO`).
    * Usa uma abordagem baseada na *posição* no texto para associar artigos a capítulos, o que é mais robusto que depender da ordem exata das linhas.
    * Guarda as posições de início dos artigos (`_artigos_posicoes`) para ajudar na associação contextual aos chunks posteriormente.
    * Normaliza os números dos artigos (`Art. X.`, `Art. Xº` -> `Art. X`) para consistência.

3.  **Chunking Mais Inteligente (`criar_chunks_texto`, `encontrar_melhor_corte`)**:
    * A função `encontrar_melhor_corte` tenta achar finais de parágrafo (`\n\n`) ou de frase (`. `) próximos ao tamanho desejado, priorizando o fim de parágrafo. Isso ajuda a manter a coesão do texto dentro do chunk.
    * Adiciona verificações para evitar chunks muito curtos ou ficar preso no mesmo lugar.

4.  **Associação Contextual de Metadados (`associar_metadados_aos_chunks`)**:
    * **Importante:** Esta função agora tenta determinar qual capítulo/artigo estava "ativo" (foi o último declarado) no *início* de cada chunk, usando as posições salvas em `_artigos_posicoes`. Isso fornece um contexto muito mais preciso do que simplesmente verificar se o nome do artigo/capítulo aparece *dentro* do chunk.
    * O metadado associado agora reflete `capitulo_ativo` e `artigo_ativo`.
    * *Nota:* Achar a posição exata do chunk no texto original pode ser um desafio com sobreposição; a busca `texto_completo.find(chunk[:50], posicao_texto)` é uma aproximação.

5.  **Qualidade de Código**:
    * Uso extensivo de `logging` em vez de `print` para melhor controle e depuração.
    * Uso de `Constantes` para parâmetros e nomes de arquivos.
    * Adição de Type Hinting (`-> Dict[str, Any]`, `: str`).
    * Melhor tratamento de erros com `try...except` mais específicos e `logging.exception` para capturar o traceback completo.
    * Estrutura principal dentro de uma função `main()` e chamada com `if __name__ == "__main__":`, que é uma boa prática em Python.

**Como Usar:**

1.  Salve este código como um arquivo Python (por exemplo, `processar_decreto.py`).
2.  Certifique-se de que o arquivo `D23569.md` esteja na mesma pasta.
3.  Execute o script: `python processar_decreto.py`
4.  Ele irá gerar:
    * `estrutura_documento.json`: A estrutura geral (similar ao `Filtro.jpg`).
    * `decreto_chunks_metadados.json`: A lista de chunks com os metadados contextuais associados.
    * Mensagens de log no console indicando o progresso e possíveis avisos/erros.

Estas melhorias tornam o script mais robusto, os resultados mais precisos (especialmente a associação de metadados) e o código mais fácil de manter e depur
