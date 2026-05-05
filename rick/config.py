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
MODEL_AUDITOR  = "qwen2.5:7b"
MODEL_PERSONA  = "qwen2.5:7b"


# ── Registry esperti ─────────────────────────────────────────────────────────
# Ogni voce descrive un esperto invocabile dal manager.
# Campi:
#   model        – modello Ollama da usare
#   prompt_file  – nome file in rick/llm/prompts/ (senza path)
#   temperature  – temperatura generazione (0.0 = deterministico, 1.0 = creativo)
#   keep_alive   – quanto tenere il modello in RAM ("0" = scarica subito)
#   description  – usata per auto-popolare il system prompt del manager
EXPERTS: dict[str, dict] = {
    "coder": {
        "model":       "qwen2.5-coder:7b",
        "prompt_file": "coder.md",
        "temperature": 0.1,
        "keep_alive":  "0",
        "description": "backend, Python, Go, Bash, debugging, code review, refactor, script",
    },
    "psychologist": {
        "model":       "qwen2.5:7b",
        "prompt_file": "psychologist.md",
        "temperature": 0.4,
        "keep_alive":  "5m",
        "description": "analisi emotiva, consigli relazionali, supporto psicologico, benessere mentale",
    },
    "sysadmin": {
        "model":       "qwen2.5-coder:7b",
        "prompt_file": "sysadmin.md",
        "temperature": 0.0,
        "keep_alive":  "0",
        "description": "bash, linux, networking, system administration, ping, shell commands, docker",
    },
    "pentester": {
        "model":       "qwen2.5-coder:7b",
        "prompt_file": "pentester.md",
        "temperature": 0.0,
        "keep_alive":  "0",
        "description": "hacking, penetration testing, nmap, exploit, security, vulnerabilità, red team, offensive",
    },
    "researcher": {
        # ⚠️ IMPORTANTE: usa un modello PIÙ GRANDE per il researcher
        # I modelli 7B tendono ad allucinare nonostante le istruzioni.
        # Opzioni raccomandate (in ordine di preferenza):
        #   - qwen2.5:32b  (migliore, richiede ~20GB VRAM)
        #   - qwen2.5:14b  (buon compromesso, ~9GB VRAM)
        #   - llama3.1:8b  (alternativa se non hai Qwen 14B)
        #
        # Se usi ancora 7b, aspettati occasionali allucinazioni nonostante
        # le istruzioni del prompt. I modelli piccoli "inventano" per completezza.
        "model":       "llama3:8b",  # ← CAMBIATO da 7b a 14b
        "prompt_file": "researcher.md",
        "temperature": 0.0,             # ← CAMBIATO da 0.3 a 0.0 (zero creatività)
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