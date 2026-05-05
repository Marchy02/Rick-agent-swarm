"""
Nodo EXPERT DISPATCHER
Responsabilità: eseguire UN esperto alla volta, in base a current_step.

Pipeline sequenziale:
  skills = ["pentester", "researcher", "coder"]
  giro 1 → pentester esegue, ottiene sandbox output, finalizza
  giro 2 → researcher legge output del pentester, esegue, finalizza
  giro 3 → coder legge tutto il contesto, scrive l'exploit
  → auditor

Ogni esperto vede tutti gli output precedenti nel proprio contesto.
"""
import json
import logging
import time
from rick.state import RickState
from rick.config import EXPERTS, PROMPTS_DIR
from rick.llm.client import llm_generate
from sandbox import extract_commands

logger = logging.getLogger(__name__)


def _build_prompt(state: RickState, skill: str) -> str:
    """Costruisce il prompt utente per un dato esperto.
    
    PRIORITÀ: Se ci sono risultati dell'executor, li mette IN CIMA
    con enfasi visiva per forzare il modello a usarli.
    """
    user_input  = state["user_input"]
    plan        = state.get("plan", [])
    audit_notes = state.get("audit_notes")
    step        = state.get("current_step", 0)
    skills      = state.get("skills_needed", [])
    all_outputs = state.get("expert_outputs", [])
    
    # Separa risultati executor da output esperti
    executor_results = [o for o in all_outputs if "── RISULTATO" in o]
    expert_outputs   = [o for o in all_outputs if "── RISULTATO" not in o]
    
    parts = []
    
    # ═══ SE CI SONO RISULTATI EXECUTOR, METTERLI IN CIMA ═══
    if executor_results:
        parts.append("═" * 70)
        parts.append("⚠️  HAI ESEGUITO COMANDI. QUESTI SONO I RISULTATI REALI:")
        parts.append("═" * 70)
        for res in executor_results:
            parts.append(res)
        parts.append("═" * 70)
        parts.append("📌 USA SOLO I DATI SOPRA. NON INVENTARE NULLA.")
        parts.append("═" * 70)
        parts.append("")  # linea vuota
    
    # Task originale
    parts.append(f"TASK ORIGINALE: {user_input}")
    parts.append(f"IL TUO RUOLO: {skill} (passo {step+1}/{len(skills)})")
    
    # Piano
    skill_tasks = [t for t in plan if t.get("skill") == skill] or plan
    parts.append(f"\nPLAN: {json.dumps(skill_tasks, ensure_ascii=False)}")
    
    # Lessons learned
    guidelines_path = PROMPTS_DIR / f"{skill}_guidelines.txt"
    if guidelines_path.exists():
        lessons = guidelines_path.read_text(encoding="utf-8").strip()
        if lessons:
            parts.append(f"\nLESSONS LEARNED (NON ripetere questi errori):\n{lessons}")
    
    # Audit notes (se retry)
    if audit_notes:
        parts.append(f"\n⚠️ AUDIT_NOTES (correggi questi problemi):\n{audit_notes}")
    
    # Output esperti precedenti (contesto)
    if expert_outputs:
        parts.append("\n--- OUTPUT ESPERTI PRECEDENTI ---")
        for out in expert_outputs[-3:]:  # ultimi 3 per non appesantire
            parts.append(out[:500])  # trunca se troppo lungo
    
    # Memoria semantica
    from rick.memory import get_recent_memories
    memories = get_recent_memories(user_input)
    if memories:
        parts.append(f"\n--- MEMORIA SEMANTICA ---\n{memories}")
    
    return "\n\n".join(parts)


def expert_dispatcher_node(state: RickState) -> dict:
    t0        = time.time()
    skills    = state.get("skills_needed", [])
    step      = state.get("current_step", 0)
    new_trace = []

    if not skills:
        logger.info("[dispatcher] nessun skill richiesto, skip")
        return {}

    if step >= len(skills):
        logger.info("[dispatcher] tutti gli esperti completati")
        return {}

    skill = skills[step]
    cfg   = EXPERTS.get(skill)
    if cfg is None:
        logger.warning(f"[dispatcher] skill '{skill}' non trovato in EXPERTS — skip")
        return {"current_step": step + 1}

    system_path = PROMPTS_DIR / cfg["prompt_file"]
    if not system_path.exists():
        logger.error(f"[dispatcher] prompt file mancante: {system_path} — skip")
        return {"current_step": step + 1}

    system = system_path.read_text(encoding="utf-8")
    
    # Iniezione regole sandbox (solo per skill che possono usarla)
    if skill in ["researcher", "coder", "sysadmin", "pentester"]:
        system += (
            "\n\n═══ REGOLE SANDBOX (OBBLIGATORIE) ═══\n"
            "Hai accesso a una sandbox reale. Per eseguire comandi DEVI usare ESATTAMENTE questi tag:\n"
            "  <bash>comando shell qui</bash>\n"
            "  <python>codice python qui</python>\n\n"
            "🚨 REGOLA CRITICA: NON scrivere MAI un output di comando se non l'hai visto nel "
            "'── RISULTATO BASH/PYTHON ──' fornito nel contesto.\n"
            "Se non c'è ancora un RISULTATO, scrivi il tag XML e FERMATI.\n"
            "I blocchi ```bash``` Markdown NON vengono eseguiti — usa solo i tag XML.\n"
            "═══════════════════════════════════════════════\n"
        )

    prompt   = _build_prompt(state, skill)
    t_skill  = time.time()
    is_retry = bool(state.get("audit_notes"))

    logger.info(
        f"[dispatcher] invoco '{skill}' "
        f"(passo {step+1}/{len(skills)}, {'retry' if is_retry else 'giro 1'})"
    )

    response = llm_generate(
        provider=cfg.get("provider", "ollama"),
        model=cfg["model"],
        prompt=prompt,
        system=system,
        temperature=cfg["temperature"],
        keep_alive=cfg.get("keep_alive", "5m"),
    )

    elapsed_ms = round((time.time() - t_skill) * 1000)
    logger.info(f"[dispatcher] '{skill}' → {len(response)} chars ({elapsed_ms}ms)")

    new_trace.append({
        "node":        f"expert_dispatcher[{skill}]",
        "ts":          time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "duration_ms": elapsed_ms,
        "model":       cfg["model"],
        "skill":       skill,
        "step":        step,
    })

    # Se la risposta non ha comandi da eseguire, questo esperto ha finito → avanza
    has_commands = bool(extract_commands(response))
    new_step = step if has_commands else step + 1

    if not has_commands and new_step < len(skills):
        logger.info(f"[dispatcher] '{skill}' completato → prossimo: {skills[new_step]}")
    elif not has_commands:
        logger.info(f"[dispatcher] tutti gli esperti completati ({len(skills)}/{len(skills)})")

    total_ms = round((time.time() - t0) * 1000)
    logger.info(f"[dispatcher] passo {step+1} completato in {total_ms}ms")

    return {
        "final_draft":    response,
        "expert_outputs": [response],
        "current_step":   new_step,
        "audit_notes":    None,
        "trace":          new_trace,
    }