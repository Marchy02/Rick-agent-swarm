"""
Stato condiviso del grafo LangGraph.
Ogni nodo legge da qui e scrive qui.
"""
from typing import TypedDict, List, Optional, Any, Annotated
import operator

class RickState(TypedDict):
    # ── Input ─────────────────────────────────────────────
    user_input: str
    session_id: str                   # ID univoco per la sandbox

    # ── Manager output ────────────────────────────────────
    intent:       str
    skills_needed: List[str]          # es. ["pentester", "researcher", "coder"]
    plan:         List[dict]          # es. [{step:1, task:"...", skill:"coder"}]
    current_step: int                 # quale esperto è attivo ora (indice in skills_needed)

    # ── Expert output ─────────────────────────────────────
    expert_outputs: Annotated[List[str], operator.add] # ogni giro di expert appende qui
    final_draft:    str               # ultima risposta dell'expert

    # ── Auditor ───────────────────────────────────────────
    audit_verdict:  str               # "pass" | "retry" | "fail"
    audit_notes:    Optional[str]     # fix_hint per il retry
    audit_passes:   int               # contatore giri auditor
    executor_passes: int              # contatore giri ReAct (cap loop)

    # ── Persona ───────────────────────────────────────────
    final_response: str               # risposta definitiva in voce Rick

    # ── Strumentazione ────────────────────────────────────
    trace: Annotated[List[dict], operator.add]        # JSONL trace per Agent-Lightning

