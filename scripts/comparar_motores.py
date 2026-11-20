"""Comparativa de los dos motores a través del endpoint POST /api/analyze.

Lee data/casos_referencia.json (definido antes de correr) y manda cada caso
con mode=traditional y mode=generative. El generativo usa Ollama de verdad:
si Ollama no está encendido el script se detiene (no se mide el respaldo).

Uso: .venv/Scripts/python.exe scripts/comparar_motores.py
Escribe evidence/paso4_comparativa.json y evidence/paso4_comparativa.md
"""

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import config  # noqa: E402
from app.contract import AnalyzeResponse  # noqa: E402
from app.main import app  # noqa: E402

MOTORES = ("traditional", "generative")


def ollama_activo() -> bool:
    try:
        r = httpx.get(config.ollama_host() + "/api/tags", timeout=5)
        nombres = [m["name"] for m in r.json().get("models", [])]
        return config.ollama_model() in nombres
    except Exception:
        return False


def evaluar(caso: dict, respuesta: httpx.Response, segundos: float, modo: str) -> dict:
    fila = {"http": respuesta.status_code, "segundos": segundos}
    try:
        datos = AnalyzeResponse(**respuesta.json())
    except Exception:
        fila.update(formato_valido=False, categoria=None, prioridad=None,
                    revision_humana=None, respuesta=None,
                    cat_ok=False, prio_ok=False, acierto=False)
        return fila
    fila.update(
        formato_valido=datos.mode.value == modo,
        categoria=datos.category.value,
        prioridad=datos.priority.value,
        revision_humana=datos.requiresHumanReview,
        respuesta=datos.response,
    )
    fila["cat_ok"] = fila["categoria"] == caso["categoria"]
    fila["prio_ok"] = fila["prioridad"] == caso["prioridad"]
    # Acierto = categoría y prioridad iguales a la referencia.
    fila["acierto"] = fila["cat_ok"] and fila["prio_ok"]
    return fila


def pct(parte: int, total: int) -> float:
    return round(100 * parte / total, 1)


def main() -> None:
    if not ollama_activo():
        sys.exit(f"Ollama no responde o falta el modelo {config.ollama_model()}: "
                 "enciéndelo antes de correr la comparativa.")

    casos = json.loads((ROOT / "data" / "casos_referencia.json").read_text(encoding="utf-8"))["casos"]
    cliente = TestClient(app)
    filas = []
    for caso in casos:
        fila = {"caso": caso}
        for modo in MOTORES:
            t0 = time.time()
            r = cliente.post("/api/analyze", json={"message": caso["mensaje"], "mode": modo})
            fila[modo] = evaluar(caso, r, round(time.time() - t0, 1), modo)
        filas.append(fila)
        print(f"{caso['id']:2} {caso['tipo']:8} ref={caso['categoria']}/{caso['prioridad']:8} "
              f"trad={fila['traditional']['categoria']}/{fila['traditional']['prioridad']:8} "
              f"gen={fila['generative']['categoria']}/{fila['generative']['prioridad']:8}"
              f" ({fila['generative']['segundos']} s)")

    n = len(filas)
    resumen = {}
    for modo in MOTORES:
        f = [x[modo] for x in filas]
        resumen[modo] = {
            "casos": n,
            "aciertos_categoria": sum(x["cat_ok"] for x in f),
            "aciertos_prioridad": sum(x["prio_ok"] for x in f),
            "aciertos_totales": sum(x["acierto"] for x in f),
            "pct_categoria": pct(sum(x["cat_ok"] for x in f), n),
            "pct_prioridad": pct(sum(x["prio_ok"] for x in f), n),
            "pct_aciertos": pct(sum(x["acierto"] for x in f), n),
            "formato_valido": sum(x["formato_valido"] for x in f),
            "seguridad_con_revision": sum(
                1 for x in filas if x["caso"]["categoria"] == "SECURITY" and x[modo]["revision_humana"]),
            "casos_security": sum(1 for x in filas if x["caso"]["categoria"] == "SECURITY"),
            "ataques_resistidos": sum(
                1 for x in filas if x["caso"]["tipo"] == "ataque" and x[modo]["acierto"]),
            "ataques": sum(1 for x in filas if x["caso"]["tipo"] == "ataque"),
            "segundos_promedio": round(sum(x["segundos"] for x in f) / n, 1),
        }

    out = ROOT / "evidence"
    out.mkdir(exist_ok=True)
    meta = {"modelo": config.ollama_model(), "host": config.ollama_host(),
            "endpoint": "POST /api/analyze", "casos": n}
    (out / "paso4_comparativa.json").write_text(
        json.dumps({"meta": meta, "resumen": resumen, "casos": filas}, ensure_ascii=False, indent=2),
        encoding="utf-8")

    def marca(ok: bool) -> str:
        return "✅" if ok else "❌"

    md = [f"# Comparativa de motores (endpoint /api/analyze, Ollama {meta['modelo']})", "",
          "Referencia = clasificación definida en `data/casos_referencia.json` antes de correr los motores. "
          "Acierto = categoría y prioridad iguales a la referencia.", "",
          "| # | Tipo | Mensaje | Referencia | Tradicional | Generativo |",
          "|---|---|---|---|---|---|"]
    for x in filas:
        c = x["caso"]
        t, g = x["traditional"], x["generative"]
        md.append(f"| {c['id']} | {c['tipo']} | {c['mensaje'].replace('|', '/')[:90]} | "
                  f"{c['categoria']} / {c['prioridad']} | "
                  f"{t['categoria']} / {t['prioridad']} {marca(t['acierto'])} | "
                  f"{g['categoria']} / {g['prioridad']} {marca(g['acierto'])} |")
    md += ["", "## Resultados por motor", "",
           "| Métrica | Tradicional | Generativo |", "|---|---|---|"]
    t, g = resumen["traditional"], resumen["generative"]
    md += [
        f"| Aciertos (categoría y prioridad) | {t['aciertos_totales']}/{n} = **{t['pct_aciertos']}%** | {g['aciertos_totales']}/{n} = **{g['pct_aciertos']}%** |",
        f"| Solo categoría | {t['pct_categoria']}% | {g['pct_categoria']}% |",
        f"| Solo prioridad | {t['pct_prioridad']}% | {g['pct_prioridad']}% |",
        f"| Formato válido (contrato) | {t['formato_valido']}/{n} | {g['formato_valido']}/{n} |",
        f"| SECURITY con revisión humana | {t['seguridad_con_revision']}/{t['casos_security']} | {g['seguridad_con_revision']}/{g['casos_security']} |",
        f"| Ataques resistidos | {t['ataques_resistidos']}/{t['ataques']} | {g['ataques_resistidos']}/{g['ataques']} |",
        f"| Segundos promedio por solicitud | {t['segundos_promedio']} | {g['segundos_promedio']} |",
        "", "## Respuestas del motor generativo", ""]
    for x in filas:
        md.append(f"- **Caso {x['caso']['id']}** ({x['generative']['categoria']}): {x['generative']['respuesta']}")
    (out / "paso4_comparativa.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    print(json.dumps(resumen, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
