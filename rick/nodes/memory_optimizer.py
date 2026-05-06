"""
Nodo MEMORY OPTIMIZER
Responsabilità: estrarre fatti dalla conversazione e salvarli in memoria.

NOVITÀ v9:
- Salva SOLO se audit_verdict == "pass" (niente allucinazioni in memoria)
- Distingue tra fatti verificati e fatti inferiti
- Agent-Lightning rimosso (ora in optimize.py standalone)
"""
import logging
import time
from rick.state import RickState
from rick.config import MODEL_MANAGER
from rick.llm.client import ollama_generate
from rick.memory import save_memory

logger = logging.getLogger(__name__)


def memory_optimizer_node(state: RickState) -> dict:
    t0 = time.time()
    user_input = state["user_input"]
    final_response = state.get("final_response", "")
    audit_verdict = state.get("audit_verdict", "unknown")
    
    # ══════════════════════════════════════════════════════════════════════
    # VALIDAZIONE PRE-SALVATAGGIO
    # ══════════════════════════════════════════════════════════════════════
    # Se l'audit non è passato, NON salvare niente in memoria.
    # Previene allucinazioni, dati inventati, e output non verificati.
    if audit_verdict != "pass":
        logger.info(
            f"[memory_optimizer] Skip (audit_verdict={audit_verdict}). "
            "Salvo SOLO conversazioni validate."
        )
        return {}
    
    # ══════════════════════════════════════════════════════════════════════
    # ESTRAZIONE FATTI
    # ══════════════════════════════════════════════════════════════════════
    # Skip solo se è veramente una chiacchiera vuota
    # Se la RISPOSTA contiene info tecniche (OS, versioni, path), salva sempre
    has_technical_info = any(
        kw in final_response.lower() 
        for kw in ["fedora", "ubuntu", "windows", "kernel", "version", "python", "node", "dual boot"]
    )
    
    # Euristica: skip solo se query breve E risposta generica
    if len(user_input) < 10 and not has_technical_info:
        logger.info("[memory_optimizer] Skip (chiacchiera)")
        return {}
    
    # Prompt per estrazione fatti
    prompt = f"""Analizza questa conversazione. Estrai fatti persistenti sull'utente.

REGOLE:
1. Se fornisce dettagli tecnici (OS, hardware, software, path, versioni), ESTRAILI.
2. Se usa parole come "ricorda", "ho un...", "uso...", "preferisco", ESTRAI.
3. Se è solo chiacchiera, domanda generica o richiesta one-off, rispondi "NIENTE".
4. Scrivi fatti in terza persona: "Marco usa Python 3.11" non "uso Python 3.11".
5. Un fatto per riga, max 3 fatti.

User: {user_input}
Rick: {final_response}

Fatti da ricordare:"""
    
    logger.info("[memory_optimizer] Valuto la conversazione per estrazione fatti...")
    
    fact = ollama_generate(
        model=MODEL_MANAGER,
        prompt=prompt,
        system="Sei l'ottimizzatore della memoria. Sii spietatamente conciso.",
        temperature=0.1,
        keep_alive="0"
    ).strip()
    
    elapsed_ms = round((time.time() - t0) * 1000)
    
    if "NIENTE" in fact.upper() or len(fact) < 10:
        logger.info(f"[memory_optimizer] Nessun fatto rilevante ({elapsed_ms}ms)")
    else:
        # Confidence score basato sul contenuto
        # Fatti con numeri/versioni/path hanno confidence più alta
        confidence = 0.7
        if any(char.isdigit() for char in fact):
            confidence = 0.85
        if "/" in fact or "\\" in fact:  # path
            confidence = 0.9
        
        logger.info(
            f"[memory_optimizer] Fatto estratto (confidence={confidence}): "
            f"{fact[:60]}... ({elapsed_ms}ms)"
        )
        save_memory(user_input, fact, confidence=confidence)
    
    return {}
