import os
from pathlib import Path

def bundle_project():
    project_root = Path("/home/marcobiasolo/project-rick_/v8")
    output_file = project_root / "project_rick_bundle.md"
    
    # Cartelle e file da ESCLUDERE
    exclude_dirs = {'.git', '__pycache__', 'venv', 'data', '.gemini', 'node_modules'}
    exclude_files = {'project_rick_bundle.md', 'facts.sqlite', 'checkpoints.sqlite', 'bundle_project.py'}
    include_extensions = {'.py', '.md', '.txt', '.json', '.env'}
    include_exact_files = {'.env'}

    with open(output_file, "w", encoding="utf-8") as out:
        out.write("# Project Rick C-137 — Full Codebase Bundle\n\n")
        
        # 1. Generazione TREE (Mappa del progetto)
        out.write("## PROJECT STRUCTURE (TREE)\n")
        out.write("```text\n")
        for root, dirs, files in os.walk(project_root):
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            level = root.replace(str(project_root), '').count(os.sep)
            indent = ' ' * 4 * (level)
            out.write(f"{indent}{os.path.basename(root)}/\n")
            sub_indent = ' ' * 4 * (level + 1)
            for f in files:
                if f not in exclude_files and (Path(f).suffix in include_extensions or f in include_exact_files):
                    out.write(f"{sub_indent}{f}\n")
        out.write("```\n\n")
        
        out.write("---\n\n")
        out.write("## CODE CONTENTS\n\n")
        
        # 2. Scrittura CONTENUTI
        for root, dirs, files in os.walk(project_root):
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            for file in files:
                if file in exclude_files:
                    continue
                path = Path(root) / file
                if path.suffix not in include_extensions and file not in include_exact_files:
                    continue
                
                relative_path = path.relative_to(project_root)
                out.write(f"### FILE: {relative_path}\n")
                out.write("```" + (path.suffix[1:] if path.suffix else "") + "\n")
                try:
                    content = path.read_text(encoding="utf-8", errors="ignore")
                    out.write(content)
                except Exception as e:
                    out.write(f"ERROR READING FILE: {e}")
                out.write("\n```\n\n")
                
    print(f"✅ Bundle creato con successo: {output_file}")

if __name__ == "__main__":
    bundle_project()
