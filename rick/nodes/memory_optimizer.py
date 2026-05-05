import logging
import time
from rick.state import RickState
from rick.config import MODEL_MANAGER, PROMPTS_DIR
from rick.llm.client import ollama_generate
from rick.memory import save_memory

logger = logging.getLogger(__name__)

def _learn_from_mistakes(state: RickState):
    """Analizza se l'Auditor ha richiesto correzioni e genera linee guida permanenti."""
    # Cerchiamo se c'è stato un retry dell'auditor o se l'auditor ha fallito
    if state.get("audit_passes", 0) > 0:
        notes = state.get("audit_notes", "")
        draft = state.get("final_draft", "")
        skills = state.get("skills_needed", [])
        
        if not notes or not skills:
            return

        skill = skills[0]
        guidelines_file = PROMPTS_DIR / f"{skill}_guidelines.txt"
        
        prompt = (
            f"L'esperto '{skill}' ha fatto questo errore:\n{draft[:500]}\n\n"
            f"L'Auditor ha corretto così: {notes}\n\n"
            "Estrai una REGOLA GENERALE e IMPERATIVA (max 15 parole) per evitare questo errore in futuro. "
            "NON spiegare, scrivi solo la regola."
        )
        
        logger.info(f"[memory_optimizer] Agent-Lightning: estrazione lezione per {skill}...")
        lesson = ollama_generate(
            model=MODEL_MANAGER,
            prompt=prompt,
            system="Sei un AI Optimizer. Scrivi regole tecniche brevi e ferree.",
            temperature=0.1,
            keep_alive="0"
        ).strip().replace("- ", "")

        if lesson and len(lesson) > 5:
            with open(guidelines_file, "a", encoding="utf-8") as f:
                f.write(f"- {lesson}\n")
            logger.info(f"[memory_optimizer] Nuova linea guida salvata per {skill}: {lesson}")

def memory_optimizer_node(state: RickState) -> dict:
    t0 = time.time()
    user_input = state["user_input"]
    final_response = state.get("final_response", "")

    # 1. Agent-Lightning: Impara dagli errori tecnici
    try:
        _learn_from_mistakes(state)
    except Exception as e:
        logger.error(f"[memory_optimizer] Errore durante l'apprendimento: {e}")

    # 2. Memoria Semantica: Estrai fatti sull'utente
    # Euristica veloce per evitare chiamate LLM inutili
    keywords = ["ricorda", "tieni a mente", "ho un", "uso", "preferisco", "sempre", "mai", "configur", "path", "cartella"]
    if len(user_input) < 15 and not any(kw in user_input.lower() for kw in keywords):
        logger.info("[memory_optimizer] fatti: skip (euristica veloce)")
        return {}

    prompt = f"""
Analizza questa conversazione. Estrai fatti persistenti su Marco.
REGOLE:
1. Se fornisce dettagli tecnici (OS, hardware, software, path), ESTRAILI.
2. Se usa "ricorda", "ho un...", "uso...", ESTRAI.
3. Se è solo chiacchiera, rispondi "NIENTE".

User: {user_input}
Rick: {final_response}
"""
    logger.info("[memory_optimizer] valuto la conversazione per l'estrazione di fatti...")
    
    fact = ollama_generate(
        model=MODEL_MANAGER,
        prompt=prompt,
        system="Sei l'ottimizzatore della memoria. Sii spietatamente conciso.",
        temperature=0.1,
        keep_alive="0"
    ).strip()
    
    elapsed_ms = round((time.time() - t0) * 1000)
    
    if "NIENTE" in fact.upper():
        logger.info(f"[memory_optimizer] fatti: scartata ({elapsed_ms}ms)")
    else:
        logger.info(f"[memory_optimizer] fatto estratto: {fact} ({elapsed_ms}ms)")
        save_memory(user_input, fact)
        
    return {}
