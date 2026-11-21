"""Configuración del análisis, leída de variables de entorno (o del archivo .env en la raíz).

La única variable que hay que cambiar para pasar de local a online es LLM_PROVIDER:
    LLM_PROVIDER=local    -> Ollama (qwen3.5:9b por defecto)
    LLM_PROVIDER=online   -> API de Claude (claude-haiku-5-5), requiere ANTHROPIC_API_KEY
Ver .env.example para la lista completa.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

try:  # python-dotenv es opcional: sin él solo se leen las variables del sistema
    from dotenv import load_dotenv

    load_dotenv(RAIZ / ".env", override=False)
except ImportError:  # pragma: no cover
    pass

PROVEEDORES = {"local": "local", "ollama": "local", "online": "online", "claude": "online", "anthropic": "online"}


class ConfiguracionError(RuntimeError):
    """Configuración inválida o incompleta. El mensaje explica cómo corregirla."""


def _txt(nombre: str, defecto: str) -> str:
    v = os.environ.get(nombre)
    return v.strip() if v and v.strip() else defecto


def _int(nombre: str, defecto: int) -> int:
    try:
        return int(_txt(nombre, str(defecto)))
    except ValueError as e:
        raise ConfiguracionError(f"{nombre} debe ser un entero") from e


def _float(nombre: str, defecto: float) -> float:
    try:
        return float(_txt(nombre, str(defecto)))
    except ValueError as e:
        raise ConfiguracionError(f"{nombre} debe ser un número") from e


def _fecha(nombre: str) -> date:
    v = os.environ.get(nombre, "").strip()
    if not v:
        return date.today()
    try:
        return date.fromisoformat(v)
    except ValueError as e:
        raise ConfiguracionError(f"{nombre} debe tener formato AAAA-MM-DD (recibido {v!r})") from e


def normalizar_proveedor(valor: str) -> str:
    p = PROVEEDORES.get((valor or "").strip().lower())
    if not p:
        raise ConfiguracionError(f"LLM_PROVIDER={valor!r} no es válido. Usa 'local' (Ollama) u 'online' (Claude).")
    return p


@dataclass(frozen=True)
class Ajustes:
    # --- LLM ---------------------------------------------------------------------------
    proveedor: str = "local"                     # "local" | "online"
    ollama_url: str = "http://localhost:11434"
    ollama_modelo: str = "qwen3.5:9b"
    ollama_num_ctx: int = 8192                   # contexto fijo: cambiarlo recarga el modelo
    ollama_num_gpu: int = 99                     # 99 = todas las capas en GPU (≈30 % más rápido)
    ollama_keep_alive: str = "30m"
    anthropic_api_key: str = ""
    claude_modelo: str = "claude-haiku-5-5"
    llm_timeout_s: float = 120.0
    max_chars_local: int = 12000                 # texto por documento que se envía al LLM local
    max_chars_online: int = 40000                # Claude tiene más contexto y es más rápido
    dictamen_llm: str = "auto"                   # auto | si | no  (auto: lo omite si no hay tiempo)

    # --- OCR -----------------------------------------------------------------------------
    ocr_idioma: str = "spa_fast"                 # spa_fast: 3x más rápido que spa (best), misma calidad
    ocr_dpi: int = 250
    ocr_hilos: int = 0                           # 0 = automático (núcleos lógicos, máx. 16)
    ocr_cache: bool = True                       # reutiliza el OCR de archivos idénticos (SHA-256)

    # --- Reglas de negocio -------------------------------------------------------------
    uso_requerido: str = "comercial: tienda de autoservicio / minisúper (comercio de productos básicos)"
    fecha_referencia: date = date.today()
    predial_tolerancia_anios: int = 0            # 0: el predial debe ser del año de referencia
    superficie_tolerancia: float = 0.05          # diferencia relativa aceptada entre documentos
    uso_suelo_antiguedad_max_anios: int = 1      # si la licencia no indica vigencia
    tiempo_objetivo_s: float = 60.0

    @property
    def es_local(self) -> bool:
        return self.proveedor == "local"

    @property
    def modelo(self) -> str:
        return self.ollama_modelo if self.es_local else self.claude_modelo

    @property
    def max_chars_doc(self) -> int:
        return self.max_chars_local if self.es_local else self.max_chars_online

    @property
    def hilos_ocr(self) -> int:
        return self.ocr_hilos if self.ocr_hilos > 0 else max(2, min(16, os.cpu_count() or 4))

    def con(self, **cambios) -> "Ajustes":
        if "proveedor" in cambios:
            cambios["proveedor"] = normalizar_proveedor(cambios["proveedor"])
        return replace(self, **cambios)

    @classmethod
    def desde_entorno(cls, **cambios) -> "Ajustes":
        aj = cls(
            proveedor=normalizar_proveedor(_txt("LLM_PROVIDER", "local")),
            ollama_url=_txt("OLLAMA_BASE_URL", cls.ollama_url),
            ollama_modelo=_txt("OLLAMA_MODEL", cls.ollama_modelo),
            ollama_num_ctx=_int("OLLAMA_NUM_CTX", cls.ollama_num_ctx),
            ollama_num_gpu=_int("OLLAMA_NUM_GPU", cls.ollama_num_gpu),
            ollama_keep_alive=_txt("OLLAMA_KEEP_ALIVE", cls.ollama_keep_alive),
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", "").strip(),
            claude_modelo=_txt("CLAUDE_MODEL", cls.claude_modelo),
            llm_timeout_s=_float("LLM_TIMEOUT_S", cls.llm_timeout_s),
            max_chars_local=_int("LLM_MAX_CHARS_LOCAL", cls.max_chars_local),
            max_chars_online=_int("LLM_MAX_CHARS_ONLINE", cls.max_chars_online),
            dictamen_llm=_txt("DICTAMEN_LLM", cls.dictamen_llm).lower(),
            ocr_idioma=_txt("OCR_LANG", cls.ocr_idioma),
            ocr_dpi=_int("OCR_DPI", cls.ocr_dpi),
            ocr_hilos=_int("OCR_WORKERS", cls.ocr_hilos),
            ocr_cache=_txt("OCR_CACHE", "1").lower() not in ("0", "false", "no"),
            uso_requerido=_txt("USO_REQUERIDO", cls.uso_requerido),
            fecha_referencia=_fecha("FECHA_REFERENCIA"),
            predial_tolerancia_anios=_int("PREDIAL_TOLERANCIA_ANIOS", cls.predial_tolerancia_anios),
            superficie_tolerancia=_float("SUPERFICIE_TOLERANCIA", cls.superficie_tolerancia),
            uso_suelo_antiguedad_max_anios=_int("USO_SUELO_ANTIGUEDAD_MAX_ANIOS", cls.uso_suelo_antiguedad_max_anios),
            tiempo_objetivo_s=_float("TIEMPO_OBJETIVO_S", cls.tiempo_objetivo_s),
        )
        if aj.dictamen_llm not in ("auto", "si", "no"):
            raise ConfiguracionError("DICTAMEN_LLM debe ser auto, si o no")
        return aj.con(**cambios) if cambios else aj

    def validar(self) -> None:
        """Errores de configuración que impedirían llamar al LLM."""
        if not self.es_local and not self.anthropic_api_key:
            raise ConfiguracionError(
                "LLM_PROVIDER=online requiere ANTHROPIC_API_KEY. Agrégala al archivo .env "
                "(ver .env.example) o cambia a LLM_PROVIDER=local.")
