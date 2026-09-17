"""
custom_types.py
Definição dos esquemas de dados (Pydantic models) trafegados entre os steps do Inngest e o pipeline RAG.
Garante tipagem estática e serialização confiável nas execuções assíncronas.
"""

from typing import Optional
from pydantic import BaseModel, Field


class RAGChunkAndSrc(BaseModel):
    """Estrutura intermediária contendo os fragmentos de texto extraídos e a identificação do documento."""
    chunks: list[str] = Field(description="Lista de trechos (chunks) de texto extraídos do PDF.")
    source_id: Optional[str] = Field(default=None, description="Identificador único ou nome do arquivo de origem.")


class RAGUpsertResult(BaseModel):
    """Resultado da indexação vetorial no Qdrant."""
    ingested: int = Field(description="Quantidade de chunks indexados com sucesso no banco vetorial.")


class RAGSearchResult(BaseModel):
    """Resultado da busca por similaridade semântica no banco vetorial."""
    contexts: list[str] = Field(description="Trechos mais relevantes recuperados com base na pergunta.")
    sources: list[str] = Field(description="Lista de fontes (arquivos) de onde os trechos foram extraídos.")


class RAGQueryResult(BaseModel):
    """Resposta final gerada pelo modelo de linguagem e metadados da recuperação."""
    answer: str = Field(description="Resposta sintetizada pelo LLM com base nos contextos.")
    sources: list[str] = Field(description="Fontes consultadas na geração da resposta.")
    num_contexts: int = Field(description="Número de fragmentos de contexto utilizados.")