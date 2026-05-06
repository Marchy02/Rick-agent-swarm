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

from rick.config import MAX_AUDIT_RETRIES, MAX_EXEC_RETRIES, MAX_VALIDATOR_RETRIES


def after_manager(state: RickState):
    skills = state.get("skills_needed", [])
    if skills and skills != ["none"]:
        return "expert_dispatcher"
    return "persona"


def after_dispatcher(state: RickState):
    outputs = state.get("expert_outputs", [])
    if not outputs:
        return "output_validator"
    
    last_output = outputs[-1]
    commands = extract_commands(last_output)
    exec_passes = state.get("executor_passes", 0)
    
    if commands and exec_passes < MAX_EXEC_RETRIES:
        logger.info(f"[graph] Comandi rilevati ({len(commands)}) → vado all'executor (passaggio {exec_passes+1})")
        return "executor"
    
    logger.info("[graph] Nessun comando o max exec retries → output_validator")
    return "output_validator"


def after_validator(state: RickState):
    verdict = state.get("audit_verdict", "")
    retries = state.get("validator_retries", 0)
    
    if verdict == "retry":
        if retries >= MAX_VALIDATOR_RETRIES:
            logger.warning("[graph] Max validator retries raggiunto → auditor forzato")
            return "auditor"
        logger.info("[graph] Validator ha rilevato allucinazione → retry expert_dispatcher")
        return "expert_dispatcher"
    return "auditor"


def after_audit(state: RickState):
    verdict = state.get("audit_verdict", "pass")
    audit_passes = state.get("audit_passes", 0)
    
    if audit_passes >= MAX_AUDIT_RETRIES or verdict == "pass":
        return "persona"
    
    if verdict in ["fail", "retry"]:
        logger.info(f"[graph] Audit {verdict} → torno al manager per correzione")
        return "manager"
    
    return "persona"


def build_graph(checkpointer=None):
    workflow = StateGraph(RickState)
    
    workflow.add_node("manager", manager_node)
    workflow.add_node("expert_dispatcher", expert_dispatcher_node)
    workflow.add_node("executor", executor_node)
    workflow.add_node("output_validator", output_validator_node)
    workflow.add_node("auditor", auditor_node)
    workflow.add_node("persona", persona_node)
    workflow.add_node("memory_optimizer", memory_optimizer_node)
    
    workflow.set_entry_point("manager")
    
    workflow.add_conditional_edges("manager", after_manager)
    workflow.add_conditional_edges("expert_dispatcher", after_dispatcher)
    workflow.add_edge("executor", "expert_dispatcher")
    workflow.add_conditional_edges("output_validator", after_validator)
    workflow.add_conditional_edges("auditor", after_audit)
    workflow.add_edge("persona", "memory_optimizer")
    workflow.add_edge("memory_optimizer", END)
    
    return workflow.compile(checkpointer=checkpointer) if checkpointer else workflow.compile()