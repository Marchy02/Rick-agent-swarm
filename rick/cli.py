"""
CLI entry point — `python -m rick.cli "la tua richiesta"`

Features:
  - Esegue la pipeline completa (manager → coder → auditor → persona)
  - Stampa la risposta finale su stdout
  - Scrive il trace JSONL in data/traces/<session_id>.jsonl
  - Flag --sandbox: esegue i blocchi Python nella sandbox dopo la risposta
  - Flag --no-persona: bypass Rick (persona_intensity=0)
  - Flag --trace: stampa il trace completo a fine run
"""
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
        "--intensity", type=int, choices=[0, 1, 2], default=None,
        help="Intensità persona Rick (0=off, 1=lieve, 2=full)",
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
        from rick.config import BASE_DIR
        db_path = BASE_DIR / "data" / "chroma_db"
        if db_path.exists():
            shutil.rmtree(db_path)
            print("Memoria vettoriale formattata. Rick non ricorda più nulla.")
        else:
            print("La memoria è già vuota.")
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
    if args.no_persona:
        import rick.config as cfg
        cfg.PERSONA_INTENSITY = 0
    if args.intensity is not None:
        import rick.config as cfg
        cfg.PERSONA_INTENSITY = args.intensity

    # ── Import del grafo (qui perché config può essere modificata sopra) ──────
    from rick.graph import graph
    from rick.config import DATA_DIR

    # ── Stato iniziale ────────────────────────────────────────────────────────
    session_id = str(uuid.uuid4())[:8]
    initial_state = {
        "user_input":      user_input,
        "session_id":      session_id,
        "intent":          "",
        "skills_needed":   [],
        "plan":            [],
        "current_step":    0,
        "expert_outputs":  [],
        "final_draft":     "",
        "audit_verdict":   "",
        "audit_notes":     None,
        "audit_passes":    0,
        "executor_passes": 0,
        "final_response":  "",
        "trace":           [],
    }

    # ── Esecuzione pipeline ───────────────────────────────────────────────────
    logger.info(f"=== Rick v8 | session {session_id} ===")
    t_start = time.time()

    from sandbox import RickSandbox
    try:
        final_state = graph.invoke(initial_state)
    finally:
        # Pulisce la sandbox a fine sessione
        RickSandbox(session_id).cleanup()

    elapsed = round(time.time() - t_start, 1)
    logger.info(f"=== done in {elapsed}s ===")

    # ── Output finale ─────────────────────────────────────────────────────────
    response = final_state.get("final_response") or final_state.get("final_draft", "")
    print("\n" + response + "\n")

    # ── Sandbox ───────────────────────────────────────────────────────────────
    if args.sandbox:
        from sandbox import run_code_from_response
        results = run_code_from_response(response)
        if not results:
            logger.info("[sandbox] nessun blocco Python trovato")
        else:
            print("\n── Sandbox Output ──────────────────────────────────")
            for r in results:
                idx = r["block_index"]
                if r["timed_out"]:
                    print(f"[blocco {idx}] TIMEOUT")
                elif r["returncode"] != 0:
                    print(f"[blocco {idx}] ERRORE (rc={r['returncode']})")
                    if r["stderr"]:
                        print(r["stderr"])
                else:
                    print(f"[blocco {idx}] OK")
                    if r["stdout"]:
                        print(r["stdout"])

    # ── Scrivi trace JSONL ────────────────────────────────────────────────────
    trace_path = DATA_DIR / f"{session_id}.jsonl"
    trace      = final_state.get("trace", [])
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
