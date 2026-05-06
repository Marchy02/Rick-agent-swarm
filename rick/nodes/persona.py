"""
Nodo PERSONA — Applica lo stile Rick Sanchez (C-137) alla risposta finale.
Protegge i blocchi di codice tramite placeholder per evitarne la corruzione.
Include gestione del draft vuoto (risposta conversazionale diretta o da memoria).
"""
import re
import logging
from rick.state import RickState
from rick.llm.client import llm_generate
from rick.config import PROMPTS_DIR, CODE_PLACEHOLDER_PREFIX, CODE_PLACEHOLDER_SUFFIX, MODEL_PERSONA, PERSONA_IRONY

logger = logging.getLogger(__name__)

_CODE_FENCE_RE = re.compile(r"```[\s\S]*?```")


def _extract_code_blocks(text: str) -> tuple[str, list[str]]:
    """Estrae i blocchi di codice e li sostituisce con placeholder."""
    blocks = _CODE_FENCE_RE.findall(text)
    sanitized = text
    for i, block in enumerate(blocks):
        placeholder = f"{CODE_PLACEHOLDER_PREFIX}{i}{CODE_PLACEHOLDER_SUFFIX}"
        sanitized = sanitized.replace(block, placeholder, 1)
    return sanitized, blocks


def _restore_code_blocks(text: str, blocks: list[str]) -> str:
    """Ripristina i blocchi di codice originali al posto dei placeholder."""
    for i, block in enumerate(blocks):
        placeholder = f"{CODE_PLACEHOLDER_PREFIX}{i}{CODE_PLACEHOLDER_SUFFIX}"
        text = text.replace(placeholder, block, 1)
    
    # Fallback: se il placeholder esatto è stato alterato dal modello, prova con una regex
    remaining = re.findall(
        re.escape(CODE_PLACEHOLDER_PREFIX) + r"\d+" + re.escape(CODE_PLACEHOLDER_SUFFIX), text
    )
    for match in remaining:
        try:
            idx = int(match[len(CODE_PLACEHOLDER_PREFIX):-len(CODE_PLACEHOLDER_SUFFIX)])
            if idx < len(blocks):
                text = text.replace(match, blocks[idx], 1)
        except Exception:
            pass
    return text


def persona_node(state: RickState) -> dict:
    """Trasforma la bozza tecnica in una risposta stile Rick C-137."""
    draft = state.get("final_draft", "")
    user_input = state.get("user_input", "")
    
    # ── CASO 1: nessuna bozza tecnica (conversazione diretta o errore) ─────
    if not draft.strip():
        from rick.memory import get_recent_memories
        mem = get_recent_memories(user_input)
        if mem:
            # Prova a estrarre un fatto rilevante dalla memoria
            first_line = mem.splitlines()[0]
            if first_line.startswith("[VERIFICATO"):
                fact = first_line.split("]:", 1)[-1].strip()
                draft = fact
            elif first_line.startswith("Versione"):
                draft = first_line
            else:
                draft = f"Rispondi direttamente a questa richiesta: {user_input}"
        else:
            draft = f"Rispondi direttamente a questa richiesta: {user_input}"

    # 1. Protezione codice (se ci sono blocchi)
    sanitized_draft, code_blocks = _extract_code_blocks(draft)

    # 2. Carica il system prompt di Rick
    system_path = PROMPTS_DIR / "persona_rick.md"
    system_prompt = system_path.read_text(encoding="utf-8") if system_path.exists() else "Sei Rick Sanchez."

    # 3. Costruisci il prompt utente
    from rick.irony import get_irony_level, get_irony_instructions
    effective_level = get_irony_level(PERSONA_IRONY, state)
    irony = get_irony_instructions(effective_level)
    
    prompt = (
        f"{irony}\n\n"
        f"USER_INPUT: {user_input}\n\n"
        f"BOZZA TECNICA:\n{sanitized_draft}\n"
    )

    # Memorie recenti (per i livelli alti)
    if effective_level >= 4:
        from rick.memory import get_recent_memories
        memories = get_recent_memories(user_input)
        if memories:
            prompt += f"\nMEMORIE RECENTI (usale per infierire se il livello è 5):\n{memories}\n"

    prompt += "MANTIENI I PLACEHOLDER ██RICK_CODE_N██ INTATTI."

    # ═══ AGGIUNTA IMPORTANTE ═══
    # Se la bozza contiene già una risposta definitiva (es. dalla cache),
    # impedisci a Rick di aggiungere comandi inutili
    if "versione installata" in draft.lower() or "già in memoria" in draft.lower():
        prompt += (
            "IMPORTANTE: La bozza sopra è una RISPOSTA DEFINITIVA già verificata.\n"
            "Non aggiungere comandi da eseguire. Non dire 'prova con questo comando'.\n"
            "Limitati a comunicare il dato con il tuo stile cinico.\n"
        )
    else:
        prompt += (
            "REGOLE: Sostituisci la bozza con la tua voce cinica. "
            "MANTIENI I PLACEHOLDER ██RICK_CODE_N██ ESATTAMENTE DOVE SONO. "
            "NON aggiungere codice non richiesto.\n"
        )

    # 4. Generazione
    rick_response = llm_generate(
        provider="ollama",
        model=MODEL_PERSONA,
        prompt=prompt,
        system=system_prompt,
        temperature=0.8,
    )

    # 5. Ripristino codice
    final_output = _restore_code_blocks(rick_response, code_blocks)

    # 6. Pulizia finale: rimuovi eventuali doppi backtick vuoti
    final_output = re.sub(r'```\s*```', '', final_output)

    logger.info("[persona] Risposta 'Rickizzata' con successo.")
    return {"final_response": final_output}