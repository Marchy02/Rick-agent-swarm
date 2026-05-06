"""
Grafo LangGraph — Versione "C-137" con Loop di Esecuzione e Validazione.
manager → [dispatcher ⇄ executor] → output_validator → auditor → persona → memory_optimizer → END
"""
from langgraph.graph import StateGraph, END
from rick.state import RickState
from rick.nodes.persona import persona_node
from rick.nodes.manager import manager_node
from rick.nodes.expert_dispatcher import expert_dispatcher_node
from rick.nodes.executor import executor_node
from rick.nodes.output_validator import output_validator_node
from rick.nodes.auditor import auditor_node
from rick.nodes.memory_optimizer import memory_optimizer_node
from sandbox import extract_commands
import logging

logger = logging.getLogger(__name__)

MAX_AUDIT_RETRIES = 2
MAX_EXEC_RETRIES = 3  # Numero massimo di tentativi di correzione codice


def after_manager(state: RickState):
    """Manager → dispatcher se serve esperto, altrimenti persona."""
    skills = state.get("skills_needed", [])
    if skills and skills != ["none"]:
        return "expert_dispatcher"
    return "persona"


def after_dispatcher(state: RickState):
    """
    Se l'esperto ha prodotto tag <bash> o <python>, vai all'executor.
    Altrimenti, vai al validator (che poi va all'auditor).
    """
    outputs = state.get("expert_outputs", [])
    if not outputs:
        return "output_validator"
    
    last_output = outputs[-1]
    commands = extract_commands(last_output)
    exec_passes = state.get("executor_passes", 0)
    
    if commands and exec_passes < MAX_EXEC_RETRIES:
        logger.info(f"[graph] Comandi rilevati ({len(commands)}) → vado all'executor (passaggio {exec_passes+1})")
        return "executor"
    
    logger.info("[graph] tutti gli esperti completati → output_validator")
    return "output_validator"


def after_validator(state: RickState):
    """
    Validator → auditor se OK, altrimenti retry da dispatcher.
    """
    verdict = state.get("audit_verdict")
    if verdict == "retry":
        logger.info("[graph] validator rilevato allucinazione → retry expert_dispatcher")
        return "expert_dispatcher"
    return "auditor"


def after_audit(state: RickState):
    """Auditor → persona se OK, manager se serve correzione logica."""
    verdict = state.get("audit_verdict", "pass")
    audit_passes = state.get("audit_passes", 0)
    
    if audit_passes >= MAX_AUDIT_RETRIES or verdict == "pass":
        return "persona"
    
    if verdict in ["fail", "retry"]:
        logger.info(f"[graph] Audit {verdict} → torno al manager per correzione")
        return "manager"
    
    return "persona"


def build_graph(checkpointer=None):
    """Costruisce il grafo con loop di esecuzione sandbox e validazione output."""
    workflow = StateGraph(RickState)
    
    # Nodi
    workflow.add_node("manager", manager_node)
    workflow.add_node("expert_dispatcher", expert_dispatcher_node)
    workflow.add_node("executor", executor_node)
    workflow.add_node("output_validator", output_validator_node)
    workflow.add_node("auditor", auditor_node)
    workflow.add_node("persona", persona_node)
    workflow.add_node("memory_optimizer", memory_optimizer_node)
    
    # Entry point
    workflow.set_entry_point("manager")
    
    # Routing
    workflow.add_conditional_edges("manager", after_manager)
    workflow.add_conditional_edges("expert_dispatcher", after_dispatcher)
    
    # Dopo l'esecuzione, si torna al dispatcher per vedere se l'esperto ha finito o deve fare altro
    workflow.add_edge("executor", "expert_dispatcher")
    
    # Validator può rimandare al dispatcher se trova allucinazioni
    workflow.add_conditional_edges("output_validator", after_validator)
    
    workflow.add_conditional_edges("auditor", after_audit)
    
    # Persona → memory_optimizer → END
    # Memory optimizer salva SOLO se audit_verdict == "pass"
    workflow.add_edge("persona", "memory_optimizer")
    workflow.add_edge("memory_optimizer", END)
    
    return workflow.compile(checkpointer=checkpointer) if checkpointer else workflow.compile()
