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
OLLAMA_TIMEOUT  = 180  # Aumentato per modelli pesanti

# ── Modelli base ─────────────────────────────────────────────────────────────
MODEL_MANAGER  = "qwen2.5:7b"
MODEL_AUDITOR  = "qwen2.5:7b"
MODEL_PERSONA  = "qwen2.5:7b"  # ← FIXED: era dolphin-llama3:8b (esagerava)

# ── Registry esperti ─────────────────────────────────────────────────────────
EXPERTS: dict[str, dict] = {
    "coder": {
        "model":       "qwen2.5-coder:7b",
        "prompt_file": "coder.md",
        "temperature": 0.2,
        "keep_alive":  "0",
        "description": "backend, Python, Go, C++, debugging, code review, refactor, logica complessa",
    },
    "sysadmin": {
        "model":       "qwen2.5:7b",
        "prompt_file": "sysadmin.md",
        "temperature": 0.1,
        "keep_alive":  "5m",
        "description": "script Bash, automazione Linux, amministrazione sistema, configurazione server, networking, sicurezza",
    },
    "pentester": {
        "model":       "qwen2.5:7b",
        "prompt_file": "pentester.md",
        "temperature": 0.4,
        "keep_alive":  "5m",
        "description": "security audit, vulnerabilità, CTF, exploit, analisi sicurezza",
    },
    "researcher": {
        "model":       "qwen2.5:7b",
        "prompt_file": "researcher.md",
        "temperature": 0.5,
        "keep_alive":  "5m",
        "description": "ricerca informazioni, documentazione, analisi dati, sintesi argomenti complessi",
    },
    "psychologist": {
        "model":       "qwen2.5:7b",
        "prompt_file": "psychologist.md",
        "temperature": 0.7,
        "keep_alive":  "5m",
        "description": "analisi emotiva, consigli relazionali, supporto psicologico, benessere mentale",
    },
}

# ── Persona (Rick C-137) ──────────────────────────────────────────────────────
# PERSONA_IRONY: Il selettore di personalità e cinismo.
#   1 = OFF: Rick è spento. Ricevi solo la risposta tecnica (Bypass totale).
#   2 = Spoglio: Minimalista, quasi robotico, un *burp* ogni tanto.
#   3 = Rick Classico: Sarcasmo e cinismo standard della serie (Default).
#   4 = Con Ricordi: Rick usa la memoria per fare riferimenti personali.
#   5 = Distruttivo: Si attiva da solo se sbagli. Rick ti umilia senza pietà.
PERSONA_IRONY = 3 

CODE_PLACEHOLDER_PREFIX = "██RICK_CODE_"
CODE_PLACEHOLDER_SUFFIX = "██"

# ── Auditor ──────────────────────────────────────────────────────────────────
MAX_AUDIT_RETRIES = 2   # dopo N retry, forza pass

# ── Sandbox ──────────────────────────────────────────────────────────────────
SANDBOX_TIMEOUT = 10    # secondi per esecuzione codice
MAX_EXEC_RETRIES = 3    # cap loop ReAct dell'executor
MAX_VALIDATOR_RETRIES = 2 # numero di tentativi per correggere allucinazioni numeriche
