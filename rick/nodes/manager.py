"""
Nodo MANAGER v3 — cache deterministica per risposte già note.
"""
import json
import logging
import time
from pydantic import BaseModel, Field, ValidationError
from rick.state import RickState
from rick.config import MODEL_MANAGER, PROMPTS_DIR, EXPERTS
from rick.llm.client import llm_generate

logger = logging.getLogger(__name__)

class ManagerOutput(BaseModel):
    intent: str = ""
    skills_needed: list[str] = Field(default_factory=list)
    plan: list[dict] = Field(default_factory=list)

def _build_experts_list() -> str:
    lines = []
    for skill, cfg in EXPERTS.items():
        lines.append(f"ID: '{skill}' -> desc: {cfg['description']}")
    return "\n".join(lines)

def _load_system_prompt(user_input: str) -> str:
    from rick.memory import get_recent_memories
    memory_context = get_recent_memories(user_input) or "Nessun ricordo."
    template = (PROMPTS_DIR / "manager.md").read_text(encoding="utf-8")
    template = template.replace("{EXPERTS_LIST}", _build_experts_list())
    template += f"\n\n**MEMORIA ATTUALE (fatti verificati e ricordi):**\n{memory_context}"
    return template

def _check_memory_cache(user_input: str) -> str | None:
    """Controlla se la memoria contiene già la risposta cercata."""
    from rick.memory import get_recent_memories
    memories = get_recent_memories(user_input)
    if not memories:
        return None

    lower = user_input.lower()
    # Adattato al formato esatto dei fatti salvati dal validator: "Versione rilevata: X.Y.Z"
    if "versione" in lower and "python" in lower:
        for line in memories.splitlines():
            if "Versione rilevata:" in line or "Versione Python" in line:
                return line.split("]:", 1)[-1].strip().split(":")[-1].strip()
    if "os" in lower or "sistema operativo" in lower:
        for line in memories.splitlines():
            if "fedora" in line.lower() or "ubuntu" in line.lower():
                return line.split("]:", 1)[-1].strip()
    return None

def _fallback_plan(user_input: str) -> dict:
    first_skill = next(iter(EXPERTS), "coder")
    return {
        "intent":        "unparsed",
        "skills_needed": [first_skill],
        "plan":          [{"step": 1, "task": user_input, "skill": first_skill}],
    }

def _parse_json(text: str) -> dict | None:
    clean = text.strip()
    if "```json" in clean:
        clean = clean.split("```json")[1].split("```")[0].strip()
    elif "```" in clean:
        clean = clean.split("```")[1].split("```")[0].strip()
    try:
        raw = json.loads(clean)
        return ManagerOutput.model_validate(raw).model_dump()
    except (json.JSONDecodeError, ValidationError):
        return None

def manager_node(state: RickState) -> dict:
    t0 = time.time()
    user_input = state["user_input"]

    # ═══ CACHE DETERMINISTICA ═══
    cached = _check_memory_cache(user_input)
    if cached:
        logger.info(f"[manager] RISPOSTA IN CACHE: {cached}")
        return {
            "intent":         "Risposta diretta dalla memoria",
            "skills_needed":  [],
            "plan":           [],
            "final_draft":    f"La versione installata di Python è {cached}.",
            "trace": [{
                "node":        "manager",
                "ts":          time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "duration_ms": 0,
                "model":       "cache",
                "input_keys":  ["user_input"],
                "output_keys": ["intent", "skills_needed", "plan"],
            }],
        }

    system = _load_system_prompt(user_input)
    logger.info(f"[manager] elaboro: {user_input[:80]!r}")

    raw = llm_generate(
        provider="ollama",
        model=MODEL_MANAGER,
        prompt=user_input,
        system=system,
        temperature=0.1,
        keep_alive="5m",
    )

    parsed = _parse_json(raw)
    if parsed is None:
        logger.warning("[manager] JSON malformato, retry...")
        raw2 = llm_generate(
            provider="ollama",
            model=MODEL_MANAGER,
            prompt=f"Rispondi SOLO con JSON valido.\n\nRichiesta: {user_input}",
            system=system,
            temperature=0.1,
            keep_alive="5m",
        )
        parsed = _parse_json(raw2)

    if parsed is None:
        logger.error("[manager] fallback plan attivato")
        parsed = _fallback_plan(user_input)

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