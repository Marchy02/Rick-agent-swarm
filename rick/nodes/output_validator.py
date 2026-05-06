"""
Nodo OUTPUT VALIDATOR
Responsabilità: 
1. Verificare che l'esperto abbia usato i risultati reali dell'executor
2. Salvare i risultati verificati dell'executor nella memoria come "fatti verificati"

Inserito tra executor e auditor per bloccare allucinazioni prima che arrivino all'auditor.
"""
import re
import logging
from rick.state import RickState
from rick.memory import save_verified_fact

logger = logging.getLogger(__name__)


def _extract_versions(text: str) -> set[str]:
    """Estrae versioni (X.Y, X.Y.Z, X.Y.Z-W) e i loro componenti numerici."""
    # Trova versioni complete (es. 6.19.14)
    versions = set(re.findall(r'\b\d+\.\d+(?:\.\d+)*(?:-\d+)?\b', text))
    
    # Estrai anche i singoli componenti numerici per permettere citazioni parziali
    # (es. se l'output ha 6.19.14, l'esperto può dire "kernel 6")
    components = set(re.findall(r'\b\d+\b', text))
    
    return versions | components


def _extract_numbers(text: str) -> set[str]:
    """Estrae numeri significativi, ignorando quelli piccoli comuni (1-10)."""
    all_nums = set(re.findall(r'\b\d+(?:\.\d+)?\b', text))
    # Filtriamo numeri molto piccoli che sono spesso rumore o indici di liste
    return {n for n in all_nums if float(n) > 10 or n in ['0', '80', '443', '8080']}


def _extract_executor_command(executor_output: str) -> str | None:
    """Estrae il comando eseguito dall'output dell'executor."""
    # Cerca pattern tipo "curl -s ..." o "import requests; ..."
    lines = executor_output.split('\n')
    for line in lines:
        if 'curl' in line.lower() or 'wget' in line.lower():
            return line.strip()
        if 'import' in line and 'requests' in line:
            return line.strip()
    return None


def _save_executor_results_to_memory(executor_output: str, user_input: str):
    """
    Salva i risultati dell'executor come fatti verificati nella memoria.
    
    Esempi di fatti verificati:
    - "FastAPI version 0.115.0 (verificato via curl pypi.org)"
    - "Server risponde su porta 8080 (verificato via nmap)"
    """
    # Estrai il comando eseguito
    command = _extract_executor_command(executor_output)
    
    # Estrai versioni e numeri significativi
    versions = _extract_versions(executor_output)
    
    # Se non ci sono dati estratti, skip
    if not versions and not command:
        return
    
    # Costruisci il fatto verificato
    facts = []
    
    # Versioni (es. da curl pypi)
    if versions and command and 'pypi' in command.lower():
        # Estrai nome package dal comando
        pkg_match = re.search(r'pypi\.org/pypi/([^/\s"]+)', command)
        if pkg_match:
            pkg_name = pkg_match.group(1)
            # Prendi la versione più recente (assumendo sia ordinata)
            latest_ver = sorted(versions, reverse=True)[0]
            fact = f"{pkg_name} versione {latest_ver}"
            facts.append(fact)
    
    # Salva ogni fatto come verified_fact
    for fact in facts:
        save_verified_fact(
            content=fact,
            source_type="executor_output",
            metadata={
                "command": command[:200] if command else "unknown",
                "user_query": user_input[:200],
            }
        )
        logger.info(f"[validator] ✅ Saved verified fact: {fact}")


def output_validator_node(state: RickState) -> dict:
    """
    Controlla se la risposta dell'esperto contiene dati inventati
    confrontandoli con i risultati dell'executor.
    
    Ritorna audit_verdict="retry" se rileva allucinazioni.
    """
    outputs = state.get("expert_outputs", [])
    user_input = state.get("user_input", "")
    
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
    
    # ═══════════════════════════════════════════════════════════════════════
    # SALVATAGGIO FATTI VERIFICATI
    # ═══════════════════════════════════════════════════════════════════════
    # Se l'executor è andato a buon fine, salva i risultati in memoria
    if "Exit code: 0" in executor_output:
        try:
            _save_executor_results_to_memory(executor_output, user_input)
        except Exception as e:
            logger.error(f"[validator] Errore durante salvataggio fatti: {e}")
    
    # ═══════════════════════════════════════════════════════════════════════
    # VALIDAZIONE ANTI-ALLUCINAZIONE
    # ═══════════════════════════════════════════════════════════════════════
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
