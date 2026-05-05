import logging
import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# Configure API key only if available
api_key = os.getenv("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)

def gemini_generate(
    model: str,
    prompt: str,
    system: str = "",
    temperature: float = 0.7,
) -> str:
    """
    Chiama l'API di Gemini e restituisce la risposta.
    
    Args:
        model: nome modello (es. "gemini-1.5-flash", "gemini-1.5-pro")
        prompt: testo utente
        system: system prompt
        temperature: temperatura
    """
    if not api_key:
        return "[ERROR:GEMINI_API_KEY_MISSING] API Key non configurata in .env"
        
    try:
        # Fallback to flash if not specified, though caller should specify
        model_name = model if model.startswith("gemini") else "gemini-1.5-flash"
        
        # Configuration
        generation_config = genai.GenerationConfig(
            temperature=temperature,
        )
        
        # Initialize model with system instruction if provided
        llm = genai.GenerativeModel(
            model_name=model_name,
            generation_config=generation_config,
            system_instruction=system if system else None
        )
        
        response = llm.generate_content(prompt)
        text = response.text.strip()
        logger.debug(f"[gemini] {model_name} → {len(text)} chars")
        return text
        
    except Exception as e:
        logger.error(f"[gemini] Errore inatteso: {e}")
        return f"[ERROR:{type(e).__name__}] {e}"
