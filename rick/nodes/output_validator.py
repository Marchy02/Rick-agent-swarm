"""
Nodo OUTPUT VALIDATOR
Responsabilità: verificare che l'esperto abbia usato i risultati reali dell'executor
e non abbia inventato numeri/versioni.

Inserito tra executor e auditor per bloccare allucinazioni prima che arrivino all'auditor.
"""
import re
import logging
from rick.state import RickState

logger = logging.getLogger(__name__)


def _extract_versions(text: str) -> set[str]:
    """Estrae versioni in formato X.Y.Z dal testo."""
    # Pattern: 1 o più cifre, punto, 1+ cifre, opzionale .cifre
    return set(re.findall(r'\b\d+\.\d+(?:\.\d+)?\b', text))


def _extract_numbers(text: str) -> set[str]:
    """Estrae numeri standalone (non versioni) dal testo."""
    # Match numeri interi o decimali NON seguiti da un altro punto
    # (per evitare di matchare 0.115 in "0.115.0")
    return set(re.findall(r'\b\d+(?:\.\d+)?(?!\.\d)\b', text))


def output_validator_node(state: RickState) -> dict:
    """
    Controlla se la risposta dell'esperto contiene dati inventati
    confrontandoli con i risultati dell'executor.
    
    Ritorna audit_verdict="retry" se rileva allucinazioni.
    """
    outputs = state.get("expert_outputs", [])
    if len(outputs) < 2:
        # Niente da validare: serve almeno executor output + expert response
        return {}
    
    # Trova l'ultimo risultato dell'executor
    executor_output = None
    expert_response = None
    
    for i in range(len(outputs) - 1, -1, -1):
        out = outputs[i]
        if "── RISULTATO" in out and executor_output is None:
            executor_output = out
        elif executor_output is not None:
            # Il primo output NON-executor dopo l'executor è la risposta
            expert_response = out
            break
    
    # Se non c'è stato executor in questo giro, skip validation
    if not executor_output:
        logger.info("[validator] nessun output executor da validare")
        return {}
    
    if not expert_response:
        logger.warning("[validator] executor output trovato ma nessuna risposta esperto successiva")
        return {}
    
    # Controlla exit code
    if "Exit code: 0" not in executor_output:
        logger.warning("[validator] executor fallito (exit code != 0), skip validation")
        return {}
    
    # Estrai dati rilevanti
    exec_versions = _extract_versions(executor_output)
    resp_versions = _extract_versions(expert_response)
    
    exec_numbers = _extract_numbers(executor_output)
    resp_numbers = _extract_numbers(expert_response)
    
    # Versioni inventate
    halluc_versions = resp_versions - exec_versions
    # Numeri inventati (escludendo anni comuni tipo 2024, 2025)
    halluc_numbers = {
        n for n in (resp_numbers - exec_numbers)
        if not (n.startswith('20') and len(n) == 4)  # skip anni
    }
    
    if halluc_versions or halluc_numbers:
        halluc_list = list(halluc_versions | halluc_numbers)
        logger.warning(
            f"[validator] 🚨 ALLUCINAZIONE RILEVATA: "
            f"{halluc_list} non presenti nell'output executor"
        )
        
        return {
            "audit_verdict": "retry",
            "audit_notes": (
                f"🚨 ALLUCINAZIONE RILEVATA:\n"
                f"Hai citato: {', '.join(halluc_list)}\n"
                f"Ma l'output dell'executor conteneva solo: {', '.join(exec_versions | exec_numbers)}\n\n"
                f"CORREZIONE RICHIESTA:\n"
                f"- Rileggi attentamente il blocco '── RISULTATO BASH/PYTHON ──'\n"
                f"- Usa SOLO i numeri/versioni presenti in quell'output\n"
                f"- Se l'output non contiene il dato richiesto, scrivi 'Non sono riuscito a recuperare questa informazione'\n"
                f"- NON inventare versioni o numeri"
            ),
        }
    
    logger.info("[validator] ✅ output coerente con executor")
    return {}