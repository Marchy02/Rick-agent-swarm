"""
Memory optimizer — filtra input banali prima di chiamare LLM.
"""
from rick.state import RickState
from rick.llm.client import call_llm
from rick.memory import save_memory
import logging

logger = logging.getLogger(__name__)

# Input banali da skippare senza chiamare LLM
TRIVIAL_PATTERNS = [
    "ciao", "hello", "hi", "hey", "salve",
    "come va", "come stai", "tutto bene",
    "grazie", "thanks", "ok", "va bene",
    "cosa puoi fare", "aiutami", "help"
]


def is_trivial(text: str) -> bool:
    """Check se input è troppo banale per estrarre fatti."""
    text_lower = text.lower().strip()
    
    # Input molto corti
    if len(text_lower.split()) <= 3:
        return True
    
    # Match con pattern banali
    for pattern in TRIVIAL_PATTERNS:
        if pattern in text_lower:
            return True
    
    return False


def memory_optimizer_node(state: RickState) -> dict:
    """
    Estrae fatti rilevanti dall'input utente.
    Salta chiamata LLM se input è banale.
    """
    user_input = state.get("user_input", "")
    
    # Pre-filter: skippa input banali
    if is_trivial(user_input):
        logger.info("[memory] Trivial input, skipping extraction")
        return {}
    
    # Estrazione fatti solo se input è sostanziale
    prompt = f"""Estrai SOLO fatti importanti da ricordare sul lungo termine dall'input dell'utente.

Input: {user_input}

Se ci sono fatti importanti (preferenze, informazioni personali, progetti, obiettivi), elencali in modo conciso.
Se non c'è nulla di rilevante, rispondi SOLO con: NIENTE

Esempi:
Input: "Mi piace Python e odio JavaScript"
Output: Preferenze: Python (positivo), JavaScript (negativo)

Input: "Sto lavorando a un progetto di ML con FastAPI"
Output: Progetto attuale: ML con FastAPI

Input: "Dammi una lista di comandi bash"
Output: NIENTE
"""
    
    try:
        response = call_llm(prompt, model="qwen2.5:7b", temperature=0.3, timeout=20)
        logger.info(f"[memory] Extracted: {response[:100]}...")
        
        # Salva solo se c'è qualcosa di rilevante
        if response and "NIENTE" not in response.upper():
            save_memory(user_input, response)
        
        return {}
        
    except Exception as e:
        logger.error(f"[memory] Extraction error: {e}")
        return {}
