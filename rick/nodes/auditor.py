"""
Nodo AUDITOR
Responsabilità: verificare final_draft contro il plan.
Emette verdict: "pass" | "retry" | "fail" + fix_hint.
Modello: qwen2.5:7b (stesso del manager — risparmia swap)
"""
import json
import logging
import time
from rick.state import RickState
from rick.config import MODEL_AUDITOR, PROMPTS_DIR, MAX_AUDIT_RETRIES
from rick.llm.client import ollama_generate

logger = logging.getLogger(__name__)

_SYSTEM = (PROMPTS_DIR / "auditor.md").read_text(encoding="utf-8")


def _parse_verdict(text: str) -> dict | None:
    clean = text.strip()
    if "```json" in clean:
        clean = clean.split("```json")[1].split("```")[0].strip()
    elif "```" in clean:
        clean = clean.split("```")[1].split("```")[0].strip()
    # Cerca il primo oggetto JSON nella risposta
    start = clean.find("{")
    end   = clean.rfind("}") + 1
    if start != -1 and end > start:
        try:
            return json.loads(clean[start:end])
        except json.JSONDecodeError:
            pass
    return None


def auditor_node(state: RickState) -> dict:
    t0 = time.time()
    plan         = state.get("plan", [])
    final_draft  = state.get("final_draft", "")
    audit_passes = state.get("audit_passes", 0)

    # ── Cap retry: forza pass se siamo già al limite ──────────────────────────
    if audit_passes >= MAX_AUDIT_RETRIES:
        logger.warning(f"[auditor] cap retry ({MAX_AUDIT_RETRIES}) raggiunto → forzo pass")
        trace_entry = {
            "node": "auditor",
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "duration_ms": 0,
            "model": "none (cap)",
            "input_keys": ["plan", "final_draft"],
            "output_keys": ["audit_verdict"],
        }
        return {
            "audit_verdict":  "pass",
            "audit_notes":    state.get("audit_notes"),
            "audit_passes":   audit_passes + 1,
            "current_step":   0,   # reset per eventuale nuovo ciclo
            "executor_passes": 0,  # reset cap executor
            "trace":          [trace_entry],
        }

    prompt = (
        f"PLAN:\n{json.dumps(plan, indent=2, ensure_ascii=False)}\n\n"
        f"DRAFT:\n{final_draft}"
    )

    raw = ollama_generate(
        model=MODEL_AUDITOR,
        prompt=prompt,
        system=_SYSTEM,
        temperature=0.1,
        keep_alive="5m",
    )

    parsed = _parse_verdict(raw)
    if parsed is None:
        logger.warning("[auditor] JSON malformato → forzo pass")
        parsed = {"verdict": "pass", "issues": [], "fix_hint": None}

    verdict   = parsed.get("verdict", "pass")
    issues    = parsed.get("issues", [])
    fix_hint  = parsed.get("fix_hint")

    elapsed_ms = round((time.time() - t0) * 1000)
    trace_entry = {
        "node": "auditor",
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "duration_ms": elapsed_ms,
        "model": MODEL_AUDITOR,
        "input_keys": ["plan", "final_draft"],
        "output_keys": ["audit_verdict", "audit_notes"],
        "data": {
            "draft": final_draft,
            "verdict": verdict,
            "issues": issues,
            "fix_hint": fix_hint
        } if verdict == "retry" else None
    }

    logger.info(
        f"[auditor] verdict={verdict} issues={len(issues)} ({elapsed_ms}ms)"
    )

    return {
        "audit_verdict":  verdict,
        "audit_notes":    fix_hint if verdict == "retry" else None,
        "audit_passes":   audit_passes + 1,
        "current_step":   0 if verdict == "retry" else state.get("current_step", 0),
        "executor_passes": 0 if verdict == "retry" else state.get("executor_passes", 0),
        "trace":          [trace_entry],
    }
