"""
Ingestione documenti con chunking, PDF support, retry logic.
"""
import argparse
from pathlib import Path
from rick.memory import add_knowledge
from pypdf import PdfReader
import logging
import time

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

CHUNK_SIZE = 400  # parole per chunk (più piccolo = più stabile)
SUPPORTED_EXTS = {".txt", ".md", ".pdf"}


def chunk_text(text: str, size: int = CHUNK_SIZE) -> list[str]:
    """Split testo in chunk da ~size parole."""
    words = text.split()
    chunks = []
    for i in range(0, len(words), size):
        chunk = " ".join(words[i:i+size])
        if chunk.strip():
            chunks.append(chunk)
    return chunks


def read_file(filepath: Path) -> str | None:
    """Legge file (txt, md, pdf) e ritorna il testo."""
    try:
        if filepath.suffix == ".pdf":
            reader = PdfReader(filepath)
            text = "\n".join(page.extract_text() for page in reader.pages if page.extract_text())
            return text
        else:
            return filepath.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        logger.error(f"[ingest] Error reading {filepath.name}: {e}")
        return None


def ingest_file(filepath: Path, retry_delay: int = 2):
    """
    Ingerisce un file con chunking e retry su errori Ollama.
    """
    if filepath.suffix not in SUPPORTED_EXTS:
        logger.warning(f"[ingest] Unsupported file: {filepath.name}")
        return
    
    logger.info(f"[ingest] Processing: {filepath.name}")
    
    text = read_file(filepath)
    if not text:
        logger.error(f"[ingest] Empty or unreadable: {filepath.name}")
        return
    
    # Chunking
    chunks = chunk_text(text, size=CHUNK_SIZE)
    logger.info(f"[ingest] Split into {len(chunks)} chunks")
    
    # Ingestione con retry e rate limiting
    for i, chunk in enumerate(chunks):
        retries = 0
        while retries < 3:
            try:
                add_knowledge(chunk, source_name=f"{filepath.name}#chunk{i}")
                if (i + 1) % 10 == 0:
                    logger.info(f"[ingest] Progress: {i+1}/{len(chunks)}")
                time.sleep(0.5)  # Rate limiting soft per Ollama
                break
            except Exception as e:
                retries += 1
                if "500" in str(e) or "Internal Server Error" in str(e):
                    logger.warning(f"[ingest] Ollama 500 on chunk {i}, retry {retries}/3")
                    time.sleep(retry_delay * retries)  # Backoff esponenziale
                else:
                    logger.error(f"[ingest] Fatal error on chunk {i}: {e}")
                    break
    
    logger.info(f"[ingest] ✓ Completed: {filepath.name}")


def ingest_directory(directory: Path):
    """Ingerisce tutti i file supportati in una directory."""
    files = [f for f in directory.rglob("*") if f.is_file() and f.suffix in SUPPORTED_EXTS]
    logger.info(f"[ingest] Found {len(files)} files")
    
    for filepath in files:
        ingest_file(filepath)


def main():
    parser = argparse.ArgumentParser(description="Ingest documents into Rick's knowledge base")
    parser.add_argument("path", type=str, help="File or directory to ingest")
    args = parser.parse_args()
    
    path = Path(args.path)
    if not path.exists():
        logger.error(f"[ingest] Path not found: {path}")
        return
    
    if path.is_file():
        ingest_file(path)
    elif path.is_dir():
        ingest_directory(path)
    else:
        logger.error(f"[ingest] Invalid path: {path}")


if __name__ == "__main__":
    main()
