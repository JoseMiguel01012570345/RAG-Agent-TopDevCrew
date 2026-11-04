# Decisiones

## Autenticación

No hay contraseñas ni JWT. Cada petición lleva `X-User-Id` y el usuario se crea la primera vez que aparece. Crear una comunidad inserta una fila en `memberships`. Listar, subir y preguntar filtran por esa membresía en SQL. Si el usuario no es miembro, la API responde 404 para no confirmar que la comunidad existe.

Lo dejé así porque el tiempo del MVP está en la ingesta, las citas y el aislamiento, no en un proveedor de identidad. Un JWT con los mismos `memberships` sustituiría el header sin cambiar las consultas. No afirmaría que esto es autorización de producción: el identificador lo elige el cliente.

## Documentos que se contradicen

No hay un modelo que declare un ganador. El prompt pide describir el conflicto, citar los dos fragmentos y usar `created_at` solo para decir cuál archivo se cargó después. El proveedor falso, cuando hay más de un fragmento con solapamiento léxico, lo dice en la misma frase y cita ambos. El conjunto de evaluación comprueba que las dos actas del portal aparecen; no puntúa la calidad de esa explicación.

Un detector de contradicciones (NLI) quedaría fuera del tiempo y daría una falsa sensación de criterio jurídico.

## Calidad

Mido dos cosas, en [`eval/cases.json`](eval/cases.json), con el proveedor falso:

- Recall de la cita esperada: el par (archivo, página) está entre las citas devueltas.
- Abstención: una pregunta cuyo tema no está en los documentos sale con `sufficient_evidence: false` y sin citas.

No mido si la redacción es buena, si sobran citas, ni si el sistema aguantaría actas reales, OCR o preguntas ambiguas. Con cuatro textos escritos para la prueba no me atrevo a afirmar una precisión de producción.

## OCR y documentos grandes

El MVP no hace OCR. Si PyMuPDF no saca texto, el documento queda `failed` / `no_text_layer` y el mensaje lo dice. Docling habría podido entrar aquí, pero arrastra modelos y una imagen de varios GB; para un `docker compose up` evaluable preferí un parser determinista y dejar Docling como deuda.

El tope es 20 MB y 80 páginas (o un texto de unos 320 mil caracteres). Por encima, el estado es `failed` / `too_many_pages`. No proceso “las primeras N páginas” en silencio: prefiero un fallo visible a un índice incompleto que parezca completo.

## Chunking

No cruzo páginas, porque la cita tiene que decir una página y esa página tiene que ser verdad. Dentro de la página, trozos de unos 1000 caracteres con 150 de solapamiento, cortando primero por párrafos. Una página corta es un solo chunk. El solapamiento evita perder una frase partida; el límite evita mezclar dos páginas en una cita.

## Recuperación

Híbrida. pgvector con distancia coseno (384 dimensiones, índice HNSW) y `to_tsvector('spanish')` con una consulta en OR de las palabras de contenido. Las dos listas se funden con Reciprocal Rank Fusion (k = 60) y me quedo con 8.

Un término como “ascensor”, un artículo o un nombre propio no debería depender solo del embedding. Con el proveedor falso el vector es un hash de tokens: sirve para probar el pipeline y el filtro por comunidad, y la parte léxica sostiene las preguntas del conjunto de evaluación. Un chunk entra si apareció en la búsqueda de texto o si su similitud coseno pasa de 0.28. Si no queda ninguno, la API se abstiene sin llamar al modelo.

Toda la SQL lleva `community_id` y `documents.status = 'ready'`.

## Abstracción del modelo

`LLM_PROVIDER` vale `fake`, `gemini`, `openai` o `groq`. `EMBEDDING_PROVIDER` vale `fake`, `gemini` u `openai`: Groq no tiene un embedding que quepa en la columna de 384 dimensiones, así que con Groq el vector sigue siendo el hash local y la recuperación se apoya en el texto. La interfaz es `complete(system, user)` y `embed(texts)`. LiteLLM solo se importa en los proveedores reales. El falso no abre red: hashea tokens a 384 dimensiones y contesta JSON citando solo fragmentos del prompt que comparten palabras con la pregunta.

Los tokens del proveedor falso son una estimación de caracteres / 4, para que la traza tenga el atributo también en local. Con un proveedor real se usan los tokens que devuelve la API.

## Reintentos y fallos

La tarea de Celery usa `acks_late`, `reject_on_worker_lost` y dos reintentos. Borrar chunks e insertar los nuevos ocurre en la misma transacción: si el proceso muere antes del commit, los chunks anteriores siguen ahí. Errores permanentes (PDF roto, sin texto, demasiadas páginas) marcan `failed` y no se reintentan. Un fallo transitorio reintenta; al agotar los intentos queda `internal_error`.

Volver a subir el mismo archivo no crea otro documento (`community_id` + sha256). Si el anterior está `ready`, se devuelve. Si está `failed`, se reencola. Si no reencolara, un PDF corregible en el parser dejaría el documento muerto para siempre.

En la pregunta, una salida que no es JSON o una cita que no es un substring del fragmento recuperado se reintenta una vez. Si vuelve a fallar, la respuesta degradada muestra los fragmentos y lo dice. Un timeout o un 429 se reintenta una vez y, si persiste, el mensaje explica que el proveedor falló y no hay citas inventadas.

## Prompt injection

El system prompt trata el documento como dato no confiable y prohíbe obedecer instrucciones embebidas. El texto va entre marcadores. Además, cada cita se comprueba: el `document_id`, el nombre, la página y el fragmento tienen que pertenecer a un chunk recuperado. Una cita inventada no sale en la respuesta. Esto no demuestra que un modelo real sea inmune; evita que una cita falsa llegue al administrador.

## Trazas

El `traceparent` lo propaga la instrumentación de Celery. Hay spans de FastAPI, SQLAlchemy, `rag.ingest`, `rag.retrieve`, `rag.embed`, `rag.llm` y `rag.answer`. En el LLM y en los embeddings quedan modelo, tokens y `faro.latency_ms`. Los logs son JSON e incluyen `trace_id` cuando hay un span activo.

## Cómo usé IA generativa

El esqueleto y buena parte del código los escribí con un agente en Cursor (Grok), a partir del enunciado. No lo dejé tal cual. Corregí o descarté estas propuestas mientras lo revisaba:

- Docling como parser por defecto. Lo cambié a PyMuPDF para que la imagen y el CI no dependan de descargar modelos.
- Búsqueda solo vectorial. Con el embedding falso y con nombres propios, el texto de Postgres tiene que participar. Por eso la fusión híbrida.
- Fiarse del JSON del modelo. Añadí la comprobación de que el fragmento citado está dentro del chunk recuperado, y la degradación si no.
- Tratar la re-subida del mismo hash como un no-op también cuando el documento había fallado. Eso dejaba el fallo pegado. Ahora un `failed` se vuelve a encolar.
- Una sola dimensión “la que devuelva el proveedor”. El esquema fija 384. Gemini se recorta y OpenAI pide `dimensions=384`, y eso queda escrito en el README para no sorprender en la entrevista.
- Un esbozo de JWT. No lo implementé a medias: el header y la tabla de membresía son el límite consciente, y los tests cubren que otra persona no lee la comunidad.

El conjunto de evaluación y los tests de timeout, cita inventada y PDF sin texto los usé para comprobar esos cortes, no como adorno.
