"""
Nodo PERSONA (filtro Rick)
Responsabilità: riscrivere final_draft in voce Rick Sanchez.
Modello: qwen2.5:7b, temp 0.8
Bypass totale se persona_intensity == 0.

Protezione codice: estrae i blocchi ```...``` PRIMA, li rimette DOPO
il passaggio attraverso Rick — garantisce che il codice non venga modificato.
"""
import logging
import re
import time
from rick.state import RickState
from rick.config import MODEL_PERSONA, PROMPTS_DIR, PERSONA_INTENSITY
from rick.llm.client import ollama_generate

logger = logging.getLogger(__name__)

_SYSTEM_BASE = (PROMPTS_DIR / "persona_rick.md").read_text(encoding="utf-8")

# Regex per trovare tutti i blocchi da proteggere:
# 1. Blocchi di codice Markdown (```...```)
# 2. Blocchi RISULTATO dell'Executor (── RISULTATO ... ──────────────────)
_CODE_FENCE_RE = re.compile(
    r"(```[\s\S]*?```|──[\s\S]*?──────────────────\n)",
    re.MULTILINE
)


def _extract_code_blocks(text: str) -> tuple[str, list[str]]:
    """Sostituisce i code block con placeholder __CODE_N__ e li restituisce."""
    blocks = _CODE_FENCE_RE.findall(text)
    sanitized = text
    for i, block in enumerate(blocks):
        sanitized = sanitized.replace(block, f"__CODE_{i}__", 1)
    return sanitized, blocks


def _restore_code_blocks(text: str, blocks: list[str]) -> str:
    """Reinserisce i code block originali al posto dei placeholder."""
    for i, block in enumerate(blocks):
        text = text.replace(f"__CODE_{i}__", block, 1)
    return text


def persona_node(state: RickState) -> dict:
    t0 = time.time()
    final_draft = state.get("final_draft", "")
    intensity   = PERSONA_INTENSITY

    # ── Bypass totale ──────────────────────────────────────────────────────────
    if intensity == 0:
        logger.info("[persona] bypass totale (intensity=0)")
        trace_entry = {
            "node": "persona",
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "duration_ms": 0,
            "model": "none (bypass)",
            "input_keys": ["final_draft"],
            "output_keys": ["final_response"],
        }
        return {
            "final_response": final_draft,
            "trace": [trace_entry],
        }

    # ── Personalizza system prompt in base all'intensità ─────────────────────
    if intensity == 1:
        system = _SYSTEM_BASE + "\nIntensità BASSA: max 1 menzione di Marco niente burp."
        temp   = 0.5
    else:  # intensity == 2
        system = _SYSTEM_BASE + "\nIntensità ALTA: burp e menzione Marco OBBLIGATORI almeno 1 volta."
        temp   = 0.8

    # Se non c'è una risposta tecnica (es. domanda fuori scope o chiacchierata), 
    # fai rispondere Rick direttamente all'input dell'utente.
    if not final_draft.strip():
        user_input = state.get("user_input", "")
        from rick.memory import get_recent_memories
        memories = get_recent_memories(user_input)
        
        prompt = (
            "Rispondi direttamente a questa richiesta dell'utente in stile Rick Sanchez.\n"
            "Non c'è nessuna risposta tecnica da riscrivere, rispondi e basta.\n"
        )
        if memories:
            prompt += f"\nMEMORIA CONTESTUALE (Fatti sull'utente):\n{memories}\n"
        
        prompt += f"\nRichiesta dell'utente: {user_input}"
        code_blocks = []
    else:
        # ── Proteggi i code block prima del passaggio a Rick ─────────────────────
        sanitized, code_blocks = _extract_code_blocks(final_draft)

        prompt_parts = [
            "Riscrivi questa risposta tecnica aggiungendo la voce di Rick Sanchez.",
            "REGOLA CRITICA: i placeholder __CODE_N__ contengono dati tecnici REALI "
            "(output nmap, risultati comandi, codice). NON modificarli, NON riscriverli, "
            "NON aggiungere testo al loro interno. Lasciali ESATTAMENTE come sono.",
            "Aggiungi solo una battuta di Rick all'inizio o alla fine della risposta.",
        ]
        from rick.memory import get_recent_memories
        memories = get_recent_memories(state.get("user_input", ""))
        if memories:
            prompt_parts.append(f"\nMEMORIA CONTESTUALE (Fatti che conosci sull'utente):\n{memories}")

        prompt_parts.append(f"\nBOZZA DA RISCRIVERE:\n{sanitized}")
        prompt = "\n".join(prompt_parts)

    raw = ollama_generate(
        model=MODEL_PERSONA,
        prompt=prompt,
        system=system,
        temperature=temp,
        keep_alive="0",
    )

    # ── Reinserisci i code block originali ────────────────────────────────────
    final_response = _restore_code_blocks(raw, code_blocks)

    elapsed_ms = round((time.time() - t0) * 1000)
    trace_entry = {
        "node": "persona",
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "duration_ms": elapsed_ms,
        "model": MODEL_PERSONA,
        "input_keys": ["final_draft"],
        "output_keys": ["final_response"],
    }

    logger.info(f"[persona] risposta {len(final_response)} chars ({elapsed_ms}ms)")

    return {
        "final_response": final_response,
        "trace": [trace_entry],
    }
