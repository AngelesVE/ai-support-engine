"""Contrato común de entrada y salida.

Todos los motores (tradicional, ML y generativo) devuelven exactamente esta
misma estructura, y la API valida las peticiones con estos modelos.
"""

from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints


class Category(str, Enum):
    ACCESS = "ACCESS"      # problemas de inicio de sesión o acceso
    BUG = "BUG"            # errores o fallas del sistema
    FEATURE = "FEATURE"    # solicitudes de nuevas funcionalidades
    SECURITY = "SECURITY"  # vulnerabilidades o incidentes de seguridad


class Priority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Mode(str, Enum):
    traditional = "traditional"
    generative = "generative"
    ml = "ml"


# Se recortan los espacios de los extremos y luego se exige de 1 a 2000
# caracteres, así que un mensaje de solo espacios se rechaza por vacío.
Message = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
]


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")  # campos desconocidos = error

    message: Message
    mode: Mode


class AnalyzeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: Category
    priority: Priority
    response: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
    ]
    requiresHumanReview: bool
    mode: Mode


def enforce_security_review(result: AnalyzeResponse) -> AnalyzeResponse:
    """Regla de negocio: todo incidente SECURITY pasa por revisión humana,
    sin importar qué motor lo clasificó."""
    if result.category is Category.SECURITY and not result.requiresHumanReview:
        return result.model_copy(update={"requiresHumanReview": True})
    return result
