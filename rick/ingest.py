import sys
from pathlib import Path
from rick.memory import add_knowledge

def extract_pdf_text(filepath: Path) -> str:
    try:
        import pypdf
        text = ""
        with open(filepath, "rb") as f:
            reader = pypdf.PdfReader(f)
            for page in reader.pages:
                text += page.extract_text() + "\n"
        return text
    except Exception as e:
        print(f"  [ERRORE PDF] {filepath.name}: {e}")
        return ""

def ingest_directory(dir_path: str):
    """Legge tutti i file .txt, .md e .pdf da una cartella e li indicizza in ChromaDB."""
    path = Path(dir_path)
    if not path.exists():
        print(f"Errore: la cartella {dir_path} non esiste.")
        return

    files = list(path.glob("**/*.txt")) + list(path.glob("**/*.md")) + list(path.glob("**/*.pdf"))
    
    if not files:
        print("Nessun file .txt, .md o .pdf trovato.")
        return

    print(f"Indicizzazione di {len(files)} file in corso...")
    for f in files:
        try:
            if f.suffix.lower() == ".pdf":
                content = extract_pdf_text(f).strip()
            else:
                content = f.read_text(encoding="utf-8").strip()
                
            if content:
                add_knowledge(content, source_name=f.name)
                print(f"  [OK] {f.name}")
        except Exception as e:
            print(f"  [ERRORE] {f.name}: {e}")

    print("\nFatto! Rick ora conosce questi documenti.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python3 -m rick.ingest <cartella_documenti>")
    else:
        ingest_directory(sys.argv[1])
