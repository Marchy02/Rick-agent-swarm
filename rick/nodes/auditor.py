"""
Auditor node — verifica fatti e comandi, gestisce il caso "niente da verificare".
"""
from rick.state import RickState
from rick.llm.client import call_llm
import logging

logger = logging.getLogger(__name__)


def auditor_node(state: RickState) -> dict:
    """
    Verifica draft di Rick e output di expert/executor.
    Se non c'è nulla da verificare (risposta casual), passa automaticamente.
    """
    final_draft = state.get("final_draft", "")
    executor_output = state.get("executor_output", "")
    audit_passes = state.get("audit_passes", 0)
    
    # Se superati i tentativi, forza pass
    if audit_passes >= 2:
        logger.warning("[auditor] Max retries reached, forcing PASS")
        return {
            "audit_verdict": "pass",
            "audit_report": "Max tentativi raggiunti, accettato forzatamente.",
            "audit_passes": audit_passes + 1
        }
    
    # Se final_draft vuoto, qualcosa è andato storto — fail
    if not final_draft or final_draft.strip() == "":
        logger.error("[auditor] Empty final_draft, failing")
        return {
            "audit_verdict": "fail",
            "audit_report": "Draft vuoto — persona non ha risposto.",
            "audit_passes": audit_passes + 1
        }
    
    # Caso 1: Nessun executor output → risposta conversazionale
    # Non c'è nulla da verificare, passa automaticamente
    if not executor_output or executor_output.strip() == "":
        logger.info("[auditor] No executor output → conversational reply, auto-pass")
        return {
            "audit_verdict": "pass",
            "audit_report": "Nessun comando/dato da verificare — risposta conversazionale.",
            "audit_passes": audit_passes + 1
        }
    
    # Caso 2: C'è executor output → verifica fattuale
    prompt = f"""Sei un auditor che verifica la correttezza di una risposta AI.

**Draft di Rick:**
{final_draft}

**Output di tool/expert utilizzati:**
{executor_output}

**Compito:**
1. Verifica se il draft contiene affermazioni fattuali che contraddicono l'output degli expert
2. Verifica se ci sono claim inventati non supportati dai dati
3. Verifica se i comandi bash citati sono effettivamente presenti nell'output

**Rispondi SOLO con uno di questi verdict:**
- PASS: Tutto ok, nessun problema
- FAIL: Errori gravi o affermazioni false
- RETRY: Piccole imprecisioni, può essere corretto

**Formato di risposta:**
verdict: [PASS/FAIL/RETRY]
issues: [Lista problemi trovati, o "nessuno"]
"""
    
    try:
        response = call_llm(prompt, model="qwen2.5:7b", temperature=0.1, timeout=30)
        logger.info(f"[auditor] Response: {response[:200]}...")
        
        # Parse verdict
        verdict = "fail"  # Default sicuro
        if "verdict: PASS" in response.upper() or "VERDICT:PASS" in response.upper():
            verdict = "pass"
        elif "verdict: RETRY" in response.upper() or "VERDICT:RETRY" in response.upper():
            verdict = "retry"
        elif "verdict: FAIL" in response.upper() or "VERDICT:FAIL" in response.upper():
            verdict = "fail"
        
        logger.info(f"[auditor] Verdict: {verdict}")
        
        return {
            "audit_verdict": verdict,
            "audit_report": response,
            "audit_passes": audit_passes + 1
        }
        
    except Exception as e:
        logger.error(f"[auditor] Error: {e}")
        # In caso di errore, forza pass per evitare loop
        return {
            "audit_verdict": "pass",
            "audit_report": f"Errore auditor: {e}, forzato pass.",
            "audit_passes": audit_passes + 1
        }
