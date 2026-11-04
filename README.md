# Faro Administraciones

Asistente documental para comunidades de propietarios. Un administrador crea una comunidad, sube actas, reglamentos o texto, y pregunta en lenguaje natural. La ingesta corre en segundo plano. La respuesta trae citas con documento, página y fragmento, o dice que no hay evidencia suficiente.

## Arranque

Hace falta Docker.

```bash
docker compose up --build
```

- Aplicación: http://localhost:8080
- API y OpenAPI: http://localhost:8000/docs
- Jaeger: http://localhost:16686

El identificador de administrador es simulado. En la interfaz vale `admin.demo` o cualquier valor de letras, números y `._@-`. Viaja en la cabecera `X-User-Id`. Quien crea una comunidad es su único miembro.

Por defecto el LLM y los embeddings son el proveedor falso: no hace falta ninguna clave y las respuestas son deterministas.

## Variables de entorno

Están en [`.env.example`](.env.example). Compose ya arranca con valores locales. Para Gemini:

```bash
LLM_PROVIDER=gemini
EMBEDDING_PROVIDER=gemini
GEMINI_API_KEY=tu-clave
LLM_MODEL=gemini/gemini-2.0-flash
EMBEDDING_MODEL=gemini/text-embedding-004
```

OpenAI usa `LLM_PROVIDER=openai`, `OPENAI_API_KEY`, `gpt-4o-mini` y `text-embedding-3-small`. Groq solo sustituye el LLM: `LLM_PROVIDER=groq`, `GROQ_API_KEY` y, por defecto, `groq/openai/gpt-oss-120b`. Los embeddings se quedan en `fake`, porque Groq no ofrece un vector de 384 dimensiones; la búsqueda por texto español sigue activa. LiteLLM lee el nombre del modelo. La columna de pgvector es de 384 dimensiones: OpenAI pide esa dimensión y Gemini se recorta a 384. El proveedor falso no sale a la red.

## Desarrollo local, sin reconstruir las imágenes

Postgres y Redis pueden salir solo de Compose. En Windows el worker de Celery necesita el pool `solo`.

```bash
docker compose up -d postgres redis
cd backend
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\uvicorn app.main:app --port 8000
.venv\Scripts\celery -A app.worker:celery worker --loglevel=info --pool=solo
cd ../frontend
npm install
npm run dev
```

La interfaz de Vite queda en http://localhost:5173 y proxya `/api` hacia el puerto 8000.

## Tests

Hace falta PostgreSQL con pgvector. El servicio `postgres` de Compose sirve:

```bash
docker compose up -d postgres
cd backend
pip install -e ".[dev]"
pytest
```

En CI la variable `REQUIRE_POSTGRES=1` hace fallar la suite si la base no está. Sin esa variable, y sin Postgres, los tests de integración se saltan y los unitarios siguen corriendo.

```bash
ruff check .
```

El conjunto de evaluación está en [`eval/cases.json`](eval/cases.json). Mide si la cita esperada aparece (documento y página) y si las preguntas sin soporte se abstienen. No mide la calidad de la redacción ni castiga una cita de más. Son cuatro documentos sintéticos, no un corpus real de fincas.

## Qué está hecho

- API FastAPI con comunidades, subida de PDF y texto, estado de ingesta y preguntas. Modelos Pydantic.
- Celery y Redis, tarea idempotente, estados `pending`, `processing`, `ready` y `failed`.
- Parseo con PyMuPDF, chunking por página, embeddings y pgvector.
- Recuperación híbrida (vector + texto español) y respuestas con citas comprobadas contra los fragmentos.
- Abstención, un reintento y degradación si el modelo no devuelve JSON válido. Timeout y límite de uso no inventan una respuesta.
- React con subida, polling del estado y citas que abren el fragmento.
- Proveedor falso y proveedores Gemini, OpenAI y Groq (solo el LLM) por configuración.
- OpenTelemetry desde la petición HTTP hasta Celery, la base y el LLM. Logs JSON con `trace_id`.
- Tests unitarios, de integración contra Postgres y el conjunto de evaluación. GitHub Actions ejecuta Ruff, Pytest y el build de las imágenes.

Una traza comentada está en [`docs/trace-example.md`](docs/trace-example.md).

## Qué no está hecho

- OCR. Un PDF escaneado sin texto queda `failed` con `no_text_layer`.
- Docling. Se descartó por el peso de la imagen y del CI.
- Login real, JWT y gestión de varios administradores por comunidad más allá de la membresía simulada.
- Almacén de objetos. El archivo vive en Postgres, con tope de 20 MB y 80 páginas.
- Un juez que resuelva contradicciones entre documentos. El sistema las muestra y cita ambas.
- Tests de interfaz. El contrato se cubre por la API.
- Un dataset real ni una métrica de calidad de la prosa.
