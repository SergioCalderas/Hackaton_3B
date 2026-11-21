"""Comparación de campos entre documentos, agrupación en expedientes (batch) y
verificación de coherencia de un expediente ya armado (modo producción).

Puntaje entre dos documentos (solo campos presentes en ambos; se re-normalizan pesos):
  ClaveCatastral (o CuentaPredial)  0.40
  Dirección (calle 70 % + número 30 %) 0.30
  Propietario                      0.20
  SuperficieTerreno                0.10
  Municipio o estado distintos -> puntaje × 0.6
Sin clave/cuenta ni calle comparables -> puntaje None (no se fuerza el match).
"""
from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass
from itertools import combinations

from rapidfuzz import fuzz
from rapidfuzz.distance import Levenshtein

from .fields import TIPOS, DocText, campos_utiles, detectar_tipo, extraer_campos
from .normalize import norm

TIPO_ALIASES = {
    "predial": "Predial", "boleta predial": "Predial", "pago predial": "Predial",
    "alineamiento": "Alineamiento", "alineamiento y numero oficial": "Alineamiento",
    "alineamiento_y_numero_oficial": "Alineamiento", "numero oficial": "Alineamiento",
    "escritura": "Escritura", "escrituras": "Escritura",
    "usodesuelo": "UsoDeSuelo", "uso de suelo": "UsoDeSuelo", "uso_de_suelo": "UsoDeSuelo",
    "licencia de uso de suelo": "UsoDeSuelo",
}


def canonical_tipo(tipo: str | None) -> str | None:
    if not tipo:
        return None
    if tipo in TIPOS:
        return tipo
    t = norm(tipo).lower().replace("_", " ")
    return TIPO_ALIASES.get(t) or TIPO_ALIASES.get(t.replace(" ", "")) or \
        next((v for k, v in TIPO_ALIASES.items() if k.split()[0] in t), None)


@dataclass
class MatchConfig:
    auto_threshold: float = 0.75     # >= se agrupa automáticamente
    review_threshold: float = 0.55   # entre review y auto -> hoja "revisar"
    equal_threshold: float = 0.95    # similitud mínima para "coincide"
    weights: tuple = (("clave", 0.40), ("direccion", 0.30), ("propietario", 0.20), ("superficie", 0.10))
    region_penalty: float = 0.6
    owner_only_cap: float = 0.70     # solo propietario + municipio: nunca agrupa solo


# ---------------------------------------------------------------------------
# Enriquecer documento: tipo detectado + campos
# ---------------------------------------------------------------------------
def enriquecer_documento(doc: dict, tipo_declarado: str | None = None) -> dict:
    """Agrega TipoDeclarado/TipoDetectado/TipoDocumento/CamposExtraidos/Discrepancias."""
    declarado = canonical_tipo(tipo_declarado or doc.get("TipoDeclarado") or doc.get("TipoDocumento"))
    pages = [(p["Numero"], p["Texto"]) for p in doc.get("Paginas", [])]
    detectado, _scores = detectar_tipo(DocText.from_pages(pages), declarado)
    tipo = declarado or detectado
    campos = extraer_campos(pages, tipo) if pages else {}
    disc = []
    if declarado and detectado and declarado != detectado:
        disc.append(f"TipoDeclarado ({declarado}) no coincide con TipoDetectado ({detectado}) por contenido")
    if declarado and not detectado and doc.get("TextoExtraido"):
        disc.append("No se pudo confirmar el tipo por contenido (texto ilegible o sin palabras clave)")
    if doc.get("Estado") in ("low_text", "low_confidence", "error", "partial"):
        disc.append(f"Calidad de extracción: {doc.get('Estado')} (CalidadTexto={doc.get('CalidadTexto')})")
    if not campos_utiles(campos):
        disc.append("Sin campos útiles para verificar (clave, cuenta, calle, propietario o superficie)")
    return {**doc, "TipoDocumento": tipo, "TipoDeclarado": declarado, "TipoDetectado": detectado,
            "CamposExtraidos": campos, "Discrepancias": disc, "ExpedienteId": doc.get("ExpedienteId")}


# ---------------------------------------------------------------------------
# Similitudes por campo (0..1)
# ---------------------------------------------------------------------------
_PREFIJOS_CALLE = r"^(CALLE|AVENIDA|CERRADA|PRIVADA|CARRETERA|BOULEVARD|CALZADA|ANDADOR|CAMINO|PROLONGACION)\s+"


def sim_clave(a: str, b: str) -> float:
    if a == b:
        return 1.0
    if a.rstrip("0") == b.rstrip("0") or a.lstrip("0") == b.lstrip("0"):
        return 0.97  # mismo número con ceros de relleno distintos
    if min(len(a), len(b)) >= 10 and (a in b or b in a):
        return 0.9
    d = Levenshtein.distance(a, b)
    if d == 1:
        return 0.85  # un dígito: OCR o discrepancia real -> se reporta
    if d == 2:
        return 0.6
    return 0.0


def sim_nombre(a: str, b: str) -> float:
    ta, tb = set(a.split()), set(b.split())
    small, big = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    if len(small) >= 2 and small <= big:
        return 1.0 if small == big else 0.92  # nombre incompleto ("GARCIA CERVANTES")
    return fuzz.token_sort_ratio(a, b) / 100


def sim_calle(a: str, b: str) -> float:
    a2, b2 = re.sub(_PREFIJOS_CALLE, "", a), re.sub(_PREFIJOS_CALLE, "", b)
    if not a2 or not b2:
        return 0.0
    return max(fuzz.token_set_ratio(a2, b2), fuzz.ratio(a2.replace(" ", ""), b2.replace(" ", ""))) / 100


def sim_texto(a: str, b: str) -> float:
    return max(fuzz.ratio(a, b), fuzz.token_set_ratio(a, b), fuzz.ratio(a.replace(" ", ""), b.replace(" ", ""))) / 100


def sim_superficie(a: float, b: float) -> float:
    if not a or not b:
        return 0.0
    rel = abs(a - b) / max(a, b)
    return 1.0 if rel <= 0.02 else 0.5 if rel <= 0.10 else 0.0


def sim_exacto(a, b) -> float:
    return 1.0 if str(a) == str(b) else 0.0


COMPARADORES = {
    "ClaveCatastral": sim_clave, "CuentaPredial": sim_exacto, "Propietario": sim_nombre,
    "Calle": sim_calle, "NumeroOficial": sim_exacto, "Colonia": sim_texto, "Municipio": sim_texto,
    "Estado": sim_exacto, "CodigoPostal": sim_exacto, "Lote": sim_exacto, "Manzana": sim_exacto,
    "SuperficieTerreno": sim_superficie,
}
CAMPOS_VERIFICACION = list(COMPARADORES)


def _n(doc: dict, campo: str):
    c = doc.get("CamposExtraidos", {}).get(campo)
    return c["Normalizado"] if c else None


def sim_campo(campo: str, a, b) -> float | None:
    if a in (None, "", []) or b in (None, "", []):
        return None
    return COMPARADORES[campo](a, b)


# ---------------------------------------------------------------------------
# Comparación de dos documentos
# ---------------------------------------------------------------------------
def comparar(a: dict, b: dict, cfg: MatchConfig) -> dict:
    sims = {c: sim_campo(c, _n(a, c), _n(b, c)) for c in CAMPOS_VERIFICACION}

    comps: dict[str, float] = {}
    clave = sims["ClaveCatastral"] if sims["ClaveCatastral"] is not None else sims["CuentaPredial"]
    if clave is not None:
        comps["clave"] = clave
    if sims["Calle"] is not None:
        comps["direccion"] = 0.7 * sims["Calle"] + 0.3 * sims["NumeroOficial"] if sims["NumeroOficial"] is not None \
            else sims["Calle"]
    if sims["Propietario"] is not None:
        comps["propietario"] = sims["Propietario"]
    if sims["SuperficieTerreno"] is not None:
        comps["superficie"] = sims["SuperficieTerreno"]

    # Ancla mínima: clave/cuenta o calle. Propietario + municipio también cuenta, pero con tope
    # (owner_only_cap) para que nunca se agrupe solo: va a la hoja "revisar".
    owner_only = ("clave" not in comps and "direccion" not in comps and "propietario" in comps
                  and sims["Municipio"] is not None)
    score = None
    if "clave" in comps or "direccion" in comps or owner_only:
        w = dict(cfg.weights)
        tot = sum(w[k] for k in comps)
        score = sum(w[k] * v for k, v in comps.items()) / tot
        for region in ("Municipio", "Estado"):
            if sims[region] is not None and sims[region] < 0.70:  # tolera variantes de OCR
                score *= cfg.region_penalty
        if owner_only:
            score = min(score, cfg.owner_only_cap)
        score = round(score, 4)

    coinciden = [c for c, s in sims.items() if s is not None and s >= cfg.equal_threshold]
    no_coinciden = [c for c, s in sims.items() if s is not None and s < cfg.equal_threshold]
    return {"score": score, "sims": sims, "coinciden": coinciden, "no_coinciden": no_coinciden}


# ---------------------------------------------------------------------------
# Construcción de un expediente (consolidación + discrepancias)
# ---------------------------------------------------------------------------
def _fuente(doc: dict, campo: str) -> dict:
    c = doc["CamposExtraidos"][campo]
    return {"Documento": doc["RutaArchivo"], "TipoDocumento": doc.get("TipoDocumento"),
            "Valor": c["Valor"], "Normalizado": c["Normalizado"], "Pagina": c["Pagina"]}


def _key(v) -> str:
    return "|".join(v) if isinstance(v, list) else str(v)


def construir_expediente(docs: list[dict], cfg: MatchConfig, pares: dict | None = None,
                         expediente_id: str | None = None) -> dict:
    pares = pares or {}
    rutas = [d["RutaArchivo"] for d in docs]

    # Comparaciones por par
    comparaciones, scores = [], []
    for a, b in combinations(docs, 2):
        key = (a["RutaArchivo"], b["RutaArchivo"])
        r = pares.get(key) or pares.get(key[::-1]) or comparar(a, b, cfg)
        comparaciones.append({"DocumentoA": key[0], "DocumentoB": key[1], "Puntaje": r["score"],
                              "Coinciden": r["coinciden"], "NoCoinciden": r["no_coinciden"]})
        if r["score"] is not None:
            scores.append(r["score"])

    # Consolidación
    nombres = sorted({c for d in docs for c in d.get("CamposExtraidos", {})} - {"Direccion"})
    consolidados = {}
    for campo in nombres:
        fuentes = [_fuente(d, campo) for d in docs if campo in d.get("CamposExtraidos", {})]
        cnt = Counter(_key(f["Normalizado"]) for f in fuentes)
        top = cnt.most_common(1)[0][0]
        best = next(f for f in fuentes if _key(f["Normalizado"]) == top)
        consolidados[campo] = {"Valor": best["Valor"], "Normalizado": best["Normalizado"], "Fuentes": fuentes}

    # Coinciden / no coinciden: cada fuente contra el valor consolidado (el más frecuente).
    coinciden, no_coinciden = [], []
    for campo in CAMPOS_VERIFICACION:
        fuentes = consolidados.get(campo, {}).get("Fuentes", [])
        if len(fuentes) < 2:
            continue
        ref = consolidados[campo]["Normalizado"]
        sims = [sim_campo(campo, ref, f["Normalizado"]) for f in fuentes]
        sims = [s for s in sims if s is not None]
        smin = min(sims) if sims else None
        if smin is not None and smin >= cfg.equal_threshold:
            coinciden.append(campo)
        elif smin is not None:
            detalle = ("difieren levemente (posible error de OCR o alteración)" if smin >= 0.8
                       else "valores distintos entre documentos")
            no_coinciden.append({"Campo": campo, "Detalle": detalle, "Similitud": round(smin, 3), "Valores": fuentes})

    # Prediales del mismo ejercicio fiscal
    prediales = [d for d in docs if d.get("TipoDocumento") == "Predial"]
    for p1, p2 in combinations(prediales, 2):
        y1, y2 = set(_n(p1, "EjercicioFiscal") or []), set(_n(p2, "EjercicioFiscal") or [])
        if y1 & y2:
            no_coinciden.append({
                "Campo": "EjercicioFiscal", "Similitud": None,
                "Detalle": f"dos prediales del mismo ejercicio fiscal ({', '.join(sorted(y1 & y2))})",
                "Valores": [_fuente(p, "EjercicioFiscal") for p in (p1, p2)]})

    # Tipos
    tipos = [d.get("TipoDocumento") for d in docs if d.get("TipoDocumento")]
    presentes = [t for t in TIPOS if t in tipos]
    faltantes = [t for t in TIPOS if t not in tipos]

    alertas = []
    for t, n in Counter(tipos).items():
        if n > 1 and t != "Predial":
            alertas.append(f"Hay {n} documentos de tipo {t} en el expediente")
    for d in docs:
        if d.get("TipoDocumento") is None:
            alertas.append(f"{d['RutaArchivo']}: tipo de documento desconocido")
        for x in d.get("Discrepancias", []):
            alertas.append(f"{d['RutaArchivo']}: {x}")
    if len(docs) > 2:  # documento que no cuadra con el resto
        for d in docs:
            own = [c["Puntaje"] for c in comparaciones
                   if d["RutaArchivo"] in (c["DocumentoA"], c["DocumentoB"]) and c["Puntaje"] is not None]
            if own and sum(own) / len(own) < cfg.review_threshold:
                alertas.append(f"{d['RutaArchivo']}: puntaje promedio {sum(own) / len(own):.2f} con el resto; "
                               f"posible documento de otro inmueble")

    puntaje = round(sum(scores) / len(scores), 4) if scores else None
    nivel = ("sin_datos" if puntaje is None else "alto" if puntaje >= cfg.auto_threshold
             else "medio" if puntaje >= cfg.review_threshold else "bajo")

    if not expediente_id:
        clave = consolidados.get("ClaveCatastral", {}).get("Normalizado")
        expediente_id = f"EXP-{clave}" if clave else \
            "EXP-" + hashlib.sha1("|".join(sorted(d.get("Hash") or d["RutaArchivo"] for d in docs)).encode()).hexdigest()[:10]

    documentos = [{**d, "ExpedienteId": expediente_id} for d in docs]
    return {
        "ExpedienteId": expediente_id, "CamposConsolidados": consolidados, "PuntajeMatch": puntaje,
        "NivelMatch": nivel, "CamposCoinciden": coinciden, "CamposNoCoinciden": no_coinciden,
        "TiposPresentes": presentes, "DocumentosFaltantes": faltantes, "Alertas": alertas,
        "Comparaciones": comparaciones, "Documentos": documentos,
    }


# ---------------------------------------------------------------------------
# Batch: agrupar documentos sueltos en expedientes
# ---------------------------------------------------------------------------
def _compatible(ga: list[dict], gb: list[dict]) -> str | None:
    """None si se pueden unir; si no, el motivo.

    Regla: máximo un documento por tipo (salvo Predial, que puede repetirse por ejercicio).
    Excepción: dos documentos del mismo tipo con clave catastral IDÉNTICA (p. ej. constancia de
    alineamiento y constancia de número oficial del mismo predio) sí se unen; queda como alerta.
    """
    for d in gb:
        t = d.get("TipoDocumento")
        if not t or t == "Predial":
            continue
        for o in ga:
            if o.get("TipoDocumento") != t:
                continue
            ca, cb = _n(o, "ClaveCatastral"), _n(d, "ClaveCatastral")
            if not (ca and cb and ca == cb):
                return f"ya hay un documento de tipo {t}"
    return None


def agrupar(docs: list[dict], cfg: MatchConfig | None = None) -> dict:
    """Devuelve {"expedientes": [...], "revisar": [...], "sin_match": [...], "pares": {...}}."""
    cfg = cfg or MatchConfig()
    usable = [d for d in docs if campos_utiles(d.get("CamposExtraidos", {})) and not d.get("DuplicadoDe")]
    by_ruta = {d["RutaArchivo"]: d for d in docs}

    pares = {}
    for a, b in combinations(usable, 2):
        r = comparar(a, b, cfg)
        if r["score"] is not None:
            pares[(a["RutaArchivo"], b["RutaArchivo"])] = r

    grupo = {d["RutaArchivo"]: i for i, d in enumerate(usable)}
    miembros = {i: [d["RutaArchivo"]] for i, d in enumerate(usable)}
    bloqueados = []

    def score(x, y):
        r = pares.get((x, y)) or pares.get((y, x))
        return r["score"] if r else None

    for (ra, rb), r in sorted(pares.items(), key=lambda kv: -kv[1]["score"]):
        if r["score"] < cfg.auto_threshold:
            break
        ga, gb = grupo[ra], grupo[rb]
        if ga == gb:
            continue
        motivo = _compatible([by_ruta[x] for x in miembros[ga]], [by_ruta[x] for x in miembros[gb]])
        cross = [s for x in miembros[ga] for y in miembros[gb] if (s := score(x, y)) is not None]
        if not motivo and cross and (sum(cross) / len(cross) < cfg.review_threshold or min(cross) < 0.3):
            motivo = "el resto de los documentos del grupo no coincide"
        if motivo:
            bloqueados.append((ra, rb, r, motivo))
            continue
        for x in miembros[gb]:
            grupo[x] = ga
        miembros[ga] += miembros.pop(gb)

    expedientes, ids = [], Counter()
    for rutas in miembros.values():
        if len(rutas) < 2:
            continue
        exp = construir_expediente([by_ruta[r] for r in sorted(rutas)], cfg, pares)
        ids[exp["ExpedienteId"]] += 1
        if ids[exp["ExpedienteId"]] > 1:  # misma clave en dos grupos
            exp = construir_expediente([by_ruta[r] for r in sorted(rutas)], cfg, pares,
                                       f"{exp['ExpedienteId']}-{ids[exp['ExpedienteId']]}")
        expedientes.append(exp)
    expedientes.sort(key=lambda e: (-len(e["Documentos"]), e["ExpedienteId"]))

    exp_de = {d["RutaArchivo"]: e["ExpedienteId"] for e in expedientes for d in e["Documentos"]}

    revisar = []
    for (ra, rb), r in pares.items():
        same = exp_de.get(ra) and exp_de.get(ra) == exp_de.get(rb)
        if cfg.review_threshold <= r["score"] < cfg.auto_threshold and not same:
            revisar.append({"DocumentoA": ra, "DocumentoB": rb, "Puntaje": r["score"],
                            "ExpedienteA": exp_de.get(ra), "ExpedienteB": exp_de.get(rb),
                            "Motivo": "puntaje medio", "Coinciden": r["coinciden"], "NoCoinciden": r["no_coinciden"]})
    for ra, rb, r, motivo in bloqueados:
        if not (exp_de.get(ra) and exp_de.get(ra) == exp_de.get(rb)):
            revisar.append({"DocumentoA": ra, "DocumentoB": rb, "Puntaje": r["score"],
                            "ExpedienteA": exp_de.get(ra), "ExpedienteB": exp_de.get(rb),
                            "Motivo": f"puntaje alto pero no se unió: {motivo}",
                            "Coinciden": r["coinciden"], "NoCoinciden": r["no_coinciden"]})
    revisar.sort(key=lambda x: -x["Puntaje"])

    sin_match = []
    for d in docs:
        ruta = d["RutaArchivo"]
        if ruta in exp_de:
            continue
        if d.get("DuplicadoDe"):
            motivo = f"duplicado de {d['DuplicadoDe']}"
        elif not campos_utiles(d.get("CamposExtraidos", {})):
            motivo = "sin campos útiles (texto ilegible o sin datos del predio)"
        else:
            motivo = "ningún otro documento supera el umbral"
        cands = sorted(((r["score"], rb if ra == ruta else ra) for (ra, rb), r in pares.items() if ruta in (ra, rb)),
                       reverse=True)
        best = cands[0] if cands else (None, None)
        sin_match.append({"Documento": ruta, "TipoDocumento": d.get("TipoDocumento"), "Estado": d.get("Estado"),
                          "Motivo": motivo, "MejorCandidato": best[1], "PuntajeMejorCandidato": best[0],
                          "ExpedienteMejorCandidato": exp_de.get(best[1]) if best[1] else None})
    return {"expedientes": expedientes, "revisar": revisar, "sin_match": sin_match, "pares": pares}


def verificar(docs: list[dict], cfg: MatchConfig | None = None) -> dict:
    """Modo producción: todos los documentos son del mismo inmueble; se verifica su coherencia."""
    return construir_expediente(docs, cfg or MatchConfig())


# ---------------------------------------------------------------------------
# Modo compacto (para el LLM): sin texto completo
# ---------------------------------------------------------------------------
MODOS = ("completo", "compacto")


def compactar_documento(doc: dict) -> dict:
    """Quita TextoExtraido y el texto de las páginas; conserva solo las páginas donde
    se encontró algún campo (con sus metadatos). Campos, evidencia y discrepancias quedan intactos."""
    usadas = {c.get("Pagina") for c in doc.get("CamposExtraidos", {}).values()}
    paginas = [{**p, "Texto": None} for p in doc.get("Paginas", []) if p["Numero"] in usadas]
    return {**doc, "Modo": "compacto", "TextoExtraido": None, "Paginas": paginas}


def compactar_expediente(exp: dict) -> dict:
    return {**exp, "Modo": "compacto", "Documentos": [compactar_documento(d) for d in exp["Documentos"]]}


def aplicar_modo(obj: dict, modo: str, es_expediente: bool) -> dict:
    if modo not in MODOS:
        raise ValueError(f"modo debe ser uno de {MODOS}, no {modo!r}")
    if modo == "completo":
        return {**obj, "Modo": "completo"}
    return compactar_expediente(obj) if es_expediente else compactar_documento(obj)
