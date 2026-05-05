"""
Grafo LangGraph — flusso semplificato senza validator.
persona → manager → [experts] → auditor → persona
"""
from langgraph.graph import StateGraph, END
from rick.state import RickState
from rick.nodes.persona import persona_node
from rick.nodes.manager import manager_node
from rick.nodes.expert_dispatcher import expert_dispatcher_node
from rick.nodes.auditor import auditor_node
from rick.nodes.memory_optimizer import memory_optimizer_node
import logging

logger = logging.getLogger(__name__)

MAX_AUDIT_RETRIES = 2


def after_manager(state: RickState):
    """Manager → dispatcher se serve esperto, altrimenti END."""
    skills = state.get("skills_needed", [])
    if skills and skills != ["none"]:
        return "expert_dispatcher"
    return END


def after_dispatcher(state: RickState):
    """Dispatcher → auditor sempre (l'auditor verifica anche "niente da verificare")."""
    return "auditor"


def after_audit(state: RickState):
    """
    Auditor → persona se OK
    Auditor → manager se fallito (per ricorreggere)
    Auditor → END se superati i retry
    """
    verdict = state.get("audit_verdict", "pass")
    audit_passes = state.get("audit_passes", 0)
    
    # Se superati i tentativi, forza chiusura
    if audit_passes >= MAX_AUDIT_RETRIES:
        logger.warning("[graph] Max audit retries reached, forcing END")
        return END
    
    # Se passato, vai a persona per risposta finale
    if verdict == "pass":
        return "persona"
    
    # Se fallito/retry, torna al manager per correggere
    if verdict in ["fail", "retry"]:
        logger.info(f"[graph] Audit {verdict} → back to manager")
        return "manager"
    
    # Fallback sicuro se l'auditor alucina un verdict strano
    logger.warning(f"[graph] Unknown verdict '{verdict}' → forcing END")
    return END


def build_graph():
    """Costruisce il grafo semplificato."""
    workflow = StateGraph(RickState)
    
    # Nodi
    workflow.add_node("persona", persona_node)
    workflow.add_node("manager", manager_node)
    workflow.add_node("expert_dispatcher", expert_dispatcher_node)
    workflow.add_node("auditor", auditor_node)
    workflow.add_node("memory_optimizer", memory_optimizer_node)
    
    # Entry point
    workflow.set_entry_point("persona")
    
    # Routing
    workflow.add_conditional_edges("persona", lambda s: "memory_optimizer")
    workflow.add_conditional_edges("memory_optimizer", lambda s: "manager")
    workflow.add_conditional_edges("manager", after_manager)
    workflow.add_conditional_edges("expert_dispatcher", after_dispatcher)
    workflow.add_conditional_edges("auditor", after_audit)
    
    return workflow.compile()

# Istanza globale del grafo per il CLI
graph = build_graph()
