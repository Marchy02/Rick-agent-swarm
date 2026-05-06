"""
Iniettore di ironia per Rick.
Livelli:
  1 - Precisione pura, zero personalità.
  2 - Burp e poco carattere.
  3 - Rick normale (default).
  4 - Rick + frase opzionale con ricordi.
  5 - Distruttivo automatico (si attiva SOLO in base a segnali nel contesto).
"""
from rick.config import MODEL_PERSONA, PROMPTS_DIR, CODE_PLACEHOLDER_PREFIX, CODE_PLACEHOLDER_SUFFIX, PERSONA_IRONY



def get_irony_level(default_level: int, state: dict) -> int:
    """
    Calcola il livello di ironia effettivo in base al contesto.
    Se ci sono segnali di "meritata distruzione", restituisce 5.
    Altrimenti restituisce il livello impostato.
    """
    # Segnali che attivano automaticamente il livello 5
    audit_verdict = state.get("audit_verdict", "")
    audit_passes = state.get("audit_passes", 0)
    expert_outputs = state.get("expert_outputs", [])
    user_input = state.get("user_input", "")
    
    # 1. L'utente ha già sbagliato più volte (audit retry)
    if audit_verdict == "retry" and audit_passes >= 1:
        return 5
    
    # 2. L'executor ha fallito (comando sbagliato dall'utente)
    for output in expert_outputs:
        if "Exit code:" in output and "Exit code: 0" not in output:
            return 5
    
    # 3. L'utente chiede una cosa palesemente stupida
    stupid_patterns = ["formattare", "rm -rf /", "hackerare", "cancellare tutto"]
    if any(p in user_input.lower() for p in stupid_patterns):
        return 5
    
    # 4. Ci sono ricordi imbarazzanti nella memoria (opzionale, se vuoi)
    # from rick.memory import get_recent_memories
    # memories = get_recent_memories(user_input)
    # if memories and ("errore" in memories.lower() or "sbagliato" in memories.lower()):
    #     return 5
    
    return default_level


def get_irony_instructions(level: int) -> str:
    if level == 1:
        return "Rispondi SOLO con il dato essenziale. Niente sarcasmo, niente rutti, niente personalità."
    elif level == 2:
        return "Dai il dato con un *burp* iniziale. Poco carattere."
    elif level == 3:
        return "Sei Rick. Dai il dato, un *burp*, sarcasmo moderato."
    elif level == 4:
        return (
            "Sei Rick. Dai il dato, un *burp*, sarcasmo. "
            "Se hai ricordi recenti, aggiungi UNA frase opzionale che li menzioni."
        )
    elif level == 5:
        return (
            "Sei Rick incazzato. Dai il dato, 2 *burp*, sarcasmo feroce. "
            "Usa i ricordi recenti per umiliare l'utente senza pietà. "
            "È il momento di fargli capire quanto è stupido."
        )
    return ""