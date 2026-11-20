"""Configuración leída del entorno (.env)."""

import os

from dotenv import load_dotenv

load_dotenv()


def ollama_host() -> str:
    return os.getenv("OLLAMA_HOST", "http://localhost:11434")


def ollama_model() -> str:
    return os.getenv("OLLAMA_MODEL", "qwen2.5:3b")


def ollama_timeout() -> float:
    try:
        return float(os.getenv("OLLAMA_TIMEOUT", "60"))
    except ValueError:
        return 60.0
