"""
vector_db.py
Camada de persistência e recuperação vetorial utilizando Qdrant.
Gerencia coleções, upsert em lote com PointStruct e busca por similaridade semântica (distância cosseno).
"""

import os
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

load_dotenv()


class QdrantStorage:
    """Classe responsável pela integração com o banco vetorial Qdrant."""

    def __init__(self, url: str | None = None, collection: str = "docs", dim: int = 3072):
        """
        Inicializa a conexão com o Qdrant e cria a coleção caso ainda não exista.
        
        Args:
            url: Endereço do Qdrant (ex: 'http://localhost:6333' ou ':memory:').
                 Se não informado, lê a variável QDRANT_URL do .env.
            collection: Nome da coleção de vetores.
            dim: Dimensionalidade dos vetores de embeddings (3072 para text-embedding-3-large).
        """
        target_url = url or os.getenv("QDRANT_URL", "http://localhost:6333")

        if target_url == ":memory:":
            self.client = QdrantClient(location=":memory:", timeout=30)
        else:
            self.client = QdrantClient(url=target_url, timeout=30)

        self.collection = collection

        # Garante a existência da coleção com métrica de distância cosseno
        if not self.client.collection_exists(self.collection):
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
            )

    def upsert(self, ids: list[str], vectors: list[list[float]], payloads: list[dict]) -> None:
        """
        Insere ou atualiza vetores e seus metadados (payloads) na coleção.
        
        Args:
            ids: Lista de UUIDs únicos para cada ponto.
            vectors: Lista de vetores numéricos correspondentes aos embeddings.
            payloads: Dicionários com metadados (texto original, nome do arquivo fonte, etc.).
        """
        if not ids:
            return

        points = [
            PointStruct(id=ids[i], vector=vectors[i], payload=payloads[i])
            for i in range(len(ids))
        ]
        self.client.upsert(self.collection, points=points)

    def search(self, query_vector: list[float], top_k: int = 5) -> dict:
        """
        Executa a busca vetorial por similaridade semântica para encontrar os chunks mais relevantes.
        
        Args:
            query_vector: Vetor de embedding da pergunta do usuário.
            top_k: Número máximo de chunks relevantes a retornar.
            
        Returns:
            Dicionário com a lista de textos recuperados ('contexts') e os arquivos de origem ('sources').
        """
        # Suporte a versões recentes do qdrant-client (query_points) e legadas (search)
        if hasattr(self.client, "query_points"):
            results = self.client.query_points(
                collection_name=self.collection,
                query=query_vector,
                with_payload=True,
                limit=top_k,
            ).points
        else:
            results = self.client.search(
                collection_name=self.collection,
                query_vector=query_vector,
                with_payload=True,
                limit=top_k,
            )

        contexts: list[str] = []
        sources: set[str] = set()

        for r in results:
            payload = getattr(r, "payload", None) or {}
            text = payload.get("text", "")
            source = payload.get("source", "")
            if text:
                contexts.append(text)
                sources.add(source)

        return {"contexts": contexts, "sources": list(sources)}