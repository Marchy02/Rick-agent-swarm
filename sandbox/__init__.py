"""
Sandbox di Sessione — stazione di lavoro temporanea e sicura.

Sicurezza:
  - Nessun comando dalla blocklist può essere eseguito
  - Timeout rigido su ogni esecuzione (SANDBOX_TIMEOUT)
  - Eredita l'env reale ma rimuove variabili sensibili
  - Lavora in una cartella temporanea isolata che si auto-distrugge
  - Esegue solo i tag XML (<bash>, <python>) — i blocchi Markdown sono solo display
"""
import subprocess
import os
import re
import shutil
import sys
import logging
import time
from pathlib import Path
from rick.config import (
    SANDBOX_TIMEOUT, SANDBOX_BLOCKLIST, SANDBOX_ENV_BLOCKLIST
)

logger = logging.getLogger(__name__)

# ── Sandbox ───────────────────────────────────────────────────────────────────

class RickSandbox:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.path = Path("/tmp") / f"rick_sandbox_{session_id}"
        self.path.mkdir(parents=True, exist_ok=True)
        logger.info(f"[sandbox] Inizializzato in {self.path}")

    def _safe_env(self) -> dict:
        """Costruisce un ambiente sicuro: eredita l'env reale, rimuove variabili pericolose."""
        env = os.environ.copy()
        for key in SANDBOX_ENV_BLOCKLIST:
            env.pop(key, None)
        # Forza HOME nella sandbox — impedisce scritture accidentali in ~
        env["HOME"] = str(self.path)
        return env

    def _check_blocklist(self, command: str) -> str | None:
        """Restituisce il pattern bloccato se il comando è pericoloso, None se è sicuro."""
        cmd_lower = command.lower()
        for pattern in SANDBOX_BLOCKLIST:
            if re.search(pattern, cmd_lower):
                return pattern
        return None

    def execute_bash(self, command: str) -> dict:
        """Esegue un comando shell nella sandbox con controlli di sicurezza."""
        blocked = self._check_blocklist(command)
        if blocked:
            logger.warning(f"[sandbox] BLOCCATO (pattern: {blocked!r}): {command[:60]}")
            return {
                "stdout": "",
                "stderr": f"BLOCCATO: questo comando corrisponde alla regola di sicurezza '{blocked}'.",
                "returncode": -1,
                "success": False,
                "blocked": True,
            }

        try:
            result = subprocess.run(
                ["bash", "-c", command],
                cwd=self.path,
                capture_output=True,
                text=True,
                timeout=SANDBOX_TIMEOUT,
                env=self._safe_env(),
            )
            return {
                "stdout":     result.stdout,
                "stderr":     result.stderr,
                "returncode": result.returncode,
                "success":    result.returncode == 0,
            }
        except subprocess.TimeoutExpired:
            logger.warning(f"[sandbox] TIMEOUT dopo {SANDBOX_TIMEOUT}s: {command[:60]}")
            return {
                "stdout": "", "stderr": "",
                "error":  f"Timeout: il comando ha superato {SANDBOX_TIMEOUT} secondi. "
                          "Suggerimento: aggiungi un limite (es. -c 4 per ping).",
                "returncode": -1, "success": False,
            }
        except Exception as e:
            return {"stdout": "", "stderr": "", "error": str(e), "returncode": -1, "success": False}

    def execute_python(self, code: str) -> dict:
        """Esegue codice Python nella sandbox."""
        blocked = self._check_blocklist(code)
        if blocked:
            logger.warning(f"[sandbox] BLOCCATO codice Python (pattern: {blocked!r})")
            return {
                "stdout": "", "stderr": f"BLOCCATO: pattern pericoloso '{blocked}'.",
                "returncode": -1, "success": False, "blocked": True,
            }

        tmp_script = self.path / f"script_{int(time.time())}.py"
        tmp_script.write_text(code, encoding="utf-8")
        try:
            result = subprocess.run(
                [sys.executable, str(tmp_script)],
                cwd=self.path,
                capture_output=True,
                text=True,
                timeout=SANDBOX_TIMEOUT,
                env=self._safe_env(),
            )
            return {
                "stdout":     result.stdout,
                "stderr":     result.stderr,
                "returncode": result.returncode,
                "success":    result.returncode == 0,
            }
        except subprocess.TimeoutExpired:
            return {
                "stdout": "", "stderr": "",
                "error":  f"Timeout: script Python superato {SANDBOX_TIMEOUT}s.",
                "returncode": -1, "success": False,
            }
        except Exception as e:
            return {"stdout": "", "stderr": "", "error": str(e), "returncode": -1, "success": False}
        finally:
            if tmp_script.exists():
                tmp_script.unlink()

    def cleanup(self):
        """Elimina la cartella sandbox."""
        if self.path.exists():
            shutil.rmtree(self.path)
            logger.info(f"[sandbox] Cartella {self.path} eliminata.")


# ── Helpers ───────────────────────────────────────────────────────────────────

def extract_commands(text: str) -> list[tuple[str, str]]:
    """
    Estrae SOLO i tag XML <bash>...</bash> e <python>...</python>.
    I blocchi Markdown (```bash```) NON vengono eseguiti — sono solo display.
    Questo previene l'esecuzione accidentale di codice negli esempi o spiegazioni.
    """
    results = []
    bash_cmds = re.findall(r"<bash>(.*?)</bash>", text, re.DOTALL)
    for cmd in bash_cmds:
        results.append(("bash", cmd.strip()))

    py_cmds = re.findall(r"<python>(.*?)</python>", text, re.DOTALL)
    for cmd in py_cmds:
        results.append(("python", cmd.strip()))

    return results
