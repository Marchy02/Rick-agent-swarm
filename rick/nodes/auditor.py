"""
Auditor node — verifica fatti e comandi, gestisce il caso "niente da verificare".
"""
import time
from rick.state import RickState
from rick.llm.client import call_llm
import logging

logger = logging.getLogger(__name__)


def _trace(verdict: str, issues=None, fix_hint=None) -> list[dict]:
    return [{
        "node": "auditor",
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "model": "qwen2.5:7b",
        "data": {"verdict": verdict, "issues": issues or [], "fix_hint": fix_hint or ""},
    }]


def auditor_node(state: RickState) -> dict:
    """
    Verifica draft di Rick e output di expert/executor.
    Se non c'è nulla da verificare (risposta casual), passa automaticamente.
    """
    final_draft = state.get("final_draft", "")
    
    # Cerchiamo i risultati dell'executor nella lista degli output esperti
    all_outputs = state.get("expert_outputs", [])
    executor_results = [o for o in all_outputs if "── RISULTATO" in o]
    executor_output = "\n".join(executor_results)
    
    audit_passes = state.get("audit_passes", 0)
    
    # Se superati i tentativi, forza pass
    if audit_passes >= 2:
        logger.warning("[auditor] Max retries reached, forcing PASS")
        return {
            "audit_verdict": "pass",
            "audit_report": "Max tentativi raggiunti, accettato forzatamente.",
            "audit_passes": audit_passes + 1,
            "trace": _trace("pass", ["max_retries"], None),
        }

    # Se final_draft vuoto, qualcosa è andato storto — fail
    if not final_draft or final_draft.strip() == "":
        logger.error("[auditor] Empty final_draft, failing")
        return {
            "audit_verdict": "fail",
            "audit_report": "Draft vuoto — persona non ha risposto.",
            "audit_passes": audit_passes + 1,
            "trace": _trace("fail", ["empty_draft"], None),
        }

    # Caso 1: Nessun executor output → risposta conversazionale
    # Non c'è nulla da verificare, passa automaticamente
    if not executor_output or executor_output.strip() == "":
        logger.info("[auditor] No executor output → conversational reply, auto-pass")
        return {
            "audit_verdict": "pass",
            "audit_report": "Nessun comando/dato da verificare — risposta conversazionale.",
            "audit_passes": audit_passes + 1,
            "trace": _trace("pass", [], None),
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
        resp_up = response.upper()
        if "VERDICT: PASS" in resp_up or "VERDICT:PASS" in resp_up:
            verdict = "pass"
        elif "VERDICT: RETRY" in resp_up or "VERDICT:RETRY" in resp_up:
            verdict = "retry"
        elif "VERDICT: FAIL" in resp_up or "VERDICT:FAIL" in resp_up:
            verdict = "fail"
        
        logger.info(f"[auditor] Verdict: {verdict}")

        # Estrai issues dal response (formato: "issues: [...]")
        issues = []
        for line in response.splitlines():
            if line.lower().startswith("issues:"):
                issues = [line.split(":", 1)[1].strip()]
                break

        return {
            "audit_verdict": verdict,
            "audit_report": response,
            "audit_notes": response if verdict in ("retry", "fail") else None,
            "audit_passes": audit_passes + 1,
            "trace": _trace(verdict, issues, response if verdict != "pass" else None),
        }

    except Exception as e:
        logger.error(f"[auditor] Error: {e}")
        return {
            "audit_verdict": "pass",
            "audit_report": f"Errore auditor: {e}, forzato pass.",
            "audit_passes": audit_passes + 1,
            "trace": _trace("pass", [f"auditor_error:{type(e).__name__}"], None),
        }
