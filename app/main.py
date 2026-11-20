"""API de AI Support Engine (FastAPI).

POST /api/analyze  {message, mode: "traditional" | "generative"}
  -> {category, priority, response, requiresHumanReview, mode}

Errores (siempre JSON {"error": "..."} y sin eco del mensaje del usuario):
  400 petición inválida (JSON roto, campos faltantes o extra, mensaje vacío
      o de más de 2000 caracteres, modo desconocido)
  413 cuerpo de más de 64 KB
  415 Content-Type distinto de application/json
  500 falla interna (sin detalles al cliente)

Si Ollama no responde, el motor generativo usa el de reglas como respaldo y
marca revisión humana (la API sigue contestando 200).
"""

import asyncio
import json
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.contract import AnalyzeRequest, AnalyzeResponse, Mode
from app.engines import generative, traditional

log = logging.getLogger(__name__)

MAX_BODY_BYTES = 64 * 1024

app = FastAPI(title="AI Support Engine", version="1.0.0")

# El modo "ml" existe en el contrato pero no tiene motor en esta API.
_ENGINES = {
    Mode.traditional: traditional.analyze,
    Mode.generative: generative.analyze,
}


def _error(status: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": message})


async def _read_body(request: Request) -> bytes | None:
    """Lee el cuerpo sin pasar de MAX_BODY_BYTES; None si se pasa."""
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        return None
    body = b""
    async for chunk in request.stream():
        body += chunk
        if len(body) > MAX_BODY_BYTES:
            return None
    return body


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze(request: Request):
    content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if content_type != "application/json":
        return _error(415, "El Content-Type debe ser application/json.")

    body = await _read_body(request)
    if body is None:
        return _error(413, f"El cuerpo no puede superar {MAX_BODY_BYTES // 1024} KB.")

    try:
        payload = AnalyzeRequest.model_validate(json.loads(body))
    except ValidationError as exc:
        campos = sorted({".".join(str(p) for p in e["loc"]) or "cuerpo" for e in exc.errors()})
        return _error(400, "Petición inválida en: " + ", ".join(campos)
                      + ". Se requiere message (1 a 2000 caracteres) y mode.")
    except ValueError:
        return _error(400, "El cuerpo no es un JSON válido.")

    engine = _ENGINES.get(payload.mode)
    if engine is None:
        return _error(400, "mode debe ser 'traditional' o 'generative'.")

    try:
        result = await asyncio.to_thread(engine, payload.message)
        return AnalyzeResponse(**result)
    except Exception as exc:  # nunca se filtra el detalle interno al cliente
        log.error("Falla interna en el motor %s (%s)", payload.mode.value, type(exc).__name__)
        return _error(500, "Error interno al analizar la solicitud.")
