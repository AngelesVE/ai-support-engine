# Endpoint real POST /api/analyze (servidor uvicorn + Ollama)

Servidor: `uvicorn app.main:app --port 8000`. Mensaje en ambos modos: `Encontré una vulnerabilidad de inyección SQL en el buscador`

## mode = traditional (HTTP 200)
```json
{
  "category": "SECURITY",
  "priority": "HIGH",
  "response": "Gracias por avisarnos. Su reporte se trata como un posible incidente de seguridad y fue escalado al equipo de seguridad para su revisión prioritaria. Mientras tanto, no comparta contraseñas ni datos sensibles por este medio y evite difundir los detalles.",
  "requiresHumanReview": true,
  "mode": "traditional"
}
```

## mode = generative (HTTP 200)
```json
{
  "category": "BUG",
  "priority": "HIGH",
  "response": "Gracias por informar la vulnerabilidad. Estaremos investigando de inmediato.",
  "requiresHumanReview": false,
  "mode": "generative"
}
```

## Errores

- Content-Type text/plain: HTTP 415 {"error":"El Content-Type debe ser application/json."}
- message vacío: HTTP 400 {"error":"Petición inválida en: message. Se requiere message (1 a 2000 caracteres) y mode."}
- mode desconocido: HTTP 400 {"error":"Petición inválida en: mode. Se requiere message (1 a 2000 caracteres) y mode."}
- JSON roto: HTTP 400 {"error":"El cuerpo no es un JSON válido."}
- cuerpo de 70 KB: HTTP 413 {"error":"El cuerpo no puede superar 64 KB."}
- GET /health: {"status":"ok"}
