import logging
import time
from rick.state import RickState
from sandbox import RickSandbox, extract_commands

logger = logging.getLogger(__name__)


def executor_node(state: RickState) -> dict:
    t0          = time.time()
    session_id  = state.get("session_id", "default")
    outputs     = state.get("expert_outputs", [])
    passes      = state.get("executor_passes", 0)

    if not outputs:
        return {"executor_passes": passes}

    last_output = outputs[-1]
    commands    = extract_commands(last_output)

    if not commands:
        return {"executor_passes": passes}

    sandbox          = RickSandbox(session_id)
    execution_results = []

    for cmd_type, cmd_content in commands:
        logger.info(f"[executor] esecuzione {cmd_type}: {cmd_content[:60]}...")

        res = sandbox.execute_bash(cmd_content) if cmd_type == "bash" \
              else sandbox.execute_python(cmd_content)

        # Formato leggibile dall'LLM con hint per il prossimo giro
        lines = [f"\n── RISULTATO {cmd_type.upper()} (giro {passes+1}) ──"]
        # DEBUG: Salvo l'output reale
        import json
        with open("/tmp/executor_last_run.json", "w") as f:
            json.dump(res, f)

        if res.get("blocked"):
            lines.append(f"BLOCCATO DALLA SANDBOX: {res['stderr']}")
        else:
            if res.get("stdout"):
                lines.append(f"OUTPUT:\n{res['stdout'].strip()}")
            if res.get("stderr"):
                lines.append(f"ERRORI/WARNING:\n{res['stderr'].strip()}")
            if res.get("error"):
                lines.append(f"ECCEZIONE: {res['error']}")
            lines.append(f"Exit code: {res.get('returncode', '?')}")

        lines.append(
            "ISTRUZIONE: leggi l'output sopra e fornisci la risposta finale "
            "includendo i dati numerici rilevanti. NON rieseguire lo stesso comando."
        )
        lines.append("──────────────────\n")
        execution_results.append("\n".join(lines))

    elapsed_ms = round((time.time() - t0) * 1000)
    logger.info(f"[executor] giro {passes+1}: {len(commands)} cmd in {elapsed_ms}ms")

    return {
        "expert_outputs":  execution_results,
        "executor_passes": passes + 1,
        "trace": [{
            "node":         "executor",
            "ts":           time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "duration_ms":  elapsed_ms,
            "commands_run": len(commands),
            "loop_pass":    passes + 1,
        }]
    }
