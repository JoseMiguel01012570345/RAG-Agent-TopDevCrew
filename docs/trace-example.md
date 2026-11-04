# Traza de una consulta

Esta es la forma de la traza de una pregunta con documentos ya ingeridos y el proveedor falso, tal como la dibuja la instrumentación en Jaeger (`http://localhost:16686`, servicio `faro-api`). El collector recibe el mismo árbol. El JSON de abajo ilustra los atributos que el código escribe en `rag.llm`; una ejecución concreta cambia tokens y latencia.

## Qué se ve

```text
faro-api  POST /communities/{id}/questions          ~40–200 ms
└─ rag.answer
   ├─ rag.retrieve
   │  ├─ rag.embed          model=fake-hash-384  input_tokens≈N  faro.latency_ms
   │  └─ SQL SELECT chunks  (pgvector + tsvector, filtro community_id)
   └─ rag.llm               model=fake-answer    input_tokens  output_tokens  faro.latency_ms
```

La ingesta, en el servicio `faro-worker`, es otra traza continua. Celery propaga el `traceparent` de la petición que subió el archivo:

```text
faro-api  POST /communities/{id}/documents
└─ celery apply  app.tasks.ingest_document
   └─ faro-worker  run app.tasks.ingest_document
      └─ rag.ingest
         ├─ rag.embed
         └─ SQL INSERT chunks / UPDATE documents
```

Atributos que importan para costo y tiempo:

- `gen_ai.request.model`: `fake-answer`, `fake-hash-384`, o el modelo de Groq o de Google AI Studio.
- `gen_ai.usage.input_tokens` y `gen_ai.usage.output_tokens`.
- `faro.latency_ms` en el embed y en el LLM.
- `faro.community_id`, `rag.chunk_count`, `rag.sufficient_evidence`, `rag.degraded`.

Los logs de `faro.qa` y `faro.ingest` van en JSON. Si el log ocurre dentro del span, llevan `trace_id` y `span_id` para cruzarlos con Jaeger.

Ejemplo de span `rag.llm` (proveedor falso, pregunta con una cita válida):

```json
{
  "name": "rag.llm",
  "attributes": {
    "gen_ai.request.model": "fake-answer",
    "gen_ai.usage.input_tokens": 180,
    "gen_ai.usage.output_tokens": 70,
    "faro.latency_ms": 1.2
  }
}
```

Con el proveedor falso esos tokens son `len(texto) / 4`, no una factura. Con Groq o Google AI Studio el valor sale del `usage` de LiteLLM. La latencia del falso es casi solo CPU; en un proveedor real el mismo atributo concentra la espera de red y es lo primero que miro si una pregunta se va de tiempo.

## Qué aprendí al recorrerla

Casi todo el tiempo de una pregunta, con el falso, está en Postgres (dos búsquedas: vector y texto), no en el modelo. El span `rag.embed` es barato en local y pasa a ser una llamada de red en cuanto se cambia el proveedor: por eso el modelo y los tokens están en ese span y no solo en el del chat. Si el modelo devuelve una cita que no está en los chunks, no aparece un segundo `rag.retrieve`: el reintento es otro `rag.llm` dentro del mismo `rag.answer`, y `rag.degraded` queda en true si ese segundo intento también falla. Así se distingue “no había evidencia” de “el modelo no supo citar”.

La ingesta no comparte el span de la pregunta. Si un documento se queda en `processing`, la traza que hay que abrir es la del `POST` de subida y el servicio `faro-worker`, no la del chat.
