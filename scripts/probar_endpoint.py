"""Prueba del endpoint real contra un servidor uvicorn ya encendido y guarda la evidencia.

1) .venv/Scripts/python.exe -m uvicorn app.main:app --port 8000
2) .venv/Scripts/python.exe scripts/probar_endpoint.py [url_base]
Escribe evidence/paso4_endpoint_real.md
"""

import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
MENSAJE = "Encontré una vulnerabilidad de inyección SQL en el buscador"


def main() -> None:
    md = ["# Endpoint real POST /api/analyze (servidor uvicorn + Ollama)", "",
          f"Servidor: `uvicorn app.main:app --port 8000`. Mensaje en ambos modos: `{MENSAJE}`", ""]
    for modo in ("traditional", "generative"):
        r = httpx.post(f"{BASE}/api/analyze", json={"message": MENSAJE, "mode": modo}, timeout=120)
        md += [f"## mode = {modo} (HTTP {r.status_code})", "```json",
               json.dumps(r.json(), ensure_ascii=False, indent=2), "```", ""]
    md += ["## Errores", ""]
    pruebas = [
        ("Content-Type text/plain", dict(content="x", headers={"content-type": "text/plain"})),
        ("message vacío", dict(json={"message": "", "mode": "traditional"})),
        ("mode desconocido", dict(json={"message": "hola", "mode": "otro"})),
        ("JSON roto", dict(content="{no", headers={"content-type": "application/json"})),
        ("cuerpo de 70 KB", dict(json={"message": "a" * 70000, "mode": "traditional"})),
    ]
    for nombre, kwargs in pruebas:
        r = httpx.post(f"{BASE}/api/analyze", timeout=30, **kwargs)
        md.append(f"- {nombre}: HTTP {r.status_code} {r.text[:120]}")
    md.append(f"- GET /health: {httpx.get(BASE + '/health').text}")
    (ROOT / "evidence" / "paso4_endpoint_real.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
