"""
Modulo di Ottimizzazione (Agent-Lightning Hook)

Analizza i trace generati dal sistema per trovare gli errori corretti dall'Auditor.
Genera "Linee Guida" permanenti affinché il Coder non ripeta l'errore.
"""
import json
import logging
import os
import sys
from pathlib import Path
from rick.config import DATA_DIR, PROMPTS_DIR, MODEL_MANAGER
from rick.llm.client import ollama_generate

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("optimizer")

GUIDELINES_FILE = PROMPTS_DIR / "coder_guidelines.txt"

_SYSTEM_OPTIMIZER = (
    "Sei un AI Optimizer. Il tuo scopo è analizzare un errore fatto da un Coder e la correzione richiesta "
    "da un Auditor. Devi estrarre UNA SINGOLA REGOLA GENERALE, chiara e concisa (max 2 frasi), "
    "che il Coder dovrà seguire in futuro per non ripetere lo stesso errore.\n"
    "Esempio: 'Evita l'uso di rm -rf /tmp/*, usa invece trap per pulire i file temporanei specifici dello script.'"
)

def _load_traces() -> list[list[dict]]:
    """Carica tutte le sessioni JSONL dalla directory."""
    sessions = []
    if not DATA_DIR.exists():
        return sessions
    for filepath in DATA_DIR.glob("*.jsonl"):
        session_trace = []
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    session_trace.append(json.loads(line))
        sessions.append(session_trace)
    return sessions

def extract_lessons() -> list[str]:
    """Trova le interazioni dove l'Auditor ha generato un retry e impara la lezione."""
    sessions = _load_traces()
    new_lessons = []
    
    # Carica le lezioni già apprese per evitare duplicati logici
    existing_lessons = ""
    if GUIDELINES_FILE.exists():
        existing_lessons = GUIDELINES_FILE.read_text(encoding="utf-8")

    for session in sessions:
        for node_data in session:
            if node_data["node"] == "auditor" and node_data.get("data"):
                data = node_data["data"]
                if data["verdict"] == "retry":
                    # Abbiamo trovato un errore!
                    draft = data.get("draft", "")
                    issues = data.get("issues", [])
                    hint = data.get("fix_hint", "")
                    
                    # Usa Ollama per estrarre la regola
                    prompt = (
                        f"Il Coder ha scritto questo codice errato:\n{draft[:1000]}...\n\n"
                        f"L'Auditor ha riscontrato questi problemi: {issues}\n"
                        f"Suggerimento dell'Auditor: {hint}\n\n"
                        "Genera una REGOLA BREVE (max 2 frasi) da aggiungere alle linee guida. "
                        "NON spiegare, scrivi solo la regola imperativa."
                    )
                    
                    if hint in existing_lessons:
                        continue # Evita di generare due volte per lo stesso errore (euristica semplice)
                        
                    logger.info(f"Trovato errore. Estrazione lezione...")
                    lesson = ollama_generate(
                        model=MODEL_MANAGER, 
                        prompt=prompt, 
                        system=_SYSTEM_OPTIMIZER, 
                        temperature=0.2, 
                        keep_alive="0"
                    )
                    if lesson and len(lesson) < 200:
                        new_lessons.append(lesson)
                        existing_lessons += f"\n- {lesson}"
                        
    if new_lessons:
        with open(GUIDELINES_FILE, "a", encoding="utf-8") as f:
            for lesson in new_lessons:
                f.write(f"\n- {lesson}\n")
        logger.info(f"Agent-Lightning: Apprese {len(new_lessons)} nuove lezioni!")
    else:
        logger.info("Agent-Lightning: Nessuna nuova lezione da imparare.")
        
    return new_lessons

if __name__ == "__main__":
    logger.info("Avvio Agent-Lightning Optimizer...")
    extract_lessons()
