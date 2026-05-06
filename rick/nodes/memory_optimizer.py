"""
Nodo MEMORY OPTIMIZER (v10)
- Identifica fatti tecnici e personali dall'input utente (e dalla risposta finale)
- Skip aggressivo su chiacchiera, domande generiche, richieste one-shot via Regex
- Salva SOLO se il contenuto è verificabile, tecnico, o personale esplicito
- Dedup automatico via UNIQUE constraint in SQLite (gestito in memory.py)
"""
import logging
import re
import time
from rick.state import RickState
from rick.config import MODEL_MANAGER
from rick.llm.client import ollama_generate
from rick.memory import save_memory

logger = logging.getLogger(__name__)

# ── Pattern per identificare input "spazzatura" (da non salvare) ─────────────
TRIVIAL_REGEX = re.compile(
    r"^(ciao|hey|ehi|salve|ok|grazie|thanks|aiuto|help|test|prova|che (cosa |)puoi fare|come (stai|va)|tutto bene|buongiorno|buonasera)[!?.]*$",
    re.IGNORECASE
)

# Domande one-shot che NON contengono informazioni personali
ONE_SHOT_PATTERNS = [
    r"come (si|posso) (fare|creare|scrivere|installare|usare)",
    r"quanto (è|tempo|spazio|manca)",
    r"qual è (il|la|un|una|l')",
    r"dammi (una|un|la|il|dei|degli)",
    r"mostrami (una|un|la|il)",
    r"elenca (tutti|i|le|gli)",
    r"spiega(mi)? (come|cos'è|cosa)",
    r"perché (la|il|si)",
    r"(cerca|trova|dimmi) (su|in|per|un|una|il|la)",
    r"fammi (un|una|il|la|vedere)",
    r"puoi (creare|scrivere|fare|mostrare|darmi|trovare)",
]

# Parole chiave che indicano informazione personale / tecnica persistente
PERSONAL_INFO_PATTERNS = [
    r"(mi chiamo|il mio nome è|sono)\s+\w+",
    r"(abito|vivo|sto)\s+(a|in|a casa|in provincia)\s",
    r"(lavoro|studio|faccio|programmo)\s+(come|in|con|a|per)",
    r"(ho|possiedo|uso)\s+(un|una|il|la|iPhone|Mac|Windows|Linux|Fedora|Ubuntu)",
    r"(il mio|la mia)\s+(computer|pc|portatile|server|OS|sistema|macchina)",
    r"(sono|faccio|lavoro)\s+(un|una|il|la)\s+(programmatore|sviluppatore|studente|sysadmin|hacker|ingegnere)",
    r"\b(configurazione|setup|ambiente|toolchain|progetto|repository|repo)\b",
]

TECH_INFO_PATTERNS = [
    r"\b(python|node|java|rust|go|ruby|php|javascript|typescript)\s*\d+\.\d+",
    r"\b(fedora|ubuntu|debian|arch|manjaro|centos|rhel|windows|macos|osx)\s*\d*",
    r"\b(kernel|version|versione)\s*\d+\.\d+",
    r"\b(dual boot|vm|virtualbox|docker|k8s|kubernetes|container|vmware)\b",
    r"\b(path|percorso|directory|folder|home)\s*[:/\\]",
    r"\b(api key|token|secret|password|credenziali)\b",
    r"\b(nginx|apache|postgres|mysql|mariadb|mongodb|redis)\b",
    r"\b(ssh|vpn|firewall|nftables|iptables|ufw)\b",
    r"\b(gpu|cpu|ram|ssd|hdd|nvidia|amd|intel)\b",
    r"\b(config|dotfile|\.bashrc|\.zshrc|\.vimrc|\.gitconfig)\b",
]


def _contains_personal_or_tech_info(text: str) -> bool:
    """True se il testo contiene informazioni personali o tecniche che vale la pena salvare."""
    for pattern in PERSONAL_INFO_PATTERNS + TECH_INFO_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def _is_trivial(user_input: str) -> bool:
    """Determina se l'input è spazzatura conversazionale."""
    stripped = user_input.strip().lower()
    
    # Match esatto con pattern triviali
    if TRIVIAL_REGEX.match(stripped):
        return True
    
    # Input cortissimo senza contenuto tecnico/personale
    if len(stripped.split()) <= 3 and not _contains_personal_or_tech_info(user_input):
        return True
    
    # Domanda one-shot generica
    for pattern in ONE_SHOT_PATTERNS:
        if re.search(pattern, stripped):
            # A meno che non contenga anche dati personali
            if not _contains_personal_or_tech_info(user_input):
                return True
    
    return False


def _build_extraction_prompt(user_input: str, final_response: str | None = None) -> str:
    """Costruisce il prompt di estrazione fatti."""
    base = f"""Analizza questo messaggio utente. Estrai SOLO fatti persistenti.

REGOLE FERREE:
1. Estrai SOLO informazioni che l'utente:
   - Dichiara su di sé (nome, lavoro, posizione geografica, OS, tool preferiti)
   - Menziona come parte del suo ambiente/setup (file, path, versioni, hardware)
   - Chiede di ricordare esplicitamente ("ricorda che...", "tieni a mente...")
2. NON salvare:
   - Domande tecniche generiche ("come installo...?", "quanto pesa...?")
   - Richieste one-shot ("fammi uno script...", "cercami...")
   - Opinioni, curiosità, chiacchiere
3. Scrivi fatti in terza persona: "L'utente abita a Vicenza", "L'utente usa Fedora 41"
4. Un fatto per riga, massimo 3 fatti.
5. Se non c'è NIENTE di persistente, rispondi esattamente: NIENTE

Messaggio utente: {user_input}"""

    if final_response and final_response.strip():
        base += f"\n\nRisposta di Rick:\n{final_response[:1000]}"

    return base + "\n\nFatti da ricordare:"


def memory_optimizer_node(state: RickState) -> dict:
    t0 = time.time()
    user_input = state["user_input"]
    final_response = state.get("final_response", "")
    audit_verdict = state.get("audit_verdict", "")
    intent = state.get("intent", "")

    # ══ STEP 0: Safety Check (v9) ════════════════════════════════════════════
    if audit_verdict not in ["pass", ""]:
        logger.info(f"[memory_optimizer] Skip (audit_verdict={audit_verdict}).")
        return {}

    # ══ STEP 1: Skip aggressivo su input spazzatura (v10) ════════════════════
    if _is_trivial(user_input):
        logger.info(f"[memory_optimizer] Skip (input triviale): {user_input[:60]!r}")
        return {}

    # ══ STEP 2: Controllo euristico pre-LLM ═══════════════════════════════════
    # Se l'intento riguarda la memoria, saltiamo il triage ed entriamo sempre
    is_memory_intent = "memorizz" in intent.lower() or "ricord" in intent.lower()
    
    has_tech = _contains_personal_or_tech_info(user_input)
    has_tech_in_response = bool(final_response) and _contains_personal_or_tech_info(final_response)

    if not is_memory_intent and not has_tech and not has_tech_in_response:
        if len(user_input.split()) < 40:
            logger.info(f"[memory_optimizer] Skip (nessun marker tech/personale, input breve)")
            return {}

    # ══ STEP 3: Estrazione via LLM ════════════════════════════════════════════
    prompt = _build_extraction_prompt(user_input, final_response)

    logger.info("[memory_optimizer] Estrazione fatti in corso...")

    raw = ollama_generate(
        model=MODEL_MANAGER,
        prompt=prompt,
        system="Sei un estrattore di fatti spietato. Ritorna solo i fatti o NIENTE.",
        temperature=0.0,
        keep_alive="0"
    ).strip()

    logger.debug(f"[memory_optimizer] RAW OUTPUT: {raw!r}")

    elapsed_ms = round((time.time() - t0) * 1000)

    # ══ STEP 4: Validazione e salvataggio ═════════════════════════════════════
    if not raw or "NIENTE" in raw.upper() or len(raw) < 6:
        logger.info(f"[memory_optimizer] Nessun fatto persistente ({elapsed_ms}ms)")
        return {}

    lines = [l.strip("- •· \t") for l in raw.splitlines() if l.strip()]
    facts_saved = 0
    for line in lines:
        if len(line) < 10:
            continue
        if any(w in line.lower() for w in ["domanda", "chiacchiera", "richiesta", "one-shot"]):
            continue
        
        # Validazione semantica minima
        if not (re.search(r"\b(usa|ha|possiede|programma|lavora|abita|vive|studia|è|preferisce)\b", line.lower())
                or ":" in line):
            continue

        logger.info(f"[memory_optimizer] Fatto validato: {line[:80]}...")
        save_memory(user_input, line)
        facts_saved += 1

    if facts_saved:
        logger.info(f"[memory_optimizer] Salvati {facts_saved}/{len(lines)} fatti ({elapsed_ms}ms)")
    else:
        logger.info(f"[memory_optimizer] Tutti i fatti scartati dal controllo qualità ({elapsed_ms}ms)")

    return {}
