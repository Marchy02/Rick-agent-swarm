"""
Grafo LangGraph — assembla i nodi e definisce il routing condizionale.

Flusso:
  manager → [router] → expert_dispatcher → [after_dispatcher] → executor ─┐
                ↓                                    ↑                     │
             persona                        (loop cap: MAX_EXEC_RETRIES)  │
                ↑                                                          │
           memory_optimizer ← persona ← [after_audit] ← auditor ← validator ←┘

Per aggiungere nuovi esperti NON modificare questo file:
agisci solo su EXPERTS in config.py e sul file .md del prompt.
"""
import logging
from langgraph.graph import StateGraph, END
from rick.state import RickState
from rick.config import MAX_EXEC_RETRIES
from rick.nodes.manager           import manager_node
from rick.nodes.expert_dispatcher import expert_dispatcher_node
from rick.nodes.auditor           import auditor_node
from rick.nodes.persona           import persona_node
from rick.nodes.executor          import executor_node
from rick.nodes.memory_optimizer  import memory_optimizer_node
from rick.nodes.output_validator  import output_validator_node  # ← NUOVO

logger = logging.getLogger(__name__)


# ── Edge functions (routing condizionale) ─────────────────────────────────────

def after_router(state: RickState) -> str:
    """Dopo il manager: se servono esperti → dispatcher, altrimenti → persona."""
    skills = state.get("skills_needed", [])
    if skills:
        logger.info(f"[graph] route → expert_dispatcher (skills={skills})")
        return "expert_dispatcher"
    logger.info("[graph] route → persona (nessun expert)")
    return "persona"


def after_dispatcher(state: RickState) -> str:
    """
    Dopo il dispatcher:
    - Se l'esperto ha scritto comandi → executor
    - Se ci sono altri esperti in coda → expert_dispatcher (prossimo passo)
    - Altrimenti → validator (nuovo) → auditor
    """
    passes    = state.get("executor_passes", 0)
    skills    = state.get("skills_needed", [])
    step      = state.get("current_step", 0)
    outputs   = state.get("expert_outputs", [])

    # Cap sul loop executor (sicurezza anti-loop)
    if passes >= MAX_EXEC_RETRIES:
        logger.info(f"[graph] cap executor ({passes}/{MAX_EXEC_RETRIES}) → validator")
        return "validator"

    # Controlla se l'ultimo output ha comandi da eseguire
    if outputs:
        from sandbox import extract_commands
        cmds = extract_commands(outputs[-1])
        if cmds:
            logger.info(f"[graph] route → executor (passo {step}, {len(cmds)} cmd)")
            return "executor"

    # Nessun comando: controlla se ci sono altri esperti da eseguire
    if step < len(skills):
        logger.info(f"[graph] route → expert_dispatcher (prossimo: {skills[step] if step < len(skills) else 'N/A'})")
        return "expert_dispatcher"

    logger.info("[graph] tutti gli esperti completati → validator")
    return "validator"


def after_validator(state: RickState) -> str:
    """
    Dopo il validator: se ha rilevato allucinazioni → retry da dispatcher,
    altrimenti → auditor.
    """
    verdict = state.get("audit_verdict")
    if verdict == "retry":
        logger.info("[graph] validator detected hallucination → expert_dispatcher")
        return "expert_dispatcher"
    logger.info("[graph] validator pass → auditor")
    return "auditor"


def after_audit(state: RickState) -> str:
    """Dopo l'auditor: pass/fail → persona | retry → expert_dispatcher.
    Il cap sul numero di retry è già gestito DENTRO auditor_node (forza pass).
    """
    verdict = state.get("audit_verdict", "pass").lower()
    if verdict == "retry":
        logger.info(f"[graph] audit retry ({state.get('audit_passes',0)}) → expert_dispatcher")
        return "expert_dispatcher"
    logger.info(f"[graph] audit {verdict} → persona")
    return "persona"


# ── Costruzione grafo ─────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    g = StateGraph(RickState)

    g.add_node("manager",           manager_node)
    g.add_node("expert_dispatcher", expert_dispatcher_node)
    g.add_node("executor",          executor_node)
    g.add_node("validator",         output_validator_node)  # ← NUOVO
    g.add_node("auditor",           auditor_node)
    g.add_node("persona",           persona_node)
    g.add_node("memory_optimizer",  memory_optimizer_node)

    g.set_entry_point("manager")

    g.add_conditional_edges("manager", after_router, {
        "expert_dispatcher": "expert_dispatcher",
        "persona":           "persona",
    })
    g.add_conditional_edges("expert_dispatcher", after_dispatcher, {
        "executor":          "executor",
        "expert_dispatcher": "expert_dispatcher",
        "validator":         "validator",  # ← passa dal validator prima dell'auditor
    })
    g.add_edge("executor", "expert_dispatcher")
    
    # Nuovo flusso: validator può rimandare al dispatcher o passare all'auditor
    g.add_conditional_edges("validator", after_validator, {
        "auditor":           "auditor",
        "expert_dispatcher": "expert_dispatcher",
    })

    g.add_conditional_edges("auditor", after_audit, {
        "persona":           "persona",
        "expert_dispatcher": "expert_dispatcher",
    })
    g.add_edge("persona", "memory_optimizer")
    g.add_edge("memory_optimizer", END)

    return g.compile()


# Singleton compilato — importato da cli.py
graph = build_graph()