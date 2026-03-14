# CogerLaPala

MVP para automatizar postulaciones de trabajo con un flujo seguro:

1. Descubre vacantes segun parametros (fuentes enchufables).
2. Puntua cada vacante por compatibilidad con tu perfil.
3. Genera respuestas de formulario con heuristicas + IA opcional.
4. Ejecuta automatizacion web con Playwright en modo `dry-run` por defecto.

## Stack

- Python + FastAPI
- Playwright para automatizacion de navegador
- OpenAI API opcional para mapear preguntas de formularios
- Modelo de pipeline con controles de seguridad

## Estructura

```text
.
├── app.py
├── .env.example
├── examples/sample_request.json
├── examples/linkedin_request.json
├── scripts/run_pipeline.py
├── src/cogerlapala/
│   ├── entrypoint.py
│   ├── gui_app.py
│   ├── main.py
│   ├── models.py
│   └── services/
│       ├── matching.py
│       ├── ai_mapper.py
│       ├── browser_automator.py
│       ├── application_orchestrator.py
│       ├── linkedin_easy_apply.py
│       ├── pipeline.py
│       ├── job_sources/demo_source.py
│       └── job_sources/linkedin_source.py
└── requirements.txt
```

## Instalacion

```bash
pip install -U pip
python -m pip install -r requirements.txt
python -m playwright install chromium
```

## Configuracion

1. Copia `.env.example` a `.env`.
2. Si quieres usar IA para respuestas, agrega `OPENAI_API_KEY`.

Variables relevantes:

- `MIN_MATCH_SCORE`: umbral minimo de aplicacion.
- `MAX_DAILY_APPLICATIONS`: limite diario del pipeline.
- `DEFAULT_DRY_RUN`: modo seguro por defecto.
- `SCREENSHOT_DIR`: carpeta de capturas durante automatizacion.
- `DEFAULT_REQUEST_FILE`: request por defecto para el arranque unico.
- `START_MODE`: `command`, `signal` o `immediate`.
- `START_SIGNAL_FILE`: ruta del archivo de senal para modo `signal`.
- `START_SIGNAL_TIMEOUT_SECONDS`: timeout en segundos en modo `signal`.

Variables LinkedIn:

- `LINKEDIN_EMAIL`: opcional, para login automatico.
- `LINKEDIN_PASSWORD`: opcional, para login automatico.
- `LINKEDIN_STORAGE_STATE`: archivo de sesion persistente.
- `LINKEDIN_HEADLESS`: `false` recomendado en primer uso para login/MFA.
- `LINKEDIN_MANUAL_LOGIN_TIMEOUT_SECONDS`: tiempo para login manual.
- `LINKEDIN_MAX_SEARCH_PAGES`: numero de paginas de resultados a recorrer.

## Inicio Unico (Recomendado)

Ejecuta siempre este comando para abrir la aplicacion con interfaz grafica:

```bash
python app.py
```

La app no inicia solicitudes automaticamente. Desde la interfaz puedes:

1. Cargar/guardar request JSON.
2. Seleccionar CV desde explorador de archivos.
3. Ajustar parametros de perfil, busqueda y ejecucion.
4. Lanzar `Preview` o `Run` con botones.

Si quieres abrir la app con un request concreto:

```bash
python app.py --request examples/sample_request.json
```

## Modos Avanzados

- Modo CLI (flujo por terminal):

```bash
python app.py --cli --request examples/sample_request.json
```

- Modo API (FastAPI):

```bash
python app.py --api
```

## Ejecutar Pipeline por CLI (Avanzado)

```bash
python app.py --cli --request examples/sample_request.json
```

Tambien puedes usar el script directo:

```bash
python scripts/run_pipeline.py --request examples/sample_request.json
```

El archivo `examples/sample_request.json` trae un ejemplo completo de:

- perfil
- parametros de busqueda
- opciones de ejecucion

## Flujo LinkedIn (busqueda + Easy Apply)

1. Copia `.env.example` a `.env` y configura, si quieres, `LINKEDIN_EMAIL` y `LINKEDIN_PASSWORD`.
2. Asegura `LINKEDIN_HEADLESS=false` en la primera ejecucion.
3. Abre la interfaz:

```bash
python app.py --request examples/linkedin_request.json
```

1. Desde la app, primero pulsa `Ejecutar Preview` para validar.
2. Luego pulsa `Ejecutar Run` cuando quieras aplicar.

En la primera corrida real, si no existe sesion guardada, el navegador te deja iniciar sesion manualmente y resolver MFA. Luego guarda estado en `LINKEDIN_STORAGE_STATE`.

Para envio real automatico:

1. En `examples/linkedin_request.json` cambia `dry_run` a `false`.
2. En `examples/linkedin_request.json` cambia `require_human_review` a `false`.
3. Ejecuta de nuevo el pipeline.

Notas del adapter LinkedIn:

- Busca empleos por criterios con soporte para `linkedin_easy_apply_only`.
- Intenta aplicar unicamente por flujos `Easy Apply`.
- Si una oferta no tiene `Easy Apply`, se marca como fallo controlado y sigue con la siguiente.
- `search.location` puede ser string (`"Madrid"`) o lista (`["Barcelona", "Madrid", "Galicia"]`).

### Problema Comun: "navegador no seguro" al usar Google

Google suele bloquear login OAuth en navegadores automatizados.

Solucion recomendada:

1. No uses el boton "Continuar con Google" dentro de la automatizacion.
2. Inicia sesion con email/password de LinkedIn.
3. Si tu cuenta es solo Google, crea una clave en LinkedIn (recuperar contrasena).
4. Guarda `LINKEDIN_EMAIL` y `LINKEDIN_PASSWORD` en `.env`.
5. Ejecuta de nuevo `python app.py`.

Tras el primer login correcto, la sesion queda guardada en `LINKEDIN_STORAGE_STATE`.

## Seguridad Operativa

- `dry_run=true` evita envio real.
- `require_human_review=true` bloquea submit real aunque `dry_run=false`.
- `enable_browser_automation=false` permite solo generar respuestas sin abrir navegador.

## API (Avanzado)

```bash
python app.py --api
```

Tambien puedes arrancarla con uvicorn:

```bash
uvicorn cogerlapala.main:app --reload
```

Endpoints:

- `GET /health`
- `POST /pipeline/preview` (sin enviar)
- `POST /pipeline/run` (ejecuta el pipeline)

## Agregar Fuentes Reales

La clase `DemoAutonomousSource` es una fuente de ejemplo.
Para produccion, implementa un adapter nuevo con la misma firma:

```python
async def search(self, params: SearchParameters) -> list[JobPosting]
```

Luego registra la fuente en `build_default_pipeline`.

## Nota de cumplimiento

Si conectas portales como LinkedIn, respeta sus terminos de servicio,
politicas de automatizacion y limites de uso. Este proyecto deja controles
de revision humana y modo seguro para reducir riesgos operativos.

No se incluye bypass de captcha, MFA ni mecanismos de seguridad de plataforma.
