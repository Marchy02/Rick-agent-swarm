"""
Client sincrono per Ollama.
Usa httpx in modalità sincrona — nessun async/await, compatibile con
LangGraph che gira in un event-loop gestito da lui.
"""
import logging
import time
import httpx
from rick.config import OLLAMA_BASE_URL, OLLAMA_TIMEOUT

logger = logging.getLogger(__name__)


def ollama_generate(
    model: str,
    prompt: str,
    system: str = "",
    temperature: float = 0.7,
    keep_alive: str = "5m",
) -> str:
    """
    Chiama POST /api/generate di Ollama e restituisce la risposta completa.

    Args:
        model:       nome modello Ollama (es. "qwen2.5:7b")
        prompt:      testo utente
        system:      system prompt (stringa, può essere vuoto)
        temperature: temperatura generazione
        keep_alive:  quanto tenere il modello in RAM ("0" = scarica subito)

    Returns:
        Testo generato, o stringa di errore in caso di failure.
    """
    url = f"{OLLAMA_BASE_URL}/api/generate"
    payload: dict = {
        "model":      model,
        "prompt":     prompt,
        "stream":     False,
        "keep_alive": keep_alive,
        "options": {
            "temperature": temperature,
            "num_predict": 2048,
        },
    }
    if system:
        payload["system"] = system

    t0 = time.time()
    try:
        with httpx.Client(timeout=OLLAMA_TIMEOUT) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            text = resp.json().get("response", "").strip()
            elapsed = round((time.time() - t0) * 1000)
            logger.debug(f"[ollama] {model} → {elapsed}ms, {len(text)} chars")
            return text
    except httpx.TimeoutException:
        logger.error(f"[ollama] TIMEOUT dopo {OLLAMA_TIMEOUT}s per {model}")
        return f"[ERROR:TIMEOUT] Il modello {model} ha impiegato troppo."
    except httpx.HTTPStatusError as e:
        logger.error(f"[ollama] HTTP {e.response.status_code} per {model}")
        return f"[ERROR:HTTP_{e.response.status_code}]"
    except Exception as e:
        logger.error(f"[ollama] Errore inatteso: {e}")
        return f"[ERROR:{type(e).__name__}] {e}"


def call_llm(
    prompt: str,
    model: str = "qwen2.5:7b",
    temperature: float = 0.7,
    system: str = "",
    timeout: int | None = None,
    keep_alive: str = "5m",
) -> str:
    """
    Interfaccia semplificata per chiamare Ollama.
    Wrapper di ollama_generate con parametri opzionali più comodi.
    """
    return ollama_generate(
        model=model,
        prompt=prompt,
        system=system,
        temperature=temperature,
        keep_alive=keep_alive,
    )

def llm_generate(
    provider: str,
    model: str,
    prompt: str,
    system: str = "",
    temperature: float = 0.7,
    keep_alive: str = "5m",
) -> str:
    """
    Funzione di compatibilità per i vecchi nodi (manager, persona, dispatcher).
    Ignora il provider e usa sempre Ollama.
    """
    return ollama_generate(
        model=model,
        prompt=prompt,
        system=system,
        temperature=temperature,
        keep_alive=keep_alive
    )
