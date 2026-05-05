import rick.config as cfg
"""
Modulo di Ottimizzazione (Agent-Lightning Hook)

Analizza i trace generati dal sistema per trovare gli errori corretti dall'Auditor.
Genera "Linee Guida" permanenti per OGNI ESPERTO affinché non ripeta l'errore.

NOVITÀ v9:
- Supporta TUTTI gli esperti (coder, researcher, pentester, sysadmin, etc.)
- Genera <skill>_guidelines.txt dinamicamente
- Evita duplicati confrontando contenuto, non hint
"""
import json
import logging
import hashlib
from pathlib import Path
from rick.config import DATA_DIR, PROMPTS_DIR, MODEL_MANAGER, EXPERTS
from rick.llm.client import llm_generate

logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("optimizer")

_SYSTEM_OPTIMIZER = (
    "Sei un AI Optimizer. Il tuo scopo è analizzare un errore fatto da un esperto AI "
    "e la correzione richiesta da un Auditor. Devi estrarre UNA SINGOLA REGOLA GENERALE, "
    "chiara e concisa (max 2 frasi), che l'esperto dovrà seguire in futuro per non "
    "ripetere lo stesso errore.\n\n"
    "Esempio buono: 'Evita rm -rf /tmp/*, usa trap per pulire file temporanei specifici.'\n"
    "Esempio cattivo: 'Il codice è sbagliato, correggilo.' (troppo generico)"
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


def _get_guidelines_path(skill: str) -> Path:
    """Ritorna il path del file guidelines per un dato skill."""
    return PROMPTS_DIR / f"{skill}_guidelines.txt"


def _load_existing_guidelines(skill: str) -> set[str]:
    """
    Carica le guidelines esistenti per un skill e ritorna un set di hash.
    Questo permette di evitare duplicati logici (non solo testuali).
    """
    path = _get_guidelines_path(skill)
    if not path.exists():
        return set()
    
    content = path.read_text(encoding="utf-8")
    # Ogni guideline è una linea che inizia con "- "
    guidelines = [
        line.strip()[2:].strip() 
        for line in content.split('\n') 
        if line.strip().startswith('- ')
    ]
    
    # Hash di ogni guideline per deduplica semantica
    return {hashlib.md5(g.encode()).hexdigest()[:8] for g in guidelines}


def _save_guideline(skill: str, lesson: str):
    """Appende una nuova guideline al file dell'esperto."""
    path = _get_guidelines_path(skill)
    
    # Crea il file se non esiste
    if not path.exists():
        path.write_text(
            f"# Linee guida per {skill}\n"
            "# Generate automaticamente da Agent-Lightning\n"
            "# NON ripetere questi errori:\n\n",
            encoding="utf-8"
        )
    
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"- {lesson}\n")


def extract_lessons() -> dict[str, list[str]]:
    """
    Trova le interazioni dove l'Auditor ha generato un retry e impara la lezione.
    
    Returns:
        dict[skill, list[lessons]]: Lezioni apprese per ogni esperto
    """
    sessions = _load_traces()
    lessons_by_skill: dict[str, list[str]] = {}
    
    # Carica guidelines esistenti per ogni skill
    existing_hashes_by_skill = {
        skill: _load_existing_guidelines(skill)
        for skill in EXPERTS.keys()
    }

    for session in sessions:
        # Trova coppie (expert_dispatcher → auditor retry)
        for i, node_data in enumerate(session):
            # L'auditor segna l'errore
            if node_data.get("node") == "auditor" and node_data.get("data"):
                data = node_data["data"]
                
                if data.get("verdict") != "retry":
                    continue
                
                # Cerca il nodo expert_dispatcher precedente
                skill = None
                draft = ""
                
                for j in range(i - 1, -1, -1):
                    prev_node = session[j]
                    if prev_node.get("node", "").startswith("expert_dispatcher"):
                        # Estrai skill dal nome nodo: "expert_dispatcher[researcher]"
                        node_name = prev_node.get("node", "")
                        if "[" in node_name and "]" in node_name:
                            skill = node_name.split("[")[1].split("]")[0]
                        draft = prev_node.get("data", {}).get("final_draft", "")
                        break
                
                if not skill or skill not in EXPERTS:
                    continue
                
                # Estrai info dall'audit
                issues = data.get("issues", [])
                hint = data.get("fix_hint", data.get("audit_notes", ""))
                
                # Genera lesson con LLM
                prompt = (
                    f"L'esperto '{skill}' ha prodotto questo output con errori:\n"
                    f"{draft[:1000]}\n\n"
                    f"Problemi riscontrati dall'Auditor: {issues}\n"
                    f"Suggerimento dell'Auditor: {hint}\n\n"
                    "Genera una REGOLA BREVE (max 2 frasi) da aggiungere alle linee guida "
                    f"per l'esperto '{skill}'. NON spiegare, scrivi solo la regola imperativa."
                )
                
                logger.info(f"Trovato errore per '{skill}'. Estrazione lezione...")
                
                lesson = llm_generate(
                    provider=cfg.PROVIDER_MANAGER,
                    model=MODEL_MANAGER,
                    prompt=prompt,
                    system=_SYSTEM_OPTIMIZER,
                    temperature=0.2,
                    keep_alive="0"
                )
                
                if not lesson or len(lesson) > 250:
                    continue
                
                # Check duplicati con hash
                lesson_hash = hashlib.md5(lesson.encode()).hexdigest()[:8]
                
                if lesson_hash in existing_hashes_by_skill[skill]:
                    logger.info(f"  → Lezione già presente per '{skill}', skip")
                    continue
                
                # Salva
                _save_guideline(skill, lesson)
                existing_hashes_by_skill[skill].add(lesson_hash)
                
                # Track
                if skill not in lessons_by_skill:
                    lessons_by_skill[skill] = []
                lessons_by_skill[skill].append(lesson)
                
                logger.info(f"  ✅ Nuova lezione per '{skill}': {lesson[:60]}...")
    
    # Summary
    total_lessons = sum(len(v) for v in lessons_by_skill.values())
    if total_lessons > 0:
        logger.info(f"Agent-Lightning: Apprese {total_lessons} nuove lezioni!")
        for skill, lessons in lessons_by_skill.items():
            logger.info(f"  → {skill}: {len(lessons)} lezioni")
    else:
        logger.info("Agent-Lightning: Nessuna nuova lezione da imparare.")
    
    return lessons_by_skill


if __name__ == "__main__":
    logger.info("Avvio Agent-Lightning Optimizer...")
    extract_lessons()
