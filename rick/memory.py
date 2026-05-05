"""
Memoria semantica con ChromaDB — lazy init, chunking, deduplica.
"""
import chromadb
import requests
import logging
import hashlib
import time
from pathlib import Path
from rick.config import BASE_DIR, OLLAMA_BASE_URL

logger = logging.getLogger(__name__)

DB_PATH = BASE_DIR / "data" / "chroma_db"
EMBED_MODEL = "nomic-embed-text"
CHUNK_SIZE = 500  # token approx

# Lazy init — solo al primo uso
_client = None
_mem_coll = None
_knw_coll = None


class OllamaEmbedder(chromadb.EmbeddingFunction):
    def __call__(self, input: chromadb.Documents) -> chromadb.Embeddings:
        embeddings = []
        for text in input:
            try:
                res = requests.post(
                    f"{OLLAMA_BASE_URL}/api/embeddings",
                    json={"model": EMBED_MODEL, "prompt": text},
                    timeout=30
                )
                res.raise_for_status()
                embeddings.append(res.json()["embedding"])
            except Exception as e:
                logger.error(f"[memory] Embedding error: {e}")
                raise e
        return embeddings


def _init():
    """Init ChromaDB solo al primo uso — non all'import."""
    global _client, _mem_coll, _knw_coll
    if _client is not None:
        return
    
    try:
        _client = chromadb.PersistentClient(path=str(DB_PATH))
        embedder = OllamaEmbedder()
        _mem_coll = _client.get_or_create_collection(name="memories", embedding_function=embedder)
        _knw_coll = _client.get_or_create_collection(name="knowledge", embedding_function=embedder)
        logger.info("[memory] ChromaDB initialized")
    except Exception as e:
        logger.error(f"[memory] Init failed: {e}")
        raise


def _chunk_text(text: str, size: int = CHUNK_SIZE) -> list[str]:
    """Split text in chunk da ~size parole."""
    words = text.split()
    chunks = []
    for i in range(0, len(words), size):
        chunk = " ".join(words[i:i+size])
        if chunk.strip():
            chunks.append(chunk)
    return chunks


def save_memory(user_input: str, extracted_facts: str):
    """Salva fatto nella memoria — usa hash per deduplica."""
    if not extracted_facts or "NIENTE" in extracted_facts.upper():
        return
    
    _init()
    try:
        # Hash del fatto per deduplica
        fact_hash = hashlib.md5(extracted_facts.encode()).hexdigest()[:12]
        mem_id = f"mem_{fact_hash}"
        
        # Check se esiste già
        existing = _mem_coll.get(ids=[mem_id])
        if existing and existing['ids']:
            logger.info(f"[memory] Fatto già presente: {extracted_facts[:50]}...")
            return
        
        _mem_coll.add(
            documents=[extracted_facts],
            metadatas=[{"user_input": user_input, "source": "chat", "ts": int(time.time())}],
            ids=[mem_id]
        )
        logger.info(f"[memory] Saved: {extracted_facts[:60]}...")
    except Exception as e:
        logger.error(f"[memory] Save error: {e}")


def get_recent_memories(query: str, limit: int = 6) -> str:
    """Ricerca semantica — bilanciata tra ricordi e knowledge."""
    _init()
    try:
        # Prendi metà da ogni collezione
        n_per_coll = max(3, limit // 2)
        
        results_mem = _mem_coll.query(query_texts=[query], n_results=n_per_coll)
        results_knw = _knw_coll.query(query_texts=[query], n_results=n_per_coll)
        
        combined = []
        
        if results_mem and results_mem['documents'] and results_mem['documents'][0]:
            for doc in results_mem['documents'][0]:
                combined.append(f"[RICORDO]: {doc}")
                
        if results_knw and results_knw['documents'] and results_knw['documents'][0]:
            for doc in results_knw['documents'][0]:
                combined.append(f"[DOCS]: {doc}")
        
        return "\n".join(combined[:limit]) if combined else ""
    except Exception as e:
        logger.error(f"[memory] Query error: {e}")
        return ""


def add_knowledge(text: str, source_name: str):
    """Aggiunge documento con chunking — deduplica su hash chunk."""
    _init()
    try:
        chunks = _chunk_text(text, size=CHUNK_SIZE)
        added = 0
        for i, chunk in enumerate(chunks):
            chunk_hash = hashlib.md5(chunk.encode()).hexdigest()[:12]
            doc_id = f"knw_{chunk_hash}"
            
            # Deduplica
            existing = _knw_coll.get(ids=[doc_id])
            if existing and existing['ids']:
                continue
            
            _knw_coll.add(
                documents=[chunk],
                metadatas=[{"source": source_name, "chunk": i}],
                ids=[doc_id]
            )
            added += 1
        
        logger.info(f"[memory] Added {added}/{len(chunks)} chunks from: {source_name}")
    except Exception as e:
        logger.error(f"[memory] Add knowledge error: {e}")
