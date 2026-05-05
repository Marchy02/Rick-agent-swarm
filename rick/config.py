"""
Configurazione centralizzata — modifica qui i modelli e i parametri.

Per aggiungere un nuovo esperto:
  1. Crea il file  rick/llm/prompts/<nome>.md  con il system prompt
  2. Aggiungi una voce in EXPERTS qui sotto
  3. Nient'altro — graph.py e nodes/ non vanno toccati
"""
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).parent.parent
DATA_DIR    = BASE_DIR / "data" / "traces"
PROMPTS_DIR = Path(__file__).parent / "llm" / "prompts"

DATA_DIR.mkdir(parents=True, exist_ok=True)

# ── Ollama ───────────────────────────────────────────────────────────────────
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_TIMEOUT  = 120  # secondi

# ── Modelli base ─────────────────────────────────────────────────────────────
MODEL_MANAGER  = "qwen2.5:7b"
PROVIDER_MANAGER = "ollama"

MODEL_AUDITOR  = "qwen2.5:7b"
PROVIDER_AUDITOR = "ollama"

MODEL_PERSONA  = "qwen2.5:7b"
PROVIDER_PERSONA = "ollama"


# ── Registry esperti ─────────────────────────────────────────────────────────
# Ogni voce descrive un esperto invocabile dal manager.
# Campi:
#   provider     - "ollama" (locale) o "gemini" (cloud Google)
#   model        – nome del modello (es. "qwen2.5-coder:7b" o "gemini-1.5-flash")
#   prompt_file  – nome file in rick/llm/prompts/ (senza path)
#   temperature  – temperatura generazione (0.0 = deterministico, 1.0 = creativo)
#   keep_alive   – quanto tenere il modello in RAM ("0" = scarica subito, solo per ollama)
#   description  – usata per auto-popolare il system prompt del manager
EXPERTS: dict[str, dict] = {
    "coder": {
        "provider":    "ollama",
        "model":       "qwen2.5-coder:7b",
        "prompt_file": "coder.md",
        "temperature": 0.1,
        "keep_alive":  "0",
        "description": "backend, Python, Go, Bash, debugging, code review, refactor, script",
    },
    "psychologist": {
        "provider":    "ollama",
        "model":       "qwen2.5:7b",
        "prompt_file": "psychologist.md",
        "temperature": 0.4,
        "keep_alive":  "5m",
        "description": "analisi emotiva, consigli relazionali, supporto psicologico, benessere mentale",
    },
    "sysadmin": {
        "provider":    "ollama",
        "model":       "qwen2.5-coder:7b",
        "prompt_file": "sysadmin.md",
        "temperature": 0.0,
        "keep_alive":  "0",
        "description": "bash, linux, networking, system administration, ping, shell commands, docker",
    },
    "pentester": {
        "provider":    "ollama",
        "model":       "qwen2.5-coder:7b",
        "prompt_file": "pentester.md",
        "temperature": 0.0,
        "keep_alive":  "0",
        "description": "hacking, penetration testing, nmap, exploit, security, vulnerabilità, red team, offensive",
    },
    "researcher": {
        # Per attivare Gemini cambia provider in "gemini" e model in "gemini-1.5-flash"
        "provider":    "gemini",
        "model":       "gemini-2.5-flash",
        "prompt_file": "researcher.md",
        "temperature": 0.0,
        "keep_alive":  "5m",
        "description": "ricerca internet, documentazione, versioni librerie, news, curl, pypi, ricerca web, cerca online",
    },
}

# ── Persona ───────────────────────────────────────────────────────────────────
# 0 = bypass totale | 1 = lieve | 2 = full Rick
PERSONA_INTENSITY = 1

# ── Auditor ──────────────────────────────────────────────────────────────────
MAX_AUDIT_RETRIES = 2   # dopo N retry, forza pass

# ── Sandbox ──────────────────────────────────────────────────────────────────
SANDBOX_TIMEOUT     = 30    # secondi per singola esecuzione (nmap lento richiede più tempo)
MAX_EXEC_RETRIES    = 3     # max giri ReAct (executor→dispatcher) per sessione

# Comandi pericolosi bloccati prima dell'esecuzione
SANDBOX_BLOCKLIST: list[str] = [
    "rm -rf /",
    "rm -rf ~",
    "mkfs",
    ":(){:|:&};:",   # fork bomb
    "dd if=/dev/zero",
    "sudo rm",
    "chmod -R 777 /",
    "(curl|wget).*\\|.*\\s+(bash|sh|zsh)", # Blocca solo pipe verso shell
]

# Variabili d'ambiente aggiuntive da bloccare nella sandbox
# (la sandbox eredita l'env del processo ma ESCLUDE queste)
SANDBOX_ENV_BLOCKLIST: list[str] = [
    "SUDO_ASKPASS", "DBUS_SESSION_BUS_ADDRESS",
]