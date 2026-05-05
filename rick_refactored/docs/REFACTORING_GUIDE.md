# Rick Agent — Refactoring Completo

## 🔴 Problemi risolti

### 1. Loop infinito validator ↔ dispatcher
**Causa**: Il validator cercava output dell'executor che non c'era, lo interpretava come allucinazione, rimandava al dispatcher. Il dispatcher vedeva che non c'erano expert da chiamare, rimandava al validator. Loop infinito fino a crash.

**Fix**: **Eliminato completamente il validator**. È ridondante — l'auditor fa già la verifica. Nuovo flusso:
```
persona → memory_optimizer → manager → [experts] → auditor → persona
                                  ↓                      ↓
                                 END                  manager (se fail)
```

### 2. Ollama 500 durante ingestione
**Causa**: Blocchi di testo troppo grossi mandati all'embedding model. Ollama crash con "Internal Server Error".

**Fix**: Chunking più piccolo (400 parole invece di intero file), retry con backoff esponenziale, rate limiting (0.5s tra chunk).

### 3. ID duplicati in ChromaDB
**Causa**: `mem_id = f"mem_{int(time.time())}"` → due save nello stesso secondo = crash.

**Fix**: Hash MD5 del contenuto come ID. Deduplica automatica.

### 4. Knowledge base sempre ignorata
**Causa**: `combined[:limit]` tagliava sempre la knowledge se c'erano 5+ ricordi.

**Fix**: `limit//2` da ogni collezione, poi merge e taglia.

### 5. Personalità esagerata
**Causa**: `dolphin-llama3:8b` uncensored + `PERSONA_INTENSITY=2` + prompt senza esempi.

**Fix**: Switch a `qwen2.5:7b` + `PERSONA_INTENSITY=1` + prompt con esempi concreti.

### 6. ChromaDB init all'import
**Causa**: Se Ollama non gira, l'import esplode prima di `main()`.

**Fix**: Lazy init — ChromaDB si inizializza solo al primo uso.

### 7. Agent Lightning inesistente
**Causa**: `optimize.py` esiste ma non è connesso al grafo. Nessun pezzo di codice lo chiama o scrive i file che dovrebbe leggere.

**Fix**: Per ora eliminato dal refactoring. Se vuoi implementarlo, va integrato nel grafo come nodo separato.

---

## 📦 File da sostituire

### Nel progetto originale:

```bash
cp memory_fixed.py          rick/memory.py
cp graph_fixed.py           rick/graph.py
cp auditor_fixed.py         rick/nodes/auditor.py
cp ingest_fixed.py          rick/ingest.py
cp memory_optimizer_fixed.py rick/nodes/memory_optimizer.py
cp config_fixed.py          rick/config.py
cp persona_rick_fixed.md    rick/llm/prompts/persona_rick.md
```

### Da eliminare:

```bash
rm -rf rick/nodes/validator.py      # Non serve più
rm -rf rick/nodes/optimize.py       # Non connesso
rm -rf rick_optimizer/              # Directory vecchia
```

---

## 🧪 Test dopo il refactoring

### 1. Test conversazione base
```bash
python -m rick.cli
> ciao come va
# Dovrebbe rispondere senza chiamare expert o andare in loop
```

### 2. Test con expert
```bash
> scrivimi un hello world in Python
# Dovrebbe chiamare coder → auditor → risposta
# Log: [manager] skills_needed: ['coder']
```

### 3. Test memoria
```bash
> mi piace il calcio
# Salva in memoria
> cosa ti ricordi di me?
# Dovrebbe recuperare "mi piace il calcio"
```

### 4. Test ingestione
```bash
python -m rick.ingest data/notes/
# Dovrebbe processare tutti i file .txt/.md/.pdf senza errori 500
# Log: [ingest] Split into N chunks
```

### 5. Test audit fail
```bash
> FastAPI versione 0.96.0 esiste?
# Se il coder/researcher inventa dati, l'auditor dovrebbe bocciare
# Log: [auditor] Verdict: fail
```

---

## ⚙️ Ottimizzazioni future (opzionali)

### A. Streaming risposta
Ora Rick risponde solo alla fine. Puoi aggiungere streaming nella `persona_node` per vedere la risposta in tempo reale.

### B. Cache embedding
Ollama ricalcola gli embedding ogni volta. Aggiungi cache locale (Redis/file JSON) per query ripetute.

### C. Agent Lightning vero
Implementa un loop di feedback:
1. Dopo ogni sessione, l'auditor salva metriche (pass/fail rate, issue types)
2. Un nodo `optimizer` legge le metriche e riscrive le guidelines degli expert
3. Le guidelines aggiornate vengono caricate dal dispatcher

### D. Multi-turn conversation
Ora ogni query è isolata. Aggiungi history management nello stato per conversazioni lunghe.

### E. Pruning memoria
ChromaDB cresce all'infinito. Aggiungi un job che elimina ricordi vecchi (>30 giorni) o irrilevanti.

---

## 🐛 Debug checklist

Se qualcosa va storto:

1. **Loop infinito ancora presente?**
   - Check log: quale nodo continua a ripetersi?
   - Verifica che `after_audit` abbia il fallback su verdict sconosciuti

2. **Ollama 500 ancora?**
   - Riduci CHUNK_SIZE da 400 a 200
   - Aumenta sleep tra chunk da 0.5s a 1s

3. **Personalità ancora esagerata?**
   - Verifica che MODEL_PERSONA sia `qwen2.5:7b` in config
   - Verifica che PERSONA_INTENSITY sia 1

4. **Memory non funziona?**
   - Check se ChromaDB si inizializza: log `[memory] ChromaDB initialized`
   - Verifica che Ollama abbia `nomic-embed-text` installato: `ollama pull nomic-embed-text`

5. **Expert non risponde?**
   - Check timeout: log `[ERROR:TIMEOUT]`
   - Aumenta OLLAMA_TIMEOUT in config da 180 a 300

---

## 📊 Metriche di successo

Dopo il refactoring, dovresti vedere:

- ✅ Zero loop infiniti (nessun `GraphRecursionError`)
- ✅ Ingestione completa senza errori 500
- ✅ Personalità Rick presente ma controllata (non esagerata)
- ✅ Memory funzionante (ricordi e docs vengono recuperati)
- ✅ Audit che blocca allucinazioni (log `[auditor] Verdict: fail`)
- ✅ Tempo risposta <30s per query normali
- ✅ Log leggibili senza errori critici

---

## 🚀 Quick start

```bash
# Backup vecchia versione
mv v8 v8_backup

# Applica fix
cp memory_fixed.py rick/memory.py
cp graph_fixed.py rick/graph.py
cp auditor_fixed.py rick/nodes/auditor.py
cp ingest_fixed.py rick/ingest.py
cp memory_optimizer_fixed.py rick/nodes/memory_optimizer.py
cp config_fixed.py rick/config.py
cp persona_rick_fixed.md rick/llm/prompts/persona_rick.md

# Elimina vecchi file
rm rick/nodes/validator.py
rm -rf rick_optimizer/

# Test veloce
python -m rick.cli
> ciao
# Se risponde senza loop = successo
```

---

## 💡 Filosofia del refactoring

**Eliminato**:
- Validator (ridondante con auditor)
- Agent Lightning non connesso
- Complessità inutile nella routing logic

**Semplificato**:
- Flusso lineare: persona → manager → experts → auditor → persona
- Memory con lazy init e deduplica automatica
- Ingestione robusta con retry

**Migliorato**:
- Auditor gestisce correttamente "niente da verificare"
- Chunking intelligente per evitare Ollama crash
- Personalità bilanciata con esempi concreti

**Risultato**: Sistema lean, stabile, senza loop, con memoria funzionante.
