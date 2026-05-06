"""
Memoria semantica con ChromaDB — lazy init, chunking, deduplica.

3 COLLEZIONI:
- verified_facts: fatti validati dall'output_validator (confidence 1.0)
- memories: fatti estratti da conversazioni (confidence variabile)
- knowledge: documenti ingesti (PDF, markdown, etc.)

Query priority: verified_facts → knowledge → memories
"""
import os
os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["CHROMA_TELEMETRY"] = "False"

import chromadb
import requests
import logging
import hashlib
import time
import sqlite3

from pathlib import Path
from typing import Literal
from rick.config import BASE_DIR, OLLAMA_BASE_URL

logger = logging.getLogger(__name__)

DB_PATH = BASE_DIR / "data" / "chroma_db"
FACTS_SQLITE = BASE_DIR / "data" / "facts.sqlite"
EMBED_MODEL = "nomic-embed-text"
CHUNK_SIZE = 500  # token approx

# Lazy init — solo al primo uso
_client = None
_verified_coll = None
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
    global _client, _verified_coll, _mem_coll, _knw_coll
    if _client is not None:
        return
    
    try:
        from chromadb.config import Settings
        _client = chromadb.PersistentClient(
            path=str(DB_PATH),
            settings=Settings(anonymized_telemetry=False)
        )
        embedder = OllamaEmbedder()
        _verified_coll = _client.get_or_create_collection(
            name="verified_facts", 
            embedding_function=embedder
        )
        _mem_coll = _client.get_or_create_collection(
            name="memories", 
            embedding_function=embedder
        )
        _knw_coll = _client.get_or_create_collection(
            name="knowledge", 
            embedding_function=embedder
        )
        logger.info("[memory] ChromaDB initialized (3 collections)")
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


def save_verified_fact(
    content: str,
    source_type: Literal["executor_output", "document"] = "executor_output",
    metadata: dict | None = None
):
    """
    Salva un fatto VERIFICATO nella collezione verified_facts (ChromaDB)
    e anche nella tabella SQLite per query deterministiche.
    """
    if not content or len(content.strip()) < 10:
        return
    
    # ChromaDB
    _init()
    try:
        fact_hash = hashlib.md5(content.encode()).hexdigest()[:12]
        fact_id = f"verified_{fact_hash}"
        
        meta = {
            "source_type": source_type,
            "verified_by": "output_validator",
            "confidence": 1.0,
            "ts": int(time.time()),
            "expires_at": None,
        }
        if metadata:
            meta.update(metadata)
        
        existing = _verified_coll.get(ids=[fact_id])
        if existing and existing['ids']:
            logger.info(f"[memory] Fatto verificato già presente: {content[:50]}...")
        else:
            _verified_coll.add(
                documents=[content],
                metadatas=[meta],
                ids=[fact_id]
            )
            logger.info(f"[memory] ✅ Verified fact saved: {content[:60]}...")
    except Exception as e:
        logger.error(f"[memory] Save verified fact error: {e}")
    
    # SQLite per query esatte
    try:
        conn = sqlite3.connect(str(FACTS_SQLITE))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS verified_facts_v2 (
                id INTEGER PRIMARY KEY,
                fact TEXT NOT NULL UNIQUE,
                source TEXT DEFAULT 'executor',
                ts INTEGER NOT NULL
            )
        """)
        conn.execute(
            "INSERT OR IGNORE INTO verified_facts_v2 (fact, source, ts) VALUES (?, ?, ?)",
            (content, source_type, int(time.time()))
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"[memory] SQLite verified fact error: {e}")


def save_memory(user_input: str, extracted_facts: str, confidence: float = 0.7):
    """Salva fatto nella memoria — usa hash per deduplica."""
    if not extracted_facts or "NIENTE" in extracted_facts.upper():
        return
    
    _init()
    try:
        fact_hash = hashlib.md5(extracted_facts.encode()).hexdigest()[:12]
        mem_id = f"mem_{fact_hash}"
        
        existing = _mem_coll.get(ids=[mem_id])
        if existing and existing['ids']:
            logger.info(f"[memory] Fatto già presente: {extracted_facts[:50]}...")
            return
        
        _mem_coll.add(
            documents=[extracted_facts],
            metadatas=[{
                "user_input": user_input, 
                "source_type": "chat", 
                "confidence": confidence,
                "ts": int(time.time())
            }],
            ids=[mem_id]
        )
        logger.info(f"[memory] Saved: {extracted_facts[:60]}...")
    except Exception as e:
        logger.error(f"[memory] Save error: {e}")


def get_recent_memories(query: str, limit: int = 6) -> str:
    """
    Ricerca semantica gerarchica:
    1. verified_facts (priorità massima)
    2. knowledge (documenti)
    3. memories (chat)
    
    Ritorna i top-K risultati con prefix che indica la fonte.
    """
    _init()
    try:
        results_verified = _verified_coll.query(query_texts=[query], n_results=limit)
        results_knw = _knw_coll.query(query_texts=[query], n_results=limit)
        results_mem = _mem_coll.query(query_texts=[query], n_results=limit)
        
        combined = []
        
        if results_verified and results_verified['documents'] and results_verified['documents'][0]:
            for doc, meta in zip(
                results_verified['documents'][0],
                results_verified['metadatas'][0]
            ):
                confidence = meta.get('confidence', 1.0)
                combined.append({
                    "text": f"[VERIFICATO ✓]: {doc}",
                    "score": 1.0 + confidence,
                    "ts": meta.get('ts', 0)
                })
        
        if results_knw and results_knw['documents'] and results_knw['documents'][0]:
            for doc, meta in zip(
                results_knw['documents'][0],
                results_knw['metadatas'][0]
            ):
                source = meta.get('source', 'unknown')
                combined.append({
                    "text": f"[DOCS: {source}]: {doc}",
                    "score": 0.8,
                    "ts": meta.get('ts', 0)
                })
        
        if results_mem and results_mem['documents'] and results_mem['documents'][0]:
            for doc, meta in zip(
                results_mem['documents'][0],
                results_mem['metadatas'][0]
            ):
                confidence = meta.get('confidence', 0.7)
                combined.append({
                    "text": f"[RICORDO ~{int(confidence*100)}%]: {doc}",
                    "score": 0.5 * confidence,
                    "ts": meta.get('ts', 0)
                })
        
        combined.sort(key=lambda x: (x["score"], x["ts"]), reverse=True)
        return "\n".join([item["text"] for item in combined[:limit]]) if combined else ""
    
    except Exception as e:
        logger.error(f"[memory] Query error: {e}")
        return ""


def add_knowledge(
    text: str, 
    source_name: str,
    version: str | None = None,
    replace_existing: bool = False
):
    """Aggiunge documento con chunking — deduplica su hash chunk."""
    _init()
    try:
        if replace_existing:
            all_docs = _knw_coll.get(where={"source": source_name})
            if all_docs and all_docs['ids']:
                _knw_coll.delete(ids=all_docs['ids'])
                logger.info(f"[memory] Removed {len(all_docs['ids'])} old chunks from: {source_name}")
        
        chunks = _chunk_text(text, size=CHUNK_SIZE)
        added = 0
        ts = int(time.time())
        
        for i, chunk in enumerate(chunks):
            doc_id = f"knw_{hashlib.md5(f'{source_name}_{i}'.encode()).hexdigest()[:12]}"
            
            if not replace_existing:
                existing = _knw_coll.get(ids=[doc_id])
                if existing and existing['ids']:
                    continue
            
            _knw_coll.add(
                documents=[chunk],
                metadatas=[{
                    "source": source_name,
                    "chunk": i,
                    "version": version or "unknown",
                    "ingested_at": ts,
                }],
                ids=[doc_id]
            )
            added += 1
        
        logger.info(f"[memory] Added {added}/{len(chunks)} chunks from: {source_name}")
    except Exception as e:
        logger.error(f"[memory] Add knowledge error: {e}")


def cleanup_old_versions(source_name: str, keep_latest: int = 1):
    """Elimina versioni vecchie di un documento."""
    _init()
    try:
        all_docs = _knw_coll.get(where={"source": source_name})
        if not all_docs or not all_docs['ids']:
            return
        
        versions = {}
        for doc_id, meta in zip(all_docs['ids'], all_docs['metadatas']):
            ver = meta.get('version', 'unknown')
            ts = meta.get('ingested_at', 0)
            if ver not in versions:
                versions[ver] = []
            versions[ver].append((doc_id, ts))
        
        sorted_versions = sorted(
            versions.items(),
            key=lambda x: max(ts for _, ts in x[1]),
            reverse=True
        )
        
        to_delete = []
        for ver, chunks in sorted_versions[keep_latest:]:
            to_delete.extend([chunk_id for chunk_id, _ in chunks])
        
        if to_delete:
            _knw_coll.delete(ids=to_delete)
            logger.info(f"[memory] Cleaned {len(to_delete)} chunks from old versions of: {source_name}")
    
    except Exception as e:
        logger.error(f"[memory] Cleanup error: {e}")


def get_all_verified_facts_sqlite(limit: int = 20) -> list[str]:
    """Recupera tutti i fatti verificati dalla tabella SQLite (query esatte)."""
    try:
        conn = sqlite3.connect(str(FACTS_SQLITE))
        rows = conn.execute(
            "SELECT fact FROM verified_facts_v2 ORDER BY ts DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
        return [r[0] for r in rows]
    except Exception:
        return []