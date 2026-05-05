import sys
import zipfile
import tempfile
from pathlib import Path
from rick.memory import add_knowledge

# Estensioni di testo/codice supportate
TEXT_EXTENSIONS = {
    ".txt", ".md", ".pdf", ".py", ".js", ".ts", ".jsx", ".tsx", ".c", ".cpp", ".h", ".hpp", 
    ".java", ".go", ".rs", ".html", ".css", ".json", ".yaml", ".yml", ".sql", ".sh", ".bash",
    ".toml", ".ini", ".env", ".Dockerfile"
}

# Cartelle da ignorare TASSATIVAMENTE
IGNORE_DIRS = {
    ".git", ".svn", "node_modules", "venv", ".venv", "env", "__pycache__", 
    "dist", "build", "out", "target", "vendor", ".idea", ".vscode"
}

MAX_FILE_SIZE_KB = 1000  # Ignora file più grandi di 1MB (solitamente log o bundle minificati)

def extract_pdf_text(filepath: Path) -> str:
    try:
        import pypdf
        text = ""
        with open(filepath, "rb") as f:
            reader = pypdf.PdfReader(f)
            for page in reader.pages:
                text += page.extract_text() + "\n"
        return text
    except ImportError:
        print(f"  [AVVISO] Installa 'pypdf' per leggere i PDF: pip install pypdf")
        return ""
    except Exception as e:
        print(f"  [ERRORE PDF] {filepath.name}: {e}")
        return ""

def is_valid_file(file_path: Path) -> bool:
    """Verifica se il file è valido per l'ingestione."""
    # 1. Controlla estensione (o nome esatto come Dockerfile)
    ext = file_path.suffix.lower()
    if ext not in TEXT_EXTENSIONS and file_path.name not in ["Dockerfile", "Makefile"]:
        return False
    
    # 2. Controlla cartelle genitore
    for part in file_path.parts:
        if part in IGNORE_DIRS:
            return False
            
    # 3. Controlla dimensione
    try:
        if file_path.stat().st_size > MAX_FILE_SIZE_KB * 1024:
            return False
    except OSError:
        return False
        
    return True

def ingest_file(file_path: Path, base_dir: Path = None):
    """Indicizza un singolo file. Usa base_dir per calcolare il percorso relativo."""
    try:
        if file_path.name.lower().endswith(".pdf"):
            content = extract_pdf_text(file_path).strip()
        else:
            content = file_path.read_text(encoding="utf-8", errors="ignore").strip()
            
        if content:
            # Calcola il nome sorgente: usa il path relativo se disponibile, altrimenti il nome file
            source_name = str(file_path.relative_to(base_dir)) if base_dir else file_path.name
            
            # Aggiungiamo un'intestazione al contenuto per dare contesto a Rick
            enriched_content = f"FILE: {source_name}\n\n{content}"
            add_knowledge(enriched_content, source_name=source_name, replace_existing=True)
            print(f"  [OK] {source_name}")
            import time
            time.sleep(0.5)  # Pausa tattica per far respirare Ollama
    except Exception as e:
        print(f"  [ERRORE] {file_path.name}: {e}")

def ingest_directory(path: Path):
    """Indicizza ricorsivamente una cartella, filtrando il rumore."""
    print(f"Analisi cartella: {path}")
    
    # Trova tutti i file ricorsivamente
    all_files = [f for f in path.rglob("*") if f.is_file()]
    
    # Filtra i file validi
    valid_files = [f for f in all_files if is_valid_file(f)]
    
    if not valid_files:
        print("Nessun file supportato o valido trovato.")
        return

    print(f"Indicizzazione di {len(valid_files)} file validi (escluse cartelle spazzatura e file giganti)...")
    for f in valid_files:
        ingest_file(f, base_dir=path)

def ingest_anything(path_str: str):
    """Punto di ingresso principale: gestisce file, cartelle e ZIP in modo sicuro."""
    path = Path(path_str)
    if not path.exists():
        print(f"Errore: {path_str} non esiste.")
        return

    # Gestione ZIP
    if path.suffix.lower() == ".zip":
        print(f"Scompattazione ZIP in ambiente protetto: {path.name}")
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                with zipfile.ZipFile(path, 'r') as zip_ref:
                    zip_ref.extractall(tmpdir)
                ingest_directory(Path(tmpdir))
            except zipfile.BadZipFile:
                print("Errore: Il file fornito non è uno ZIP valido.")
        print("\nFatto! ZIP digerito.")
        return

    # Gestione Cartella
    if path.is_dir():
        ingest_directory(path)
        print("\nFatto! Cartella digerita.")
        return

    # Gestione File Singolo
    if path.is_file():
        if is_valid_file(path):
            ingest_file(path)
            print("\nFatto! File digerito.")
        else:
            print("Il file è stato scartato (estensione non supportata o troppo grande).")
        return

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python3 -m rick.ingest <file_o_cartella_o_zip>")
    else:
        ingest_anything(sys.argv[1])
