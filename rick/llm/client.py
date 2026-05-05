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


import logging
import time
import httpx
from rick.config import OLLAMA_BASE_URL, OLLAMA_TIMEOUT
from rick.llm.gemini import gemini_generate

logger = logging.getLogger(__name__)


def ollama_generate(
    model: str,
    prompt: str,
    system: str = "",
    temperature: float = 0.7,
    keep_alive: str = "5m",
) -> str:
    """Chiama POST /api/generate di Ollama in locale."""
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


def llm_generate(
    provider: str,
    model: str,
    prompt: str,
    system: str = "",
    temperature: float = 0.7,
    keep_alive: str = "5m",
) -> str:
    """
    Router unificato per chiamare Ollama o Gemini in base al provider.
    """
    if provider == "gemini":
        return gemini_generate(
            model=model,
            prompt=prompt,
            system=system,
            temperature=temperature
        )
    else:
        return ollama_generate(
            model=model,
            prompt=prompt,
            system=system,
            temperature=temperature,
            keep_alive=keep_alive
        )
