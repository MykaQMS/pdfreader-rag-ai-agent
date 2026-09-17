"""
data_loader.py
Módulo responsável pelo carregamento de arquivos PDF, divisão em chunks (chunking)
e geração de embeddings vetoriais utilizando o modelo text-embedding-3-large da OpenAI.
"""

import os
from dotenv import load_dotenv
from llama_index.core.node_parser import SentenceSplitter
from llama_index.readers.file import PDFReader
from openai import OpenAI

load_dotenv()

# Inicialização do cliente OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Configuração do modelo de embeddings da OpenAI
EMBED_MODEL = "text-embedding-3-large"
EMBED_DIM = 3072

# Divisor de sentenças: chunk_size de 1000 caracteres com sobreposição (overlap) de 200 para preservar o contexto
splitter = SentenceSplitter(chunk_size=1000, chunk_overlap=200)


def load_and_chunk_pdf(path: str) -> list[str]:
    """
    Lê um arquivo PDF utilizando o PDFReader do LlamaIndex e divide o texto em chunks menores.
    
    Args:
        path: Caminho no sistema de arquivos para o PDF.
        
    Returns:
        Lista de strings contendo cada chunk de texto gerado.
    """
    docs = PDFReader().load_data(file=path)
    texts = [d.text for d in docs if getattr(d, "text", None)]
    
    chunks: list[str] = []
    for t in texts:
        chunks.extend(splitter.split_text(t))
    return chunks


def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    Gera vetores densos (embeddings) para uma lista de textos utilizando a API de Embeddings da OpenAI.
    
    Args:
        texts: Lista de textos/chunks a serem vetorizados.
        
    Returns:
        Lista de vetores (cada vetor é uma lista de floats com dimensão 3072).
    """
    if not texts:
        return []

    response = client.embeddings.create(
        model=EMBED_MODEL,
        input=texts,
    )
    return [item.embedding for item in response.data]