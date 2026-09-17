"""
main.py
Servidor FastAPI e orquestração de workflows duráveis com Inngest.
Define as funções assíncronas para ingestão de PDFs e consulta RAG com LLM.
"""

import datetime
import logging
import os
import uuid
from dotenv import load_dotenv
from fastapi import FastAPI
import inngest
from inngest.experimental import ai
import inngest.fast_api

from custom_types import (
    RAGChunkAndSrc,
    RAGQueryResult,
    RAGSearchResult,
    RAGUpsertResult,
)
from data_loader import embed_texts, load_and_chunk_pdf
from vector_db import QdrantStorage

load_dotenv()

# Inicialização do cliente Inngest com serializador Pydantic para troca de dados entre steps
inngest_client = inngest.Inngest(
    app_id="rag_app",
    logger=logging.getLogger("uvicorn"),
    is_production=False,
    serializer=inngest.PydanticSerializer(),
)


@inngest_client.create_function(
    fn_id="RAG: Ingest PDF",
    trigger=inngest.TriggerEvent(event="rag/ingest_pdf"),
    # Throttle: Limita o processamento a no máximo 2 execuções por minuto para proteger cotas
    throttle=inngest.Throttle(
        limit=2, period=datetime.timedelta(minutes=1)
    ),
    # Rate Limit: Evita reprocessamento imediato do mesmo documento pelo source_id
    rate_limit=inngest.RateLimit(
        limit=1,
        period=datetime.timedelta(hours=4),
        key="event.data.source_id",
    ),
)
async def rag_ingest_pdf(ctx: inngest.Context):
    """
    Workflow durável de ingestão de documento PDF.
    Divide o processamento em etapas isoladas (steps) para garantir recuperação e rastreabilidade:
    1. 'load-and-chunk': Extração do texto e divisão em trechos menores.
    2. 'embed-and-upsert': Cálculo dos vetores e persistência no Qdrant.
    """
    def _load(ctx: inngest.Context) -> RAGChunkAndSrc:
        pdf_path = ctx.event.data["pdf_path"]
        source_id = ctx.event.data.get("source_id", pdf_path)
        chunks = load_and_chunk_pdf(pdf_path)
        return RAGChunkAndSrc(chunks=chunks, source_id=source_id)

    def _upsert(chunks_and_src: RAGChunkAndSrc) -> RAGUpsertResult:
        chunks = chunks_and_src.chunks
        source_id = chunks_and_src.source_id
        if not chunks:
            return RAGUpsertResult(ingested=0)

        vecs = embed_texts(chunks)
        # Geração de UUID determinístico (uuid5) para garantir idempotência na indexação
        ids = [
            str(uuid.uuid5(uuid.NAMESPACE_URL, name=f"{source_id}:{i}"))
            for i in range(len(chunks))
        ]
        payloads = [{"source": source_id, "text": chunks[i]} for i in range(len(chunks))]
        QdrantStorage().upsert(ids, vecs, payloads)
        return RAGUpsertResult(ingested=len(chunks))

    # Execução com controle de estado do Inngest (cada step é memorizado e recuperável)
    chunks_and_src = await ctx.step.run(
        "load-and-chunk", lambda: _load(ctx), output_type=RAGChunkAndSrc
    )
    ingested = await ctx.step.run(
        "embed-and-upsert", lambda: _upsert(chunks_and_src), output_type=RAGUpsertResult
    )
    return ingested.model_dump()


@inngest_client.create_function(
    fn_id="RAG: Query PDF",
    trigger=inngest.TriggerEvent(event="rag/query_pdf_ai"),
)
async def rag_query_pdf_ai(ctx: inngest.Context):
    """
    Workflow durável de consulta RAG.
    1. 'embed-and-search': Vetoriza a pergunta e busca os top-k chunks mais próximos no Qdrant.
    2. 'llm-answer': Executa inferência com OpenAI (gpt-4o-mini) usando o contexto recuperado.
    """
    def _search(question: str, top_k: int = 5) -> RAGSearchResult:
        query_vec = embed_texts([question])[0]
        store = QdrantStorage()
        found = store.search(query_vec, top_k)
        return RAGSearchResult(contexts=found["contexts"], sources=found["sources"])

    question = ctx.event.data["question"]
    top_k = int(ctx.event.data.get("top_k", 5))

    # Step 1: Busca vetorial por similaridade semântica
    found = await ctx.step.run(
        "embed-and-search", lambda: _search(question, top_k), output_type=RAGSearchResult
    )

    # Montagem do prompt com contexto recuperado
    context_block = "\n\n".join(f"- {c}" for c in found.contexts)
    user_content = (
        "Use the following context to answer the question.\n\n"
        f"Context:\n{context_block}\n\n"
        f"Question: {question}\n"
        "Answer concisely using the context above."
    )

    adapter = ai.openai.Adapter(
        auth_key=os.getenv("OPENAI_API_KEY"),
        model="gpt-4o-mini",
    )

    # Step 2: Inferência observável pelo motor de IA do Inngest
    res = await ctx.step.ai.infer(
        "llm-answer",
        adapter=adapter,
        body={
            "max_tokens": 1024,
            "temperature": 0.2,
            "messages": [
                {
                    "role": "system",
                    "content": "You answer questions using only the provided context.",
                },
                {"role": "user", "content": user_content},
            ],
        },
    )

    answer = res["choices"][0]["message"]["content"].strip()
    return {
        "answer": answer,
        "sources": found.sources,
        "num_contexts": len(found.contexts),
        "contexts": found.contexts,
    }


# Inicialização da aplicação FastAPI
app = FastAPI(
    title="PDF RAG AI Agent API",
    description="Backend assíncrono para ingestão e consulta RAG com Inngest, Qdrant e OpenAI",
    version="0.1.0",
)


@app.get("/")
def health_check():
    """Endpoint de status e informações básicas da API."""
    return {
        "status": "online",
        "service": "PDF RAG AI Agent API",
        "inngest_endpoint": "/api/inngest",
        "docs": "/docs",
    }


# Registra o endpoint do Inngest no FastAPI (/api/inngest)
inngest.fast_api.serve(app, inngest_client, functions=[rag_ingest_pdf, rag_query_pdf_ai])