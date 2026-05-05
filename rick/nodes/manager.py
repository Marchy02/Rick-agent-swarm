"""
Nodo MANAGER
Responsabilità: analizzare user_input, produrre intent + skills_needed + plan.
Modello: qwen2.5:7b (piccolo e veloce, ottimizzato per JSON strutturato)

La lista degli esperti disponibili viene iniettata a runtime da EXPERTS in config.py:
basta aggiungere una voce lì e il manager la vedrà automaticamente al prossimo avvio.
"""
import json
import logging
import time
from rick.state import RickState
from rick.config import MODEL_MANAGER, PROMPTS_DIR, EXPERTS
from rick.llm.client import ollama_generate

logger = logging.getLogger(__name__)


def _build_experts_list() -> str:
    """Genera la lista testuale degli esperti da EXPERTS in config.py."""
    lines = []
    for skill, cfg in EXPERTS.items():
        lines.append(f"ID: '{skill}' -> desc: {cfg['description']}")
    return "\n".join(lines)


def _load_system_prompt() -> str:
    """Carica manager.md e sostituisce il placeholder {EXPERTS_LIST}."""
    template = (PROMPTS_DIR / "manager.md").read_text(encoding="utf-8")
    return template.replace("{EXPERTS_LIST}", _build_experts_list())


# Fallback usato quando il JSON è malformato dopo 1 retry
def _fallback_plan(user_input: str) -> dict:
    first_skill = next(iter(EXPERTS), "coder")
    return {
        "intent":        "unparsed",
        "skills_needed": [first_skill],
        "plan":          [{"step": 1, "task": user_input, "skill": first_skill}],
    }


def _parse_json(text: str) -> dict | None:
    """Pulisce fence markdown e tenta il parse JSON."""
    clean = text.strip()
    if "```json" in clean:
        clean = clean.split("```json")[1].split("```")[0].strip()
    elif "```" in clean:
        clean = clean.split("```")[1].split("```")[0].strip()
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        return None


def manager_node(state: RickState) -> dict:
    t0         = time.time()
    user_input = state["user_input"]
    system     = _load_system_prompt()

    logger.info(f"[manager] elaboro: {user_input[:80]!r}")

    raw = ollama_generate(
        model=MODEL_MANAGER,
        prompt=user_input,
        system=system,
        temperature=0.1,
        keep_alive="5m",
    )

    parsed = _parse_json(raw)

    # Retry se il JSON è malformato
    if parsed is None:
        logger.warning("[manager] JSON malformato, retry...")
        raw2 = ollama_generate(
            model=MODEL_MANAGER,
            prompt=f"Rispondi SOLO con JSON valido secondo lo schema.\n\nRichiesta: {user_input}",
            system=system,
            temperature=0.1,
            keep_alive="5m",
        )
        parsed = _parse_json(raw2)

    if parsed is None:
        logger.error("[manager] fallback plan attivato")
        parsed = _fallback_plan(user_input)

    # Filtra skills non registrate (sicurezza contro allucinazioni del modello)
    valid_skills = [s for s in parsed.get("skills_needed", []) if s in EXPERTS]
    if len(valid_skills) != len(parsed.get("skills_needed", [])):
        unknown = set(parsed.get("skills_needed", [])) - set(valid_skills)
        logger.warning(f"[manager] skill sconosciute ignorate: {unknown}")

    elapsed_ms = round((time.time() - t0) * 1000)
    trace_entry = {
        "node":        "manager",
        "ts":          time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "duration_ms": elapsed_ms,
        "model":       MODEL_MANAGER,
        "input_keys":  ["user_input"],
        "output_keys": ["intent", "skills_needed", "plan"],
    }

    logger.info(
        f"[manager] intent={parsed.get('intent','?')} "
        f"skills={valid_skills} ({elapsed_ms}ms)"
    )

    return {
        "intent":        parsed.get("intent", ""),
        "skills_needed": valid_skills,
        "plan":          parsed.get("plan", []),
        "trace":         [trace_entry],
    }
