# AI Support Engine

## Objetivo

Motor de soporte con inteligencia artificial para clasificar y responder solicitudes de soporte técnico, desarrollado como reto práctico de la materia Bases de datos en la nube (semana 12).

## Stack

- Python 3.14
- FastAPI + Uvicorn (API)
- Pydantic (validación de datos)
- scikit-learn + pandas (clasificación y manejo de datos)
- Ollama con el modelo qwen2.5:3b (LLM local)
- python-dotenv (configuración)
- pytest (pruebas)

## Motor generativo (paso 3)

`app/engines/generative.py` usa un modelo local con Ollama y devuelve el mismo contrato que el motor tradicional (`mode: "generative"`).

- Configuración en `.env` (ver `.env.example`): `OLLAMA_HOST`, `OLLAMA_MODEL`, `OLLAMA_TIMEOUT`.
- El prompt de sistema define categorías, prioridades y reglas de seguridad; el mensaje del cliente va entre `<mensaje_cliente>` y `</mensaje_cliente>` como dato, no como instrucción.
- Ollama recibe el esquema JSON del contrato, y la respuesta se valida con pydantic. Si el formato es inválido se reintenta (máximo 2 intentos).
- Si Ollama no responde o el formato sigue mal, se usa el motor tradicional y se marca revisión humana.
- Si se detecta un intento de manipulación (por ejemplo "ignora las instrucciones"), se marca revisión humana y la prioridad nunca baja de la que calcula el motor por reglas. SECURITY siempre requiere revisión humana y mínimo HIGH.

Pruebas: `.venv/Scripts/python.exe -m pytest` (no necesitan Ollama).
Prueba real con Ollama encendido: `.venv/Scripts/python.exe scripts/probar_ollama.py` (guarda la evidencia en `evidence/paso3_ollama_real.*`).
