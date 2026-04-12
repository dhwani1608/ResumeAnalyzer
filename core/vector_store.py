from __future__ import annotations

import os
from typing import Iterable, List


class VectorStore:
    def __init__(self, collection_name: str = "skills"):
        try:
            import chromadb
            from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
            
            host = os.getenv("CHROMADB_HOST", "chromadb")
            port = int(os.getenv("CHROMADB_PORT", "8000"))
            self.client = chromadb.HttpClient(host=host, port=port)
            embedding_model = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
            self.embedding = SentenceTransformerEmbeddingFunction(model_name=embedding_model)
            self.collection = self.client.get_or_create_collection(
                name=collection_name,
                embedding_function=self.embedding,
            )
            self._available = True
        except (ImportError, Exception):
            self._available = False
            self.collection = None

    async def upsert_skills(self, skills: Iterable[str]) -> None:
        if not self._available or self.collection is None:
            return
        unique = list(dict.fromkeys(s.strip() for s in skills if s and s.strip()))
        if not unique:
            return
        ids = [f"skill::{s.lower()}" for s in unique]
        self.collection.upsert(ids=ids, documents=unique)

    async def semantic_search(self, query: str, k: int = 3) -> List[str]:
        if not self._available or self.collection is None or not query:
            return []
        results = self.collection.query(query_texts=[query], n_results=k)
        docs = results.get("documents", [[]])
        return docs[0] if docs else []
