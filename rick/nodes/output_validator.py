"""
Nodo OUTPUT VALIDATOR v11.1 — Anti-allucinazione numerica + fix metadata None.
"""
import re
import logging
from rick.state import RickState
from rick.memory import save_verified_fact
from rick.config import MAX_VALIDATOR_RETRIES

logger = logging.getLogger(__name__)

EXECUTOR_MARKER = re.compile(r"──\s+RISULTATO\s+(BASH|PYTHON)\s+\(giro\s+\d+\)\s+──")


def _extract_version_numbers(text: str) -> set[str]:
    """Estrae versioni X.Y.Z e porte associate a parole chiave."""
    versions = set(re.findall(r'\b\d+\.\d+(?:\.\d+)*(?:[.\-]\w+)?\b', text))
    ports = set(re.findall(r'(?:porta|port|ascolto|listen)\s+(\d{2,5})', text, re.IGNORECASE))
    return versions | ports


def _filter_negative_context(text: str, numbers: set[str]) -> set[str]:
    """
    Rimuove i numeri che appaiono in un contesto negativo ("non la 3.8.12"),
    perché non sono affermazioni, ma smentite.
    """
    cleaned = set()
    for num in numbers:
        idx = text.find(num)
        if idx != -1:
            context = text[max(0, idx-30):idx+len(num)+30]
            if re.search(r'\b(non|invece|evita|errore|sbagliat|obsoleto|vecchi)\b', context, re.IGNORECASE):
                continue
        cleaned.add(num)
    return cleaned


def _find_last_executor_block(outputs: list[str]) -> tuple[int, str] | None:
    for i in range(len(outputs) - 1, -1, -1):
        if EXECUTOR_MARKER.search(outputs[i]):
            return i, outputs[i]
    return None


def _find_expert_response_after(outputs: list[str], start_idx: int) -> str | None:
    for i in range(start_idx + 1, len(outputs)):
        if not EXECUTOR_MARKER.search(outputs[i]) and outputs[i].strip():
            return outputs[i]
    return None


def _extract_command(executor_output: str) -> str:
    bash_match = re.search(r"<bash>(.*?)</bash>", executor_output, re.DOTALL)
    if bash_match:
        return bash_match.group(1).strip()
    python_match = re.search(r"<python>(.*?)</python>", executor_output, re.DOTALL)
    if python_match:
        return python_match.group(1).strip()
    for line in executor_output.splitlines():
        if any(p in line.lower() for p in ['curl ', 'wget ', 'import requests']):
            return line.strip()
    return "unknown"


def _save_verified_facts(executor_output: str, user_input: str):
    command = _extract_command(executor_output)
    versions = _extract_version_numbers(executor_output)

    for ver in versions:
        if "pypi" in command.lower() or "pip" in command.lower():
            pkg_match = re.search(r'(?:pypi\.org/pypi/|install\s+)([^/\s"]+)', command)
            pkg = pkg_match.group(1) if pkg_match else "unknown"
            fact = f"{pkg} versione {ver}"
        elif "nmap" in command.lower():
            fact = f"Porta {ver} (nmap)"
        else:
            fact = f"Versione rilevata: {ver}" if "." in ver else f"Risultato: {ver}"

        # Filtra None nei metadata per evitare errori nel DB
        metadata = {
            "command": command[:200] if command else "unknown",
            "user_query": user_input[:200] if user_input else "unknown"
        }
        metadata = {k: v for k, v in metadata.items() if v is not None}

        try:
            save_verified_fact(content=fact, source_type="executor_output", metadata=metadata)
            logger.info(f"[validator] ✅ Salvato: {fact}")
        except Exception as e:
            logger.error(f"[validator] Errore salvataggio {fact}: {e}")


def output_validator_node(state: RickState) -> dict:
    outputs = state.get("expert_outputs", [])
    user_input = state.get("user_input", "")
    retries = state.get("validator_retries", 0)

    last_exec = _find_last_executor_block(outputs)
    if not last_exec:
        return {"audit_verdict": "pass", "validator_retries": 0}

    exec_idx, exec_content = last_exec
    expert_resp = _find_expert_response_after(outputs, exec_idx)
    if not expert_resp:
        return {"audit_verdict": "pass", "validator_retries": 0}

    # Salva fatti solo se il comando è riuscito
    if "Exit code: 0" in exec_content:
        _save_verified_facts(exec_content, user_input)

    # Se l'executor è fallito, non possiamo validare con certezza
    if "Exit code: 0" not in exec_content:
        logger.info("[validator] Executor fallito, salto validazione")
        return {"audit_verdict": "pass"}

    exec_versions = _extract_version_numbers(exec_content)
    resp_versions_raw = _extract_version_numbers(expert_resp)
    resp_versions = _filter_negative_context(expert_resp, resp_versions_raw)

    hallucinated = resp_versions - exec_versions

    if hallucinated:
        if retries >= MAX_VALIDATOR_RETRIES:
            logger.warning(f"[validator] Max retry raggiunti → passo all'auditor")
            return {"audit_verdict": "pass", "validator_retries": retries + 1}

        logger.warning(f"[validator] 🚨 Allucinazione: {hallucinated}")
        return {
            "audit_verdict": "retry",
            "audit_notes": (
                f"🚨 ALLUCINAZIONE RILEVATA:\n"
                f"Hai citato dati non presenti nell'output dell'executor: {', '.join(sorted(hallucinated))}. "
                "Rileggi il blocco '── RISULTATO' e usa solo i dati reali."
            ),
            "validator_retries": retries + 1,
        }

    logger.info("[validator] ✅ Output coerente con l'executor")
    return {"audit_verdict": "pass", "validator_retries": 0}
