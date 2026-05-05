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
        "description": "backend, Python, Go, Bash, debugging, code review, refactor, script",
    },
    "psychologist": {
        "model":       "qwen2.5:7b",
        "prompt_file": "psychologist.md",
        "temperature": 0.7,
        "keep_alive":  "5m",
        "description": "analisi emotiva, consigli relazionali, supporto psicologico, benessere mentale",
    },
}

# ── Persona ───────────────────────────────────────────────────────────────────
PERSONA_INTENSITY = 1  # ← FIXED: era 2 (troppo esagerato)

# ── Auditor ──────────────────────────────────────────────────────────────────
MAX_AUDIT_RETRIES = 2   # dopo N retry, forza pass

# ── Sandbox ──────────────────────────────────────────────────────────────────
SANDBOX_TIMEOUT = 10    # secondi per esecuzione codice
