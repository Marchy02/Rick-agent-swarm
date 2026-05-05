# 🛸 PROJECT RICK: THE FINAL OVERHAUL (BRIEFING FOR CLAUDE)

Ascolta bene, Claude. Abbiamo un sistema multi-agente basato su LangGraph che emula Rick Sanchez (C-137). Funziona, ma vogliamo che sia **perfetto**. Non vogliamo un'assistente, vogliamo Rick che controlla un esercito di esperti locali (Ollama).

---

## 🎯 OBIETTIVI SUPREMI

### 1. Agent-Lightning (RLAIF Pipeline)
Attualmente salviamo i trace in `data/traces/*.jsonl`. 
*   **Missione**: Implementa un sistema (nodo o script esterno) che analizzi questi trace, estragga "lezioni imparate" (es. errori di sintassi bash, timeout sandbox, allucinazioni dell'auditor) e le scriva nei file `_guidelines.txt` degli esperti.
*   **Iniezione Context**: Ogni esperto DEVE leggere le sue linee guida aggiornate prima di ogni task. Il sistema deve imparare dai suoi fallimenti.

### 2. Validazione Logica & Debugging
Rick non deve solo "scrivere", deve garantire che la logica sia impeccabile.
*   **Analisi Step-by-Step**: Prima di finalizzare, il Coder deve eseguire un "debug mentale" della soluzione, verificando i casi limite e la coerenza del flusso.
*   **Obbligo di Spiegazione**: Rick deve essere in grado di spiegare la logica dietro le sue scelte tecniche. Non vogliamo solo codice, vogliamo la "scienza" che c'è dietro.
*   **Correzione Iterativa**: Se l'Auditor o l'utente rilevano un dubbio logico, il sistema deve ri-analizzare l'intero piano invece di fare correzioni superficiali.

### 3. Ingestione Dati & RAG Perfetto
La gestione degli appunti deve essere impeccabile.
*   **Deduplica**: Implementa MD5 hashing dei chunk per evitare duplicati in ChromaDB.
*   **Formati**: Supporto totale e robusto a PDF, Markdown e codice sorgente (Python, JS, C++, ecc.) con chunking intelligente (max 400 parole).
*   **Reperimento**: Il recupero degli appunti deve essere perfetto. Rick deve citare i fatti di Marco correttamente.

### 3. Personalità Rick C-137 (Strict Separation)
Il sistema a placeholder `{draft}` in `persona_rick.md` è la base, ma va perfezionato.
*   **Regola Ferrea**: L'esperto (Coder, Sysadmin, ecc.) produce la risposta tecnica perfetta. Rick deve aggiungere l'involucro (insulti, ruttini, cinismo) **SENZA TOCCARE IL CODICE O I DATI TECNICI**.
*   **Output**: Se chiedo uno script, voglio lo script. Non una parafrasi di Rick che rompe i tab.

### 4. Pulizia Tecnica (Zero Warning)
Il terminale deve essere pulito come il garage di Rick dopo una passata di laser.
*   **Pydantic v1**: Silenzia o risolvi i warning di incompatibilità con Python 3.14.
*   **Gemini Client**: Migra `rick/llm/gemini.py` alla nuova libreria `google-genai`.
*   **Stabilità Ollama**: Rafforza la gestione degli errori 500 durante gli embedding.

### 5. Sandbox Reale & Flag Workspace
L'attuale sandbox in `/tmp` è limitata.
*   **Docker/Debian**: Valuta l'integrazione di un container Docker (Debian) per far girare i comandi in totale isolamento.
*   **Flag `--workspace <path>`**: Implementa nel `cli.py` la possibilità di specificare una cartella di lavoro reale. Rick deve poter leggere e scrivere lì.
*   **Consenso Informato**: Se Rick lavora in un workspace reale, DEVE chiedere il permesso esplicito (Human-in-the-loop) prima di eseguire comandi di scrittura o cancellazione (`rm`, `mv`, `write`).

### 6. Fondamenta d'Acciaio (Core Stability)
Le basi devono essere solide per supportare un'intelligenza superiore.
*   **Persistenza del Grafo**: Implementa un `Checkpointer` (es. `SqliteSaver`) per LangGraph. Le sessioni non devono andare perse se il processo si interrompe.
*   **Tool Calling Nativo**: Passa dai tag XML al tool-calling nativo di Ollama. Modelli come `qwen2.5-coder` sono ottimizzati per questo.
*   **Architettura Async**: Migra il client e i nodi verso `async/await` per migliorare la gestione dei flussi e dello streaming.
*   **Validation Layer**: Usa Pydantic per validare lo stato del grafo e gli output del Manager, eliminando i crash per "JSON malformato".

---

## 🛠 STATO ATTUALE (POST-FIX)
*   **Flow**: `persona -> optimizer -> manager -> experts -> auditor -> persona`.
*   **Nodi Riparati**: `manager.py`, `persona.py`, `auditor.py` e `graph.py` sono stati allineati a mano dopo un refactoring parziale.
*   **Client**: `client.py` ora supporta `call_llm` e `ollama_generate`.

---

**Claude, prendi questo progetto e rendilo la cosa più cazzuta del multiverso. Non deluderci.**
