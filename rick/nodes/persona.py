"""
Nodo PERSONA (filtro Rick) — Versione ottimizzata v10 (DeepSeek Refactor)
Responsabilità: riscrivere final_draft in voce Rick Sanchez.
"""
import logging
import re
import time
from rick.state import RickState
from rick.config import MODEL_PERSONA, PROMPTS_DIR, PERSONA_INTENSITY
from rick.llm.client import llm_generate

logger = logging.getLogger(__name__)

# ── Caricamento template ────────────────────────────────────────────────────
_SYSTEM_TEMPLATE = (PROMPTS_DIR / "persona_rick.md").read_text(encoding="utf-8")

# ── Regex per blocchi da proteggere ─────────────────────────────────────────
_CODE_FENCE_RE = re.compile(
    r"(```[^\n]*\n[\s\S]*?```|──\s+RISULTATO\s+[\s\S]*?──+\s*\n)",
    re.MULTILINE
)

# Placeholder univoci che NON possono apparire nel testo normale
_PLACEHOLDER_PREFIX = "<<<RICK_CODEBLOCK_"
_PLACEHOLDER_SUFFIX = ">>>"


def _extract_code_blocks(text: str) -> tuple[str, list[str]]:
    """Sostituisce i code block con placeholder univoci."""
    blocks = _CODE_FENCE_RE.findall(text)
    sanitized = text
    for i, block in enumerate(blocks):
        placeholder = f"{_PLACEHOLDER_PREFIX}{i}{_PLACEHOLDER_SUFFIX}"
        sanitized = sanitized.replace(block, placeholder, 1)
    return sanitized, blocks


def _restore_code_blocks(text: str, blocks: list[str]) -> str:
    """Reinserisce i code block originali al posto dei placeholder."""
    for i, block in enumerate(blocks):
        placeholder = f"{_PLACEHOLDER_PREFIX}{i}{_PLACEHOLDER_SUFFIX}"
        text = text.replace(placeholder, block, 1)
    
    # Controllo di integrità
    remaining = re.findall(re.escape(_PLACEHOLDER_PREFIX) + r"\d+" + re.escape(_PLACEHOLDER_SUFFIX), text)
    if remaining:
        logger.warning(f"[persona] {len(remaining)} placeholder rimasti dopo restore! Possibile corruzione codice.")
    
    return text


def _build_persona_system(intensity: int) -> str:
    """Costruisce il system prompt in base all'intensità."""
    base = _SYSTEM_TEMPLATE
    
    if intensity == 1:
        return base + "\n\nIntensità BASSA: max 1 menzione di Marco, niente burp. Sii sobrio ma riconoscibile."
    elif intensity >= 2:
        return base + "\n\nIntensità ALTA: burp e menzione Marco OBBLIGATORI almeno 1 volta. Puoi esagerare un po'."
    return base


def _build_user_prompt(
    user_input: str,
    draft: str,
    memories: str | None = None,
    audit_report: str | None = None,
) -> str:
    """Costruisce il prompt utente da passare a Rick."""
    lines = []
    
    if draft.strip():
        lines.append("**BOZZA TECNICA DA RICKIZZARE:**")
        lines.append(draft)
    else:
        lines.append(f"**RICHIESTA UTENTE:** {user_input}")
    
    extra_parts = []
    if memories:
        extra_parts.append(f"**Memoria utente:**\n{memories}")
    if audit_report:
        extra_parts.append(f"**Audit report:** {audit_report}")
    
    if extra_parts:
        lines.append("\n**CONTESTO AGGIUNTIVO:**")
        lines.extend(extra_parts)
    
    return "\n\n".join(lines)


def persona_node(state: RickState) -> dict:
    t0 = time.time()
    final_draft = state.get("final_draft", "")
    intensity = PERSONA_INTENSITY

    # ── Bypass totale ──────────────────────────────────────────────────────
    if intensity == 0:
        logger.info("[persona] bypass totale (intensity=0)")
        return {
            "final_response": final_draft,
            "trace": [{
                "node": "persona",
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "duration_ms": 0,
                "model": "none (bypass)",
                "input_keys": ["final_draft"],
                "output_keys": ["final_response"],
            }],
        }

    # ── Preparazione contesto ──────────────────────────────────────────────
    user_input = state.get("user_input", "")
    
    # Lazy loading memoria
    from rick.memory import get_recent_memories
    memories = get_recent_memories(user_input) or "Nessun ricordo rilevante."
    
    audit_report = state.get("audit_report", "")

    # Draft da usare
    if not final_draft.strip():
        logger.info("[persona] Nessun draft, risposta conversazionale diretta")
        draft_to_use = f"[L'utente ha detto: '{user_input}'. Rispondi direttamente a questa richiesta.]"
    else:
        draft_to_use = final_draft

    # ── Protezione codice ──────────────────────────────────────────────────
    sanitized, code_blocks = _extract_code_blocks(draft_to_use)
    if code_blocks:
        logger.info(f"[persona] Protetti {len(code_blocks)} blocchi codice/risultato")
    
    # ── Prompt e sistema separati ──────────────────────────────────────────
    system = _build_persona_system(intensity)
    user_prompt = _build_user_prompt(
        user_input=user_input,
        draft=sanitized,
        memories=memories,
        audit_report=audit_report,
    )
    
    # Temperatura in base all'intensità
    temp = 0.5 if intensity == 1 else 0.8

    logger.info(f"[persona] Chiamata LLM (intensity={intensity}, temp={temp})")
    
    raw = llm_generate(
        provider="ollama",
        model=MODEL_PERSONA,
        prompt=user_prompt,
        system=system,
        temperature=temp,
        keep_alive="0",
    )

    # ── Ripristino codice ──────────────────────────────────────────────────
    final_response = _restore_code_blocks(raw, code_blocks)

    elapsed_ms = round((time.time() - t0) * 1000)
    
    logger.info(f"[persona] Risposta generata: {len(final_response)} chars ({elapsed_ms}ms)")
    if code_blocks:
        n_restored = len(_CODE_FENCE_RE.findall(final_response))
        if n_restored != len(code_blocks):
            logger.error(
                f"[persona] DISCREPANZA BLOCCHI: "
                f"attesi {len(code_blocks)}, trovati {n_restored} dopo restore!"
            )

    return {
        "final_response": final_response,
        "trace": [{
            "node": "persona",
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "duration_ms": elapsed_ms,
            "model": MODEL_PERSONA,
            "input_keys": ["final_draft"],
            "output_keys": ["final_response"],
        }],
    }
