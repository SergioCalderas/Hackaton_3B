"""Fábrica de modelos de LangChain: Ollama (local) o Claude (online), según Ajustes.proveedor.

Todos los agentes usan EXACTAMENTE las mismas opciones de carga de Ollama (num_ctx, num_gpu):
si cambiaran entre llamadas, Ollama recargaría el modelo (~15 s) a mitad del análisis.
"""
from __future__ import annotations

import json
import logging
import threading
import time
import urllib.error
import urllib.request
from functools import lru_cache

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableLambda
from pydantic import BaseModel

from .config import Ajustes, ConfiguracionError

log = logging.getLogger("analisis")


TOKENS_POR_ROL = {"extraccion": 700, "dictamen": 320, "clasificacion": 40, "general": 900}


@lru_cache(maxsize=16)
def crear_llm(aj: Ajustes, max_tokens: int = 900) -> BaseChatModel:
    """num_predict/max_tokens varía por rol; en Ollama NO es opción de carga (no recarga el modelo)."""
    aj.validar()
    if aj.es_local:
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=aj.ollama_modelo,
            base_url=aj.ollama_url,
            reasoning=False,            # qwen3.5 "piensa" por defecto: apagarlo es clave para el tiempo
            temperature=0,
            num_ctx=aj.ollama_num_ctx,
            num_gpu=aj.ollama_num_gpu,
            num_predict=max_tokens,
            keep_alive=aj.ollama_keep_alive,
            client_kwargs={"timeout": aj.llm_timeout_s},
        )
    from langchain_anthropic import ChatAnthropic

    return ChatAnthropic(
        model=aj.claude_modelo,
        api_key=aj.anthropic_api_key,
        max_tokens=max_tokens * 2,     # Claude no tiene el costo de tiempo del modelo local
        timeout=aj.llm_timeout_s,
        max_retries=2,
    )


def esquema_json_obligatorio(esquema: type[BaseModel]) -> dict:
    """JSON Schema con TODAS las propiedades obligatorias (aceptan null).

    Con propiedades opcionales, la decodificación restringida de Ollama deja que el modelo las
    omita, y qwen3.5 omitía justo los datos importantes (uso autorizado, giro, superficie).
    """
    s = esquema.model_json_schema()
    s["required"] = list(s.get("properties", {}))
    for p in s.get("properties", {}).values():
        p.pop("default", None)
    return s


@lru_cache(maxsize=32)
def llm_estructurado(aj: Ajustes, esquema: type[BaseModel], rol: str = "general"):
    """Runnable que devuelve una instancia de `esquema`.

    Ollama: JSON Schema en `format` (decodificación restringida, siempre JSON válido) con todas las
            propiedades obligatorias; luego se valida con el modelo Pydantic.
    Claude: tool calling (método recomendado por langchain-anthropic).
    """
    llm = crear_llm(aj, TOKENS_POR_ROL.get(rol, 900))
    if aj.es_local:
        cadena = (llm.with_structured_output(esquema_json_obligatorio(esquema), method="json_schema")
                  | RunnableLambda(esquema.model_validate))
        return cadena.with_retry(stop_after_attempt=2)
    return llm.with_structured_output(esquema).with_retry(stop_after_attempt=2)


# ---------------------------------------------------------------------------------------
# Estado y precarga de Ollama
# ---------------------------------------------------------------------------------------
def _get_json(url: str, timeout: float = 3.0) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.load(r)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None


def estado_ollama(aj: Ajustes) -> dict:
    """{'servidor': bool, 'modelo_instalado': bool, 'modelo_cargado': bool, 'vram_gb': float|None}."""
    tags = _get_json(f"{aj.ollama_url}/api/tags")
    if tags is None:
        return {"servidor": False, "modelo_instalado": False, "modelo_cargado": False, "vram_gb": None}
    nombres = {m.get("name") for m in tags.get("models", [])} | {m.get("model") for m in tags.get("models", [])}
    ps = _get_json(f"{aj.ollama_url}/api/ps") or {}
    cargado = next((m for m in ps.get("models", []) if m.get("name") == aj.ollama_modelo), None)
    return {
        "servidor": True,
        "modelo_instalado": aj.ollama_modelo in nombres,
        "modelo_cargado": cargado is not None,
        "vram_gb": round(cargado["size_vram"] / 1e9, 2) if cargado and cargado.get("size_vram") else None,
        "contexto": cargado.get("context_length") if cargado else None,
    }


_precarga_lock = threading.Lock()


def precalentar(aj: Ajustes) -> float:
    """Carga el modelo en la GPU con las opciones definitivas. Devuelve los segundos que tardó.

    En modo online solo valida la configuración (no hay nada que cargar).
    """
    aj.validar()
    if not aj.es_local:
        return 0.0
    with _precarga_lock:
        est = estado_ollama(aj)
        if not est["servidor"]:
            raise ConfiguracionError(
                f"No hay servidor de Ollama en {aj.ollama_url}. Abre la app de Ollama o ejecuta 'ollama serve'.")
        if not est["modelo_instalado"]:
            raise ConfiguracionError(f"El modelo {aj.ollama_modelo} no está instalado: ollama pull {aj.ollama_modelo}")
        t = time.perf_counter()
        crear_llm(aj).invoke([HumanMessage("Responde solo: ok")])
        return round(time.perf_counter() - t, 2)
