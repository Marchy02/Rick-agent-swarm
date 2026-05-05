# Rick Agent Refactored — Quick Start

## File da sostituire nel progetto originale

```bash
# Backup prima di tutto
cp -r v8 v8_backup

# Copia i file fixati
cp rick_refactored/rick/memory.py v8/rick/memory.py
cp rick_refactored/rick/graph.py v8/rick/graph.py
cp rick_refactored/rick/nodes/auditor.py v8/rick/nodes/auditor.py
cp rick_refactored/rick/ingest.py v8/rick/ingest.py
cp rick_refactored/rick/nodes/memory_optimizer.py v8/rick/nodes/memory_optimizer.py
cp rick_refactored/rick/config.py v8/rick/config.py
cp rick_refactored/rick/llm/prompts/persona_rick.md v8/rick/llm/prompts/persona_rick.md

# Elimina file non più necessari
rm v8/rick/nodes/validator.py
rm -rf v8/rick_optimizer/

# Test
cd v8
python -m rick.cli
```

## Cosa è stato fixato

✅ **Loop infinito risolto**: Eliminato validator ridondante, flusso semplificato  
✅ **Ollama 500 risolto**: Chunking più piccolo, retry con backoff  
✅ **Memory funzionante**: Lazy init, deduplica, bilanciamento ricordi/docs  
✅ **Personalità controllata**: Switch a qwen2.5:7b, intensity ridotta, esempi nel prompt  
✅ **PDF support**: Ingestione ora supporta .txt, .md, .pdf  
✅ **ID duplicati risolti**: Hash MD5 per deduplica automatica  

Leggi `docs/REFACTORING_GUIDE.md` per i dettagli completi.
