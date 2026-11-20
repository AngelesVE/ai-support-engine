"""Motor tradicional: motor basado en reglas (sin ningún modelo).

Cómo decide:
1. Normaliza el texto (minúsculas, sin acentos).
2. Quita las frases que intentan dictar la clasificación ("ignora las
   instrucciones", "clasifica como...", "prioridad baja"): no se obedecen y
   el caso se marca para revisión humana.
3. Categoría: suma los pesos de las palabras/frases clave de cada categoría.
   Gana la de mayor puntaje; si empatan, la más grave
   (SECURITY > ACCESS > BUG > FEATURE).
   Si nada coincide, categoría por defecto: BUG con prioridad LOW (con
   revisión humana, porque el sistema no entendió el mensaje).
4. Prioridad: base por categoría + modificadores (sube con urgencia,
   producción, muchos usuarios, pérdida de datos; baja con "cuando puedan",
   sugerencias, detalles menores).
"""

import re
import unicodedata

from app.contract import (
    AnalyzeResponse,
    Category,
    Mode,
    Priority,
    enforce_security_review,
)

# ---------------------------------------------------------------------------
# Palabras clave con peso (1 = débil, 3 = media, 5-6 = muy específica).
# Van sin acentos y en minúsculas. Un "*" al final significa "cualquier
# terminación" (contrasena* acepta contraseña, contraseñas...). Sin "*" la
# palabra o frase debe aparecer completa. Cada término cuenta una sola vez.
# ---------------------------------------------------------------------------
KEYWORDS: dict[Category, list[tuple[str, int]]] = {
    Category.SECURITY: [
        ("vulnerab*", 5), ("hack*", 5), ("ransomware", 6), ("malware", 5),
        ("phishing", 5), ("filtracion*", 5), ("filtraron", 5), ("se filtr*", 5),
        ("fuga de datos", 5), ("data leak*", 5), ("leaked", 5),
        ("breach*", 5), ("brecha*", 4), ("datos expuestos", 6),
        ("expuest*", 3), ("exposed", 3), ("inyeccion sql", 6),
        ("sql injection", 6), ("inyeccion", 4), ("injection", 4),
        ("xss", 5), ("csrf", 5), ("exploit*", 5), ("ataque*", 4),
        ("attack*", 4), ("intrus*", 4), ("robo de datos", 6),
        ("data theft", 6), ("robaron", 4), ("stolen", 4),
        ("acceso no autorizado", 6), ("no autorizado", 5),
        ("sin autorizacion", 5), ("unauthorized", 5), ("seguridad", 3),
        ("security", 3), ("sospechos*", 3), ("suspicious", 3),
        ("comprometid*", 5), ("compromised", 5), ("fuerza bruta", 4),
        ("brute force", 4), ("ddos", 4), ("suplantacion", 4),
        ("spoofing", 4), ("escalada de privilegios", 5),
        ("privilege escalation", 5), ("denegacion de servicio", 4),
    ],
    Category.ACCESS: [
        ("no puedo iniciar sesion", 5), ("iniciar sesion", 3),
        ("inicio de sesion", 3), ("inicie sesion", 3), ("login", 3),
        ("log in", 3), ("logging in", 3), ("sign in", 3), ("signin", 3),
        ("no puedo entrar", 4), ("no puedo acceder", 5),
        ("cannot access", 4), ("can t access", 4), ("can t log in", 5),
        ("acceso*", 2), ("acceder", 3), ("access", 2),
        ("contrasena*", 3), ("password*", 3), ("olvide mi", 2),
        ("restablecer", 2), ("reset", 2), ("recuperar cuenta", 3),
        ("recuperacion de cuenta", 3), ("cuenta bloqueada", 5),
        ("bloquead*", 2), ("locked out", 5), ("account locked", 5),
        ("locked", 2), ("autenticacion", 2), ("authentication", 2),
        ("2fa", 3), ("dos pasos", 2), ("two factor", 3), ("otp", 2),
        ("codigo de verificacion", 3), ("verification code", 3),
        ("permiso*", 2), ("permission*", 2), ("credencial*", 2),
        ("credential*", 2), ("sesion*", 2), ("session*", 2), ("sso", 2),
        ("cuenta", 1), ("account", 1),
    ],
    Category.BUG: [
        ("no funciona", 4), ("not working", 4), ("doesn t work", 4),
        ("isn t working", 4), ("no sirve", 3), ("no carga", 3),
        ("not loading", 3), ("won t load", 3), ("no abre", 2),
        ("doesn t open", 2), ("no responde", 3), ("not responding", 3),
        ("no guarda*", 3), ("no se guard*", 3), ("doesn t save", 3),
        ("error*", 3), ("bug*", 4), ("falla*", 3), ("fallo*", 3),
        ("fail*", 3), ("crash*", 4), ("se cae*", 3), ("se cayo", 3),
        ("caid*", 3), ("outage", 3), ("fuera de servicio", 3),
        ("se cuelga*", 3), ("se congela*", 3), ("freez*", 3),
        ("pantalla en blanco", 4), ("blank screen", 4), ("lent*", 2),
        ("slow*", 2), ("timeout*", 3), ("time out", 3), ("exception*", 3),
        ("excepcion*", 3), ("stack trace", 3), ("roto*", 3), ("broken", 3),
        ("incorrect*", 2), ("duplicad*", 2), ("perdida de datos", 3),
        ("data loss", 3), ("no aparece", 2), ("desaparec*", 2),
        ("se cierra", 2), ("closes unexpectedly", 3),
    ],
    Category.FEATURE: [
        ("nueva funcionalidad", 5), ("funcionalidad*", 3),
        ("nueva funcion*", 4), ("feature request", 5), ("new feature*", 5),
        ("feature*", 4), ("sugerencia*", 4), ("sugier*", 4),
        ("sugerir*", 3), ("suggest*", 4), ("me gustaria", 4),
        ("nos gustaria", 4), ("quisiera", 2), ("would like", 4),
        ("would love", 4), ("i wish", 3), ("ojala", 3), ("seria util", 3),
        ("seria genial", 3), ("would be nice", 3), ("would be great", 3),
        ("would be useful", 3), ("mejora*", 2), ("improvement*", 2),
        ("enhancement*", 4), ("modo oscuro", 4), ("dark mode", 4),
        ("integracion con", 3), ("integration with", 3), ("exportar", 2),
        ("export", 2), ("opcion para", 2), ("option to", 2),
        ("nueva opcion", 3), ("ability to", 3), ("support for", 2),
        ("soporte para", 2), ("agreg*", 2), ("anad*", 2), ("add", 1),
        ("implement*", 2), ("podrian", 1),
    ],
}

# Orden de severidad: se usa para desempatar (el primero es el más grave).
SEVERITY_ORDER = [Category.SECURITY, Category.ACCESS, Category.BUG, Category.FEATURE]


def _compile(term: str) -> re.Pattern:
    stem = re.escape(term.rstrip("*")).replace(r"\ ", r"\s+")
    return re.compile(rf"\b{stem}" + ("" if term.endswith("*") else r"\b"))


_RULES = {
    cat: [(_compile(term), weight) for term, weight in terms]
    for cat, terms in KEYWORDS.items()
}

# ---------------------------------------------------------------------------
# Defensa contra manipulación (prompt injection): frases que intentan decirle
# al sistema cómo clasificar. Se eliminan del texto antes de analizar, así no
# pueden bajar la prioridad ni cambiar la categoría.
# ---------------------------------------------------------------------------
_LEVELS = (
    r"baja|bajo|low|media|medium|alta|alto|high|critic\w*|normal|minor|trivial|"
    r"bug|feature|access|security|acceso|seguridad|error|funcionalidad|"
    r"prioridad|priority|categoria|category|request|solicitud|ticket"
)
_MANIPULATION = [
    # "ignora todas las instrucciones anteriores", "forget the rules"...
    (re.compile(
        r"\b(?:ignora\w*|ignore|olvida\w*|forget|disregard|omite)\b[^.!?;\n]{0,40}?"
        r"\b(?:instruccion\w*|instructions?|reglas|rules|prompt|indicaciones)\b"
        r"(?:\s+(?:anteriores|previas|previous|above))?"
    ), " "),
    # "ahora eres...", "you are now in admin mode"
    (re.compile(
        r"\b(?:ahora eres|you are now|actua como|act as|finge|pretend)\b[^.!?;\n]*"
    ), " "),
    # "clasifica esto como X": se borra el verbo y el "como X", se conserva
    # lo del medio (p. ej. "esta vulnerabilidad") porque sí describe el caso.
    (re.compile(
        r"\b(?:clasific\w*|classif\w*|categoriz\w*|etiquet\w*|label\w*|marca\w*|mark\w*)\b"
        r"([^.!?;\n]{0,60}?)"
        rf"\b(?:como|as)\b[^.!?;\n]{{0,40}}?\b(?:{_LEVELS})\b(?:\s+(?:{_LEVELS}))*"
    ), r" \1 "),
    # "prioridad baja", "low priority", "alta prioridad"
    (re.compile(
        rf"\b(?:prioridad|priority)\s+(?:{_LEVELS})\b|\b(?:{_LEVELS})\s+(?:prioridad|priority)\b"
    ), " "),
]

# ---------------------------------------------------------------------------
# Prioridad: base por categoría y modificadores.
# ---------------------------------------------------------------------------
_LEVEL_ORDER = [Priority.LOW, Priority.MEDIUM, Priority.HIGH, Priority.CRITICAL]
_BASE_PRIORITY = {
    Category.SECURITY: Priority.HIGH,
    Category.ACCESS: Priority.MEDIUM,
    Category.BUG: Priority.MEDIUM,
    Category.FEATURE: Priority.LOW,
}


def _any(*terms: str) -> re.Pattern:
    return re.compile("|".join(_compile(t).pattern for t in terms))


# Cada grupo que coincida suma +1 (máximo +2 en total).
_RAISERS = {
    "urgencia": _any("urgent*", "inmediat*", "immediate*", "asap", "emergencia",
                     "emergency", "lo antes posible", "cuanto antes", "critic*",
                     "bloqueante", "blocker", "no podemos trabajar"),
    "alcance": _any("produccion", "production", "todos los usuarios", "all users",
                    "todos los clientes", "all customers", "toda la empresa",
                    "varios usuarios", "many users", "multiple users",
                    "nadie puede", "no one can", "nobody can", "ningun usuario",
                    "caid*", "outage", "fuera de servicio"),
    "perdida de datos": _any("perdida de datos", "data loss", "perdimos",
                             "perdi mis datos", "perdi todo", "lost data",
                             "se borraron", "datos perdidos", "corrupt*"),
}

# Un solo aviso de estos baja un nivel (no aplica a SECURITY).
_LOWERERS = _any("cuando puedan", "cuando pueda", "cuando tengan tiempo",
                 "cuando tengas tiempo", "sin prisa", "no hay prisa", "no rush",
                 "whenever", "when you can", "when you have time",
                 "nice to have", "opcional", "optional", "cosmetic*",
                 "estetic*", "minor", "menor", "trivial", "poco importante",
                 "no es importante", "no es grave")
# "no es urgente" NO debe contar como urgencia: baja y se borra antes.
_NEGATED_URGENCY = re.compile(
    r"\b(?:no es|no es tan|no|not|isn t|is not)\s+(?:muy\s+|tan\s+|very\s+)?"
    r"(?:urgent\w*|critic\w*)\b"
)

# Incidentes de seguridad ya ocurridos = CRITICAL (una "vulnerabilidad" sola
# se queda en HIGH, que es la base de SECURITY).
_CRITICAL_SECURITY = _any(
    "filtracion*", "filtraron", "se filtr*", "fuga de datos", "data leak*",
    "leaked", "hack*", "ransomware", "datos expuestos", "expuest*", "exposed",
    "breach*", "brecha*", "robo de datos", "data theft", "robaron",
    "comprometid*", "compromised", "no autorizado", "sin autorizacion",
    "unauthorized",
)

# Respuestas predeterminadas (una por categoría).
RESPONSES = {
    Category.ACCESS: (
        "Lamentamos el inconveniente con su acceso. Verifique que sus credenciales "
        "sean correctas y utilice la opción de recuperación de contraseña si es "
        "necesario. Si el problema continúa, nuestro equipo de soporte revisará su "
        "cuenta. Por su seguridad, no comparta su contraseña por este medio."
    ),
    Category.BUG: (
        "Gracias por reportar el problema. Hemos registrado la falla y el equipo "
        "técnico la revisará. Para ayudarnos a reproducirla, indíquenos los pasos "
        "que realizó, el mensaje de error y el dispositivo o navegador que utiliza."
    ),
    Category.FEATURE: (
        "Gracias por su sugerencia. La hemos registrado y la compartiremos con el "
        "equipo de producto para evaluarla dentro de la planeación de nuevas "
        "funcionalidades."
    ),
    Category.SECURITY: (
        "Gracias por avisarnos. Su reporte se trata como un posible incidente de "
        "seguridad y fue escalado al equipo de seguridad para su revisión "
        "prioritaria. Mientras tanto, no comparta contraseñas ni datos sensibles "
        "por este medio y evite difundir los detalles."
    ),
}


def _fold(text: str) -> str:
    """Minúsculas y sin acentos ('Contraseña' -> 'contrasena')."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _strip_manipulation(text: str) -> tuple[str, bool]:
    detected = False
    for pattern, replacement in _MANIPULATION:
        text, count = pattern.subn(replacement, text)
        detected = detected or count > 0
    return text, detected


def _score(text: str) -> dict[Category, int]:
    return {
        cat: sum(weight for pattern, weight in rules if pattern.search(text))
        for cat, rules in _RULES.items()
    }


def _pick_category(scores: dict[Category, int]) -> tuple[Category, bool, bool]:
    """Devuelve (categoría, usó_valor_por_defecto, hubo_empate)."""
    ranked = sorted(SEVERITY_ORDER, key=lambda c: (-scores[c], SEVERITY_ORDER.index(c)))
    best, runner_up = ranked[0], ranked[1]
    if scores[best] == 0:
        return Category.BUG, True, False  # por defecto: BUG / LOW
    return best, False, scores[runner_up] == scores[best]


def _priority(category: Category, text: str, default_used: bool) -> Priority:
    if category is Category.SECURITY:
        # Nunca baja de HIGH; CRITICAL si ya hubo filtración/hackeo/etc.
        raises = sum(bool(p.search(text)) for p in _RAISERS.values())
        if _CRITICAL_SECURITY.search(text) or raises >= 2:
            return Priority.CRITICAL
        return Priority.HIGH

    base = Priority.LOW if default_used else _BASE_PRIORITY[category]
    level = _LEVEL_ORDER.index(base)
    lowered = bool(_NEGATED_URGENCY.search(text) or _LOWERERS.search(text))
    text = _NEGATED_URGENCY.sub(" ", text)
    level += min(2, sum(bool(p.search(text)) for p in _RAISERS.values()))
    if lowered:
        level -= 1
    return _LEVEL_ORDER[max(0, min(level, len(_LEVEL_ORDER) - 1))]


def analyze(message: str) -> dict:
    """Clasifica un mensaje de soporte y devuelve el contrato de respuesta."""
    text, manipulated = _strip_manipulation(_fold(message))
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()  # puntuación -> espacios

    category, default_used, tie = _pick_category(_score(text))
    result = AnalyzeResponse(
        category=category,
        priority=_priority(category, text, default_used),
        response=RESPONSES[category],
        # Revisión humana si hubo intento de manipulación, si no se entendió
        # el mensaje o si dos categorías quedaron empatadas.
        requiresHumanReview=manipulated or default_used or tie,
        mode=Mode.traditional,
    )
    return enforce_security_review(result).model_dump(mode="json")
