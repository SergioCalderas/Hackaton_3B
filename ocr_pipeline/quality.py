"""Métrica de calidad de texto: proporción de palabras que existen en español.

El léxico (~179k palabras) se extrae del propio spa.traineddata con las
herramientas que trae Tesseract (combine_tessdata + dawg2wordlist) y se guarda
en tessdata/spa_words.txt. Si no se puede generar, la calidad queda en None.
"""
from __future__ import annotations

import logging
import re
import shutil
import subprocess
import tempfile
import unicodedata
from functools import lru_cache
from pathlib import Path

from .config import DEFAULT_TESSDATA_DIR, DEFAULT_TESSERACT_CMDS

log = logging.getLogger("ocr_pipeline")

TOKEN_RE = re.compile(r"[^\W\d_]{3,}")  # palabras de 3+ letras (sin dígitos)


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _tesseract_tool(name: str) -> Path | None:
    for cmd in [shutil.which("tesseract"), *DEFAULT_TESSERACT_CMDS]:
        if cmd and (p := Path(cmd).parent / f"{name}.exe").is_file():
            return p
    return None


def build_lexicon(tessdata_dir: Path = DEFAULT_TESSDATA_DIR, lang: str = "spa") -> Path | None:
    """Genera tessdata/<lang>_words.txt a partir de <lang>.traineddata."""
    out = Path(tessdata_dir) / f"{lang}_words.txt"
    if out.exists():
        return out
    traineddata = Path(tessdata_dir) / f"{lang}.traineddata"
    combine, dawg2 = _tesseract_tool("combine_tessdata"), _tesseract_tool("dawg2wordlist")
    if not (traineddata.exists() and combine and dawg2):
        log.warning("No se pudo generar el léxico (falta %s o herramientas de Tesseract).", traineddata)
        return None
    with tempfile.TemporaryDirectory() as tmp:
        tmp_td = Path(tmp) / traineddata.name
        shutil.copy(traineddata, tmp_td)
        prefix = str(Path(tmp) / f"{lang}.")
        subprocess.run([str(combine), "-u", str(tmp_td), prefix], check=True, capture_output=True)
        subprocess.run([str(dawg2), prefix + "lstm-unicharset", prefix + "lstm-word-dawg", str(out)],
                       check=True, capture_output=True)
    log.info("Léxico generado: %s", out)
    return out


@lru_cache(maxsize=4)
def load_lexicon(tessdata_dir: str = str(DEFAULT_TESSDATA_DIR), lang: str = "spa") -> frozenset[str]:
    path = build_lexicon(Path(tessdata_dir), lang)
    if not path:
        return frozenset()
    words = path.read_text(encoding="utf-8", errors="ignore").split()
    return frozenset(strip_accents(w.lower()) for w in words)


SHORT_WORDS = {"de", "la", "el", "y", "a", "en", "no", "se", "al", "lo", "un", "su", "es", "o", "e",
               "u", "le", "mi", "me", "te", "ya", "si", "ni", "tu", "m2"}
_STRIP = "\"'“”‘’«».,;:()[]{}¡!¿?*·•"
_NUMERIC_RE = re.compile(r"[\d$.,/:%+\-]+")
_WORD_RE = re.compile(r"[^\W\d_]+(?:-[^\W\d_]+)*")


def _token_valid(tok: str, lexicon: frozenset[str]) -> bool:
    """Un token es válido si es palabra del léxico, palabra corta común,
    número/fecha/monto o código alfanumérico (RFC, folio, clave)."""
    w = tok.strip(_STRIP)
    if not w:
        return False                      # puntuación suelta: "—", "|", "..."
    has_digit = any(c.isdigit() for c in w)
    if has_digit and _NUMERIC_RE.fullmatch(w):
        return True                       # 1,234.00  25/03/2024  $390.00
    if has_digit and len(w) >= 3 and any(c.isalpha() for c in w):
        return True                       # MAT850101RA5  U-16534  C62
    if w.isalpha() and len(w) <= 2:
        return strip_accents(w.lower()) in SHORT_WORDS
    if _WORD_RE.fullmatch(w):
        return all(strip_accents(p.lower()) in lexicon for p in w.split("-"))
    return False


def text_quality(text: str, lexicon: frozenset[str] | None = None) -> float | None:
    """calidad_texto: fracción (0..1) de TODOS los tokens que son válidos.

    Cuenta también la basura (letras sueltas, rayas, símbolos) como inválida; así
    un escaneo ilegible donde Tesseract "alucina" palabras reales sigue saliendo bajo.
    None si no hay texto o no hay léxico disponible.
    """
    lexicon = load_lexicon() if lexicon is None else lexicon
    tokens = text.split()
    if not lexicon or not tokens:
        return None
    return sum(_token_valid(t, lexicon) for t in tokens) / len(tokens)


def valid_word_count(text: str, lexicon: frozenset[str] | None = None) -> int:
    """Número de tokens válidos (criterio del híbrido para elegir motor)."""
    lexicon = load_lexicon() if lexicon is None else lexicon
    return sum(_token_valid(t, lexicon) for t in text.split())
