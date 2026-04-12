import os
from typing import Iterable, List
import structlog

logger = structlog.get_logger(__name__)


class VectorStore:
    def __init__(self, collection_name: str = "skills"):
        self._available = False
        self.collection = None
        try:
            import chromadb
            from chromadb.utils.embedding_functions import (
                SentenceTransformerEmbeddingFunction,
                GoogleGenerativeAiEmbeddingFunction
            )
            
            host = os.getenv("CHROMADB_HOST")
            port = int(os.getenv("CHROMADB_PORT", "8000"))
            
            if host:
                logger.info("vector_store_connecting_http", host=host, port=port)
                self.client = chromadb.HttpClient(host=host, port=port)
            else:
                # Fallback to local persistence if no host provided (convenient for local dev)
                persist_directory = os.getenv("CHROMA_PERSIST_DIRECTORY", "./data/chroma")
                logger.info("vector_store_using_local_persistence", path=persist_directory)
                self.client = chromadb.PersistentClient(path=persist_directory)

            google_key = os.getenv("GOOGLE_API_KEY")
            if google_key:
                logger.info("vector_store_using_gemini_embeddings")
                self.embedding = GoogleGenerativeAiEmbeddingFunction(
                    api_key=google_key,
                    model_name="models/text-embedding-004"
                )
            else:
                embedding_model = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
                logger.info("vector_store_using_local_embeddings", model=embedding_model)
                self.embedding = SentenceTransformerEmbeddingFunction(model_name=embedding_model)
            
            self.collection = self.client.get_or_create_collection(
                name=collection_name,
                embedding_function=self.embedding,
            )
            self._available = True
            logger.info("vector_store_initialized", collection=collection_name)
        except ImportError:
            logger.warning("vector_store_missing_dependencies")
        except Exception as e:
            logger.warning("vector_store_init_failed", error=str(e))

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
