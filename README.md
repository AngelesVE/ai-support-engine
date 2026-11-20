# AI Support Engine

Motor de soporte que clasifica solicitudes de clientes en una categoría (ACCESS, BUG, FEATURE, SECURITY) y una prioridad (LOW, MEDIUM, HIGH, CRITICAL), y redacta una respuesta. Reto práctico de la materia Bases de datos en la nube (semana 12). Tiene dos motores con el mismo contrato:

- **Tradicional** (`app/engines/traditional.py`): reglas con palabras clave ponderadas, sin ningún modelo.
- **Generativo** (`app/engines/generative.py`): modelo local `qwen2.5:3b` con Ollama.

## Stack

Python 3.14, FastAPI + Uvicorn, Pydantic, Ollama (`qwen2.5:3b`), python-dotenv, pytest.

## Instalación

1. Instalar [Ollama](https://ollama.com) y descargar el modelo: `ollama pull qwen2.5:3b`
2. Crear el entorno e instalar dependencias (Windows):

```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

3. Copiar la configuración: `copy .env.example .env` (variables `OLLAMA_HOST`, `OLLAMA_MODEL`, `OLLAMA_TIMEOUT`). No hay claves ni secretos; `.env` no se sube a Git.

## Uso

Levantar la API (Ollama debe estar encendido para el modo generativo):

```
.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```

Ejemplo con curl:

```
curl -X POST http://127.0.0.1:8000/api/analyze -H "Content-Type: application/json" \
  -d "{\"message\":\"No puedo iniciar sesion\",\"mode\":\"traditional\"}"
```

Documentación interactiva en `http://127.0.0.1:8000/docs` y estado en `GET /health`.

## Endpoint `POST /api/analyze`

Petición (`Content-Type: application/json`, máximo 64 KB):

```json
{ "message": "texto de 1 a 2000 caracteres", "mode": "traditional" }
```

`mode` puede ser `traditional` o `generative`. Respuesta (idéntica en ambos modos):

```json
{
  "category": "SECURITY",
  "priority": "HIGH",
  "response": "texto para el cliente",
  "requiresHumanReview": true,
  "mode": "traditional"
}
```

| Código | Cuándo |
|---|---|
| 200 | análisis correcto |
| 400 | JSON roto, `message` vacío o de más de 2000 caracteres, campos faltantes o extra, `mode` desconocido |
| 413 | cuerpo de más de 64 KB |
| 415 | `Content-Type` distinto de `application/json` |
| 500 | falla interna (sin detalles hacia el cliente) |

Los errores son `{"error": "..."}` y nunca repiten el mensaje del usuario.

## Seguridad y validaciones

- Toda solicitud SECURITY lleva `requiresHumanReview: true` y prioridad mínima HIGH, en ambos motores.
- Ataques tipo "ignora todas las instrucciones anteriores": el motor tradicional borra esas frases antes de clasificar; el generativo recibe el mensaje entre `<mensaje_cliente>` como dato, no como instrucción, y su prioridad nunca baja de la que calculan las reglas. En ambos casos se marca revisión humana.
- La respuesta de Ollama se pide con el esquema JSON del contrato y se valida con Pydantic; si el formato es inválido se reintenta (2 intentos máximo). Si Ollama no responde se usa el motor por reglas como respaldo y se marca revisión humana (la API sigue contestando 200).
- No se guardan ni se registran mensajes de usuarios ni secretos en los logs.

## Pruebas

```
.venv\Scripts\python.exe -m pytest
```

65 pruebas (motor tradicional, generativo y API). No necesitan Ollama: el modelo se simula en las pruebas.

Pruebas reales con Ollama encendido:

- `scripts\probar_ollama.py`: 5 casos con el motor generativo → `evidence/paso3_ollama_real.*`
- `scripts\comparar_motores.py`: la comparativa de abajo, por el endpoint → `evidence/paso4_comparativa.json` y `.md`
- `scripts\probar_endpoint.py`: peticiones HTTP contra uvicorn encendido → `evidence/paso4_endpoint_real.md`

## Resultados de la comparativa

14 casos (8 normales, 3 ambiguos y 3 ataques: dos prompt injection y una inyección SQL), con la clasificación esperada escrita en `data/casos_referencia.json` y confirmada en Git antes de correr los motores. Se corrieron de verdad con Ollama `qwen2.5:3b`. Acierto = categoría y prioridad iguales a la referencia.

| Métrica | Tradicional | Generativo |
|---|---|---|
| **Aciertos (categoría y prioridad)** | 10/14 = **71.4 %** | 9/14 = **64.3 %** |
| Solo categoría | 78.6 % | 71.4 % |
| Solo prioridad | 85.7 % | 78.6 % |
| Formato válido | 14/14 | 14/14 |
| SECURITY con revisión humana | 5/5 | 3/5 |
| Ataques resistidos | 2/3 | 2/3 |
| Segundos promedio por solicitud | 0.0 | 10.3 |

Detalle caso por caso y respuestas del modelo en `evidence/paso4_comparativa.md`.

## Conclusión

En las 14 pruebas el motor por reglas acertó 10 (71.4 %) y el generativo con Ollama 9 (64.3 %), o sea que no ganó el que usa el modelo. Las reglas son instantáneas, siempre dan lo mismo y no se dejaron engañar por las dos inyecciones de prompt, pero fallan cuando una palabra confunde, como "exportar" en un error de texto cortado. El modelo qwen2.5:3b entendió mejor un mensaje ambiguo (caso 9), aunque tardó unos 10 segundos por solicitud y llegó a clasificar como BUG una vulnerabilidad de inyección SQL, algo grave. Ninguno detectó bien el ataque con SQL escrito en el mensaje (caso 14). Son pocos casos, así que los porcentajes solo son una referencia. En producción usaría las reglas primero y el modelo como apoyo, siempre con revisión humana en SECURITY.

## Estructura

```
app/            contrato, motores (traditional, generative) y API (main.py)
data/           casos_referencia.json
docs/           conclusion.md
evidence/       resultados reales (pasos 3 y 4)
scripts/        pruebas reales y comparativa
tests/          pruebas con pytest
```
