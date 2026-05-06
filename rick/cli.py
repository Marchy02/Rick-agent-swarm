"""
CLI entry point — `python -m rick.cli "la tua richiesta"`

Features:
  - Esegue la pipeline completa (manager → expert → validator → auditor → persona)
  - Stampa la risposta finale su stdout
  - Scrive il trace JSONL in data/traces/<session_id>.jsonl
  - Flag --sandbox: esegue i blocchi Python nella sandbox dopo la risposta
  - Flag --no-persona: bypass Rick (persona_intensity=0)
  - Flag --trace: stampa il trace completo a fine run
"""
import os
os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["CHROMA_TELEMETRY"] = "False"
os.environ["CHROMA_SERVER_NOFILE"] = "524288"

import argparse
import json
import logging
import sys
import time
import uuid
from pathlib import Path

# ── Setup logging ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stderr,   # tutto il log va su stderr, stdout è solo la risposta
)
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="rick",
        description="Rick v8 — Multi-Agent CLI",
    )
    parser.add_argument("prompt", nargs="?", help="La richiesta da elaborare")
    parser.add_argument(
        "--sandbox", action="store_true",
        help="Esegui i blocchi Python della risposta nella sandbox",
    )
    parser.add_argument(
        "--no-persona", action="store_true",
        help="Bypass del filtro Rick (risposta tecnica pura)",
    )
    parser.add_argument(
        "--trace", action="store_true",
        help="Stampa il trace completo su stderr a fine run",
    )
    parser.add_argument(
        "--intensity", type=int, choices=[1, 2, 3, 4, 5], default=None,
        help="Livello ironia/personalità Rick (1=off, 3=classic, 5=toxic)",
    )
    parser.add_argument(
        "--ingest", type=str, metavar="DIR",
        help="Indicizza una cartella di documenti (.txt, .md, .pdf) nella memoria vettoriale",
    )
    parser.add_argument(
        "--wipe-memory", action="store_true",
        help="Cancella completamente la memoria (fatti e documenti) di Rick",
    )
    args = parser.parse_args()

    # ── Comandi Standalone (bypassa la pipeline LLM) ──────────────────────────
    if args.ingest:
        from rick.ingest import ingest_anything
        ingest_anything(args.ingest)
        sys.exit(0)

    if args.wipe_memory:
        import shutil
        import sqlite3
        from rick.config import BASE_DIR
        chroma_path = BASE_DIR / "data" / "chroma_db"
        facts_db = BASE_DIR / "data" / "facts.sqlite"
        wiped = []
        if chroma_path.exists():
            shutil.rmtree(chroma_path)
            wiped.append("memoria vettoriale (chroma)")
        if facts_db.exists():
            facts_db.unlink()
            wiped.append("fatti (sqlite)")
        print(f"Memoria cancellata: {', '.join(wiped)}.")
        sys.exit(0)

    # ── Legge il prompt da stdin se non fornito come argomento ────────────────
    if args.prompt:
        user_input = args.prompt
    elif not sys.stdin.isatty():
        user_input = sys.stdin.read().strip()
    else:
        parser.print_help()
        sys.exit(1)

    if not user_input:
        logger.error("Prompt vuoto.")
        sys.exit(1)

    # ── Overrides runtime ─────────────────────────────────────────────────────
    import rick.config as cfg
    if args.no_persona:
        cfg.PERSONA_IRONY = 1
    if args.intensity is not None:
        cfg.PERSONA_IRONY = args.intensity

    # ── Import del grafo ──────────────────────────────────────────────────────
    import sqlite3
    from langgraph.checkpoint.sqlite import SqliteSaver
    from rick.graph import build_graph
    from rick.config import DATA_DIR, BASE_DIR

    ckpt_path = BASE_DIR / "data" / "checkpoints.sqlite"
    ckpt_path.parent.mkdir(parents=True, exist_ok=True)
    _conn = sqlite3.connect(str(ckpt_path), check_same_thread=False)
    graph = build_graph(checkpointer=SqliteSaver(_conn))

    # ── Stato iniziale ────────────────────────────────────────────────────────
    session_id = str(uuid.uuid4())[:8]
    initial_state = {
        "user_input":        user_input,
        "session_id":        session_id,
        "intent":            "",
        "skills_needed":     [],
        "plan":              [],
        "current_step":      0,
        "expert_outputs":    [],
        "final_draft":       "",
        "audit_verdict":     "",
        "audit_notes":       None,
        "audit_passes":      0,
        "executor_passes":   0,
        "validator_retries": 0,
        "final_response":    "",
        "trace":             [],
    }

    # ── Esecuzione pipeline ───────────────────────────────────────────────────
    logger.info(f"=== Rick v8 | session {session_id} ===")
    t_start = time.time()

    final_state = initial_state.copy()
    try:
        cfg_run = {"configurable": {"thread_id": session_id}, "recursion_limit": 50}
        for event in graph.stream(initial_state, config=cfg_run):
            if not isinstance(event, dict):
                continue
                
            for node_name, state_update in event.items():
                if not isinstance(state_update, dict):
                    continue
                
                # Feedback visivo su stderr
                if node_name == "persona":
                    if state_update.get("final_response"):
                        logger.info("✅ Rick ha risposto.")
                    else:
                        logger.info("🎤 Rick sta pensando...")
                elif node_name == "manager":
                    logger.info("🧠 Manager: analisi della richiesta...")
                elif node_name == "expert_dispatcher":
                    logger.info("🔧 Expert Dispatcher: coordinamento esperti...")
                elif node_name == "auditor":
                    logger.info("🔍 Auditor: verifica della risposta...")
                elif node_name == "executor":
                    logger.info("⚙️  Executor: esecuzione comandi sandbox...")
                elif node_name == "output_validator":
                    logger.info("🛡️  Validator: controllo allucinazioni...")
                elif node_name == "memory_optimizer":
                    logger.info("🧠 Memory Optimizer: salvataggio fatti...")

                # Aggiorna final_state in modo sicuro
                for key, val in state_update.items():
                    if key in ["trace", "expert_outputs"]:
                        if key in final_state and isinstance(final_state[key], list) and isinstance(val, list):
                            final_state[key].extend(val)
                        else:
                            final_state[key] = val
                    else:
                        final_state[key] = val

    except Exception as e:
        logger.error(f"Errore durante l'esecuzione del grafo: {e}")
        sys.exit(1)
    finally:
        # Pulizia sandbox finale per sicurezza
        try:
            from sandbox import RickSandbox
            RickSandbox(session_id).cleanup()
        except Exception:
            pass

    elapsed = round(time.time() - t_start, 1)
    logger.info(f"=== done in {elapsed}s ===")

    # ── Output finale ─────────────────────────────────────────────────────────
    intent = final_state.get("intent")
    skills = final_state.get("skills_needed", [])
    plan = final_state.get("plan", [])
    verdict = final_state.get("audit_verdict")
    
    # Riassunto tecnico su stderr (opzionale, lo mettiamo su stderr per non sporcare stdout)
    if intent:
        logger.info(f"[INTENTO] {intent}")
    if verdict:
        logger.info(f"[AUDIT] {verdict.upper()}")

    # LA RISPOSTA VERA va su stdout
    response = final_state.get("final_response") or final_state.get("final_draft", "")
    print("\n" + "═"*40)
    print(response)
    print("═"*40 + "\n")

    # ── Sandbox Post-Risposta ──────────────────────────────────────────────────
    if args.sandbox:
        try:
            from sandbox import run_code_from_response
            results = run_code_from_response(response, session_id=session_id)
            if not results:
                logger.info("[sandbox] nessun blocco Python trovato")
            else:
                print("\n── Sandbox Output ──────────────────────────────────")
                for r in results:
                    idx = r["block_index"]
                    if r.get("returncode") != 0:
                        print(f"[blocco {idx}] ERRORE (rc={r.get('returncode')})")
                        if r.get("stderr"): print(r["stderr"])
                    else:
                        print(f"[blocco {idx}] OK")
                        if r.get("stdout"): print(r["stdout"])
        except Exception as e:
            logger.error(f"[sandbox] Errore: {e}")

    # ── Scrivi trace JSONL ────────────────────────────────────────────────────
    trace_path = DATA_DIR / f"{session_id}.jsonl"
    trace = final_state.get("trace", [])
    with open(trace_path, "w", encoding="utf-8") as f:
        for entry in trace:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    logger.info(f"[trace] scritto in {trace_path}")

    if args.trace:
        print("\n── Trace ────────────────────────────────────────────", file=sys.stderr)
        for entry in trace:
            print(json.dumps(entry, ensure_ascii=False), file=sys.stderr)


if __name__ == "__main__":
    main()
