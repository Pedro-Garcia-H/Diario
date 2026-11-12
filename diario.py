# -*- coding: utf-8 -*-
"""
EL DIARIO DE PEDRO (versión automática, sin IA)
================================================
Junta titulares de medios por RSS, el clima, el tipo de cambio, las
efemérides y lo más buscado en Google, y arma una página HTML con el diseño
del diario.

Uso:  python diario.py
Sale en:  docs/index.html  (y una copia en docs/archivo/AAAA-MM-DD.html)

Todo lo que querés cambiar seguido (medios, palabras, frases) está en
config.py, no aquí.
"""

import calendar
import datetime as dt
import difflib
import html
import json
import os
import random
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

import feedparser
import requests

import config

AQUI = os.path.dirname(os.path.abspath(__file__))
SALIDA = os.path.join(AQUI, "docs")
TZ = ZoneInfo(config.ZONA_HORARIA)
AHORA = dt.datetime.now(TZ)
UA = {"User-Agent": "Mozilla/5.0 (DiarioDePedro; lector RSS personal)"}

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]

PALABRAS_DEPORTE = ["futbol", "gol ", "goles", "liga nacional", "partido", "seleccion",
                    "cremas", "comunicaciones fc", "municipal", "torneo apertura",
                    "torneo clausura", "entrenador", "concacaf", "nba", "nfl",
                    "champions", "laliga", "estadio", "jornada", "tenis", "boxeo"]

AVISOS = []  # problemas para mostrar al pie (fuentes que no respondieron, etc.)


# ---------------------------------------------------------------- utilidades
def e(texto):
    """Escapa texto para HTML."""
    return html.escape(str(texto or ""), quote=True)


def normal(texto):
    """Minúsculas y sin tildes, para comparar palabras."""
    t = unicodedata.normalize("NFD", (texto or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def limpiar_html(texto):
    t = re.sub(r"(?is)<(script|style|figure|figcaption).*?</\1>", " ", texto or "")
    t = re.sub(r"(?s)<[^>]+>", " ", t)
    t = html.unescape(t)
    t = re.sub(r"(?i)the post .* appeared first on .*$", "", t)
    t = re.sub(r"(?i)la entrada .* se public[oó] primero en .*$", "", t)
    t = re.sub(r"\[(…|\.\.\.)\]", "…", t)
    return re.sub(r"\s+", " ", t).strip()


def recortar(texto, largo=280):
    """Deja el resumen en una o dos oraciones."""
    if len(texto) <= largo:
        return texto
    corte = texto[:largo]
    punto = max(corte.rfind(". "), corte.rfind("? "), corte.rfind("! "))
    if punto > 120:
        return corte[:punto + 1]
    return corte[:corte.rfind(" ")].rstrip(",;:") + "…"


def descargar(url, timeout=25, **kw):
    r = requests.get(url, headers=UA, timeout=timeout, **kw)
    r.raise_for_status()
    return r


def fecha_larga(d):
    return f"{DIAS[d.weekday()]} {d.day} de {MESES[d.month - 1]} de {d.year}"


def hora_corta(d):
    h = d.hour % 12 or 12
    return f"{h}:{d.minute:02d} {'a. m.' if d.hour < 12 else 'p. m.'}"


# ---------------------------------------------------------------- noticias
def leer_feed(fuente, horas):
    """Devuelve la lista de notas de un feed, ya limpias."""
    try:
        datos = feedparser.parse(descargar(fuente["url"]).content)
    except Exception as err:  # el medio no respondió: seguimos con los demás
        AVISOS.append(f"No pude leer {fuente['medio']} ({type(err).__name__}).")
        return []
    if not datos.entries:
        AVISOS.append(f"{fuente['medio']} no trajo notas hoy.")
        return []

    limite = AHORA - dt.timedelta(hours=horas)
    excluir = [normal(c) for c in fuente.get("excluir_categorias", [])]
    solo = [normal(c) for c in fuente.get("solo_categorias", [])]
    notas = []
    for it in datos.entries:
        titulo = limpiar_html(it.get("title", ""))
        enlace = it.get("link", "")
        if not titulo or not enlace:
            continue
        cuando = it.get("published_parsed") or it.get("updated_parsed")
        fecha = (dt.datetime.fromtimestamp(calendar.timegm(cuando), dt.timezone.utc).astimezone(TZ)
                 if cuando else None)
        if fecha and fecha < limite:
            continue
        cats = [normal(t.get("term", "")) for t in it.get("tags", []) or []]
        if excluir and any(c in excluir for c in cats):
            continue
        if solo and cats and not any(c in solo for c in cats):
            continue
        resumen = recortar(limpiar_html(it.get("summary", "")))
        if normal(resumen).startswith(normal(titulo)[:40]):
            resumen = resumen[len(titulo):].strip(" .:-—")
        notas.append({
            "titulo": titulo, "enlace": enlace, "resumen": resumen,
            "fecha": fecha, "medio": fuente["medio"], "peso": fuente.get("peso", 1),
            "idioma": fuente.get("idioma", "es"), "cats": cats,
        })
    return notas


def es_nota_roja(nota):
    t = normal(nota["titulo"] + " " + nota["resumen"])
    return any(p in t for p in config.NOTA_ROJA)


def es_deporte(nota):
    t = normal(nota["titulo"])
    por_palabra = any(re.search(r"\b" + re.escape(p.strip()) + r"\b", t) for p in PALABRAS_DEPORTE)
    return por_palabra or any("deport" in c or "futbol" in c for c in nota["cats"])


def puntaje(nota):
    t = " " + normal(nota["titulo"] + " " + nota["resumen"]) + " "
    p = nota["peso"] * 2
    for palabra, puntos in config.PRIORIDAD.items():
        if palabra in t:
            p += puntos * (2 if palabra in normal(nota["titulo"]) else 1)
    if nota["fecha"]:
        horas = (AHORA - nota["fecha"]).total_seconds() / 3600
        p += max(0, 8 - horas / 3)  # lo más reciente suma un poco
    return p


def repetida(nota, vistas):
    a = normal(nota["titulo"])
    pa = set(re.findall(r"\w{4,}", a))
    for v in vistas:
        b = normal(v["titulo"])
        if difflib.SequenceMatcher(None, a, b).ratio() > 0.62:
            return True
        pb = set(re.findall(r"\w{4,}", b))
        if pa and pb and len(pa & pb) / min(len(pa), len(pb)) >= 0.6:
            return True
    return False


def juntar_noticias():
    """Lee todas las secciones, quita repetidas y nota roja, y ordena."""
    crudas = {}
    cache = {}  # si dos secciones usan el mismo feed, se descarga una sola vez
    for clave, sec in config.SECCIONES.items():
        horas = sec.get("horas_atras", config.HORAS_ATRAS)
        notas = []
        for f in sec["fuentes"]:
            llave = (f["url"], horas, str(f.get("excluir_categorias")), str(f.get("solo_categorias")))
            if llave not in cache:
                cache[llave] = leer_feed(f, horas)
            notas += [dict(n, medio=f["medio"], peso=f.get("peso", 1)) for n in cache[llave]]
        # Secciones como Eventos solo se quedan con las notas que tienen sus palabras.
        if sec.get("solo_palabras"):
            palabras = [normal(p) for p in sec["solo_palabras"]]
            notas = [n for n in notas if any(p in normal(n["titulo"] + " " + n["resumen"]) for p in palabras)]
        crudas[clave] = notas

    todas = [n for lista in crudas.values() for n in lista]
    alertas = buscar_alertas(todas)

    # Las notas deportivas que llegan por los medios nacionales pasan a Deportes.
    deportivas = [n for n in crudas.get("guatemala", []) if es_deporte(n)]
    crudas["guatemala"] = [n for n in crudas.get("guatemala", []) if not es_deporte(n)]
    crudas.setdefault("deportes", []).extend(deportivas)

    # Lo que tenga palabras de "NO:" en gustos.txt no sale en ningún lado.
    gustos, no_quiero = leer_gustos()
    for clave in crudas:
        crudas[clave] = [n for n in crudas[clave] if not menciona(n, no_quiero)]

    # "Lo tuyo" se elige primero, para que esas notas no se repitan abajo.
    vistas = list(alertas)  # lo que ya sale en "Ojo con esto" no se repite
    lo_tuyo = elegir_lo_tuyo(crudas, gustos, vistas)
    vistas += [n for n, _ in lo_tuyo]

    # Eventos y entretenimiento van primero al quitar repetidas, para que una
    # nota de un concierto no se quede perdida en Nacionales.
    primero = [c for c in ("eventos", "entretenimiento") if c in crudas]
    orden = primero + [c for c in crudas if c not in primero]
    finales = {"lo_tuyo": lo_tuyo}
    for clave in orden:
        lista = crudas[clave]
        elegidas = []
        for n in sorted(lista, key=puntaje, reverse=True):
            if es_nota_roja(n) or repetida(n, vistas):
                continue
            vistas.append(n)
            elegidas.append(n)
        finales[clave] = elegidas
    return finales, alertas


def buscar_alertas(notas):
    zonas = [normal(z) for z in config.ZONAS_CERCANAS]
    # Los cortes de agua y luz solo cuentan si mencionan una zona cercana.
    servicios = ["agua", "empagua", "energia", "luz", "eegsa"]
    salida = []
    for n in notas:
        t = normal(n["titulo"] + " " + n["resumen"])
        if not any(normal(a) in t for a in config.ALERTAS):
            continue
        servicio = any(s in t for s in servicios)
        if not servicio or any(z in t for z in zonas):
            if not repetida(n, salida):
                salida.append(n)
    return salida[:3]


# ---------------------------------------------------------------- lo tuyo
def leer_gustos():
    """Lee gustos.txt. Devuelve (gustos, no_quiero).
    gustos: lista de (nombre que se muestra, [palabras a buscar]).
    no_quiero: lista de palabras de las líneas que empiezan con NO:"""
    ruta = os.path.join(AQUI, config.ARCHIVO_GUSTOS)
    if not os.path.exists(ruta):
        return [], []
    gustos, no_quiero, vistos = [], [], set()
    for linea in open(ruta, encoding="utf-8"):
        linea = linea.strip()
        if not linea or linea.startswith("#"):
            continue
        if normal(linea).startswith("no:"):
            no_quiero += [normal(p.strip()) for p in linea[3:].split("|") if p.strip()]
            continue
        nombres = [p.strip() for p in linea.split("|") if p.strip()]
        if nombres and normal(nombres[0]) not in vistos:
            vistos.add(normal(nombres[0]))
            gustos.append((nombres[0], [normal(p) for p in nombres]))
    return gustos, no_quiero


def menciona(nota, palabras):
    """¿La nota menciona alguna de estas palabras (como palabra completa)?
    Devuelve la primera que encuentre, o None."""
    t = " " + normal(nota["titulo"] + " " + nota["resumen"]) + " "
    for p in palabras:
        if re.search(r"(?<!\w)" + re.escape(p) + r"(?!\w)", t):
            return p
    return None


def elegir_lo_tuyo(crudas, gustos, vistas):
    """Busca en todas las secciones las notas que hablan de tus gustos.
    Máximo 2 notas por gusto, para que haya variedad."""
    candidatas = []
    for lista in crudas.values():
        for n in lista:
            if es_nota_roja(n):
                continue
            for nombre, palabras in gustos:
                if menciona(n, palabras):
                    # En el titular vale más que solo en el resumen.
                    extra = 10 if menciona({"titulo": n["titulo"], "resumen": ""}, palabras) else 0
                    candidatas.append((puntaje(n) + extra, n, nombre))
                    break
    elegidas, por_gusto, ya = [], {}, list(vistas)
    for _, n, nombre in sorted(candidatas, key=lambda c: c[0], reverse=True):
        if por_gusto.get(nombre, 0) >= 2 or repetida(n, ya):
            continue
        por_gusto[nombre] = por_gusto.get(nombre, 0) + 1
        ya.append(n)
        elegidas.append((n, nombre))
        if len(elegidas) == config.MAX_LO_TUYO:
            break
    return elegidas


# ---------------------------------------------------------------- fútbol
def sin_tildes_equipo(nombre):
    return normal(nombre).replace("-", " ").replace(".", "")


def tiene(equipo, palabra):
    return re.search(r"(?<!\w)" + re.escape(palabra.replace("-", " ")) + r"(?!\w)", sin_tildes_equipo(equipo)) is not None


def leer_partidos():
    """Busca en ESPN los partidos de tus equipos, los clásicos y los del big 6.
    Devuelve (proximos, resultados)."""
    desde = (AHORA - dt.timedelta(days=config.DIAS_RESULTADOS)).strftime("%Y%m%d")
    hasta = (AHORA + dt.timedelta(days=config.DIAS_PARTIDOS)).strftime("%Y%m%d")
    proximos, resultados, ids, fallaron, errores = [], [], set(), [], set()
    dias = [(AHORA + dt.timedelta(days=d)).strftime("%Y%m%d")
            for d in range(-config.DIAS_RESULTADOS, config.DIAS_PARTIDOS + 1)]
    for codigo, liga in config.LIGAS_ESPN.items():
        url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{codigo}/scoreboard"
        eventos = None
        # Primero se piden todos los días de un solo; si ESPN no lo acepta, día por día.
        try:
            eventos = descargar(url, timeout=15, params={"dates": f"{desde}-{hasta}"}).json().get("events", [])
        except Exception as err:
            errores.add(str(getattr(getattr(err, "response", None), "status_code", type(err).__name__)))
            eventos = []
            ok = False
            for dia in dias:
                try:
                    eventos += descargar(url, timeout=15, params={"dates": dia}).json().get("events", [])
                    ok = True
                except Exception as err2:
                    errores.add(str(getattr(getattr(err2, "response", None), "status_code", type(err2).__name__)))
                    if not ok:
                        break  # si el primer día también falla, esa liga no funciona
            if not ok:
                fallaron.append(liga)
                continue
        for ev in eventos:
            if ev.get("id") in ids:
                continue
            try:
                comp = ev["competitions"][0]
                eq = {c["homeAway"]: c for c in comp["competitors"]}
                local, visita = eq["home"]["team"]["displayName"], eq["away"]["team"]["displayName"]
                fecha = dt.datetime.fromisoformat(ev["date"].replace("Z", "+00:00")).astimezone(TZ)
            except (KeyError, IndexError, ValueError):
                continue
            motivo = motivo_partido(local, visita)
            if motivo is None:
                continue
            ids.add(ev.get("id"))
            estado = ev.get("status", {}).get("type", {})
            p = {"fecha": fecha, "local": local, "visita": visita, "liga": liga, "motivo": motivo,
                 "hora_ok": comp.get("timeValid", True), "estado": estado.get("state", "pre"),
                 "detalle": estado.get("description", ""),
                 "goles_local": eq["home"].get("score", ""), "goles_visita": eq["away"].get("score", "")}
            if p["estado"] == "post":
                resultados.append(p)
            elif fecha.date() >= AHORA.date():
                proximos.append(p)
    if len(fallaron) == len(config.LIGAS_ESPN):
        AVISOS.append(f"No pude leer los partidos de ESPN (error {', '.join(sorted(errores))}).")
    elif fallaron:
        AVISOS.append(f"ESPN no respondió para: {', '.join(fallaron)}.")
    proximos.sort(key=lambda p: p["fecha"])
    resultados.sort(key=lambda p: p["fecha"], reverse=True)
    return proximos, resultados


def motivo_partido(local, visita):
    """Dice por qué un partido sale en el diario, o None si no interesa."""
    for a, b, nombre in config.CLASICOS:
        if (tiene(local, a) and tiene(visita, b)) or (tiene(local, b) and tiene(visita, a)):
            return nombre
    if any(tiene(local, x) for x in config.BIG_6) and any(tiene(visita, x) for x in config.BIG_6):
        return "Big 6"
    if any(tiene(local, x) or tiene(visita, x) for x in config.MIS_EQUIPOS):
        return ""
    return None


def leer_tabla_espn():
    url = "https://site.api.espn.com/apis/v2/sports/soccer/gua.1/standings"
    datos = descargar(url).json()
    # La tabla viene adentro de "children" o directo en "standings".
    grupos = datos.get("children") or [datos]
    entradas = []
    for g in grupos:
        entradas = g.get("standings", {}).get("entries", [])
        if entradas:
            break
    filas = []
    for ent in entradas:
        st = {s.get("name"): s.get("value") for s in ent.get("stats", [])}
        filas.append({"equipo": ent["team"]["displayName"],
                      "pj": int(st.get("gamesPlayed") or 0), "g": int(st.get("wins") or 0),
                      "e": int(st.get("ties") or 0), "p": int(st.get("losses") or 0),
                      "dif": int(st.get("pointDifferential") or 0), "pts": int(st.get("points") or 0),
                      "pos": int(st.get("rank") or 0)})
    if not filas:
        raise ValueError("tabla vacía")
    filas.sort(key=lambda f: (f["pos"] or 99, -f["pts"], -f["dif"]))
    return filas


def wiki_tablas(pagina, palabras_seccion):
    """Lee la primera tabla de la sección de Wikipedia cuyo título tenga
    alguna de esas palabras. Devuelve una lista de filas (listas de textos)."""
    api = "https://es.wikipedia.org/w/api.php"
    secciones = descargar(api, params={"action": "parse", "page": pagina, "prop": "sections",
                                       "format": "json", "formatversion": 2, "redirects": 1}).json()
    indice = None
    for s in secciones.get("parse", {}).get("sections", []):
        if any(p in normal(s.get("line", "")) for p in palabras_seccion):
            indice = s["index"]
            break
    if indice is None:
        return []
    html_sec = descargar(api, params={"action": "parse", "page": pagina, "prop": "text", "section": indice,
                                      "format": "json", "formatversion": 2, "redirects": 1}).json()["parse"]["text"]
    tabla = re.search(r"(?is)<table.*?</table>", html_sec)
    if not tabla:
        return []
    filas = []
    for tr in re.findall(r"(?is)<tr.*?</tr>", tabla.group(0)):
        celdas = [limpiar_html(c) for c in re.findall(r"(?is)<t[hd][^>]*>(.*?)</t[hd]>", tr)]
        if celdas:
            filas.append(celdas)
    return filas


def torneo_actual():
    if config.WIKI_TORNEO:
        return config.WIKI_TORNEO
    nombre = "Apertura" if AHORA.month >= 7 else "Clausura"
    return f"Torneo {nombre} {AHORA.year} (Guatemala)"


def leer_tabla_wiki():
    filas = wiki_tablas(torneo_actual(), ["tabla general", "clasificacion", "tabla de posiciones", "posiciones"])
    if len(filas) < 2:
        raise ValueError("sin tabla en Wikipedia")
    cab = [normal(c) for c in filas[0]]

    def col(*nombres):
        for i, c in enumerate(cab):
            if any(c == n or c.startswith(n) for n in nombres):
                return i
        return None
    i_eq, i_pts, i_pj = col("equipo", "club"), col("pts", "puntos"), col("pj", "jj")
    i_g, i_e, i_p, i_dif = col("g", "pg", "jg"), col("e", "pe", "je"), col("p", "pp", "jp"), col("dif", "dg", "+/-")
    if i_eq is None or i_pts is None:
        raise ValueError("no entendí la tabla de Wikipedia")

    def num(fila, i):
        try:
            return int(re.sub(r"[^\d-]", "", fila[i].replace("−", "-"))) if i is not None else 0
        except (ValueError, IndexError):
            return 0
    salida = []
    for fila in filas[1:]:
        if len(fila) <= max(i_eq, i_pts):
            continue
        salida.append({"equipo": fila[i_eq], "pj": num(fila, i_pj), "g": num(fila, i_g), "e": num(fila, i_e),
                       "p": num(fila, i_p), "dif": num(fila, i_dif), "pts": num(fila, i_pts), "pos": len(salida) + 1})
    if not salida:
        raise ValueError("tabla vacía en Wikipedia")
    return salida


def leer_tabla():
    try:
        return leer_tabla_espn(), "ESPN"
    except Exception:
        pass
    try:
        return leer_tabla_wiki(), "Wikipedia"
    except Exception as err:
        AVISOS.append(f"No pude leer la tabla de la Liga Nacional ({type(err).__name__}).")
        return [], ""


def leer_goleadores(n=5):
    try:
        filas = wiki_tablas(torneo_actual(), ["goleador"])
    except Exception as err:
        AVISOS.append(f"No pude leer los goleadores ({type(err).__name__}).")
        return []
    salida = []
    for fila in filas:
        numeros = [c for c in fila if re.fullmatch(r"\d{1,2}", c)]
        textos = [c for c in fila if re.search(r"[A-Za-zÁÉÍÓÚáéíóúÑñ]{3,}", c)]
        if not numeros or not textos or normal(textos[0]) in ("jugador", "nombre", "futbolista"):
            continue
        salida.append({"jugador": textos[0], "club": textos[1] if len(textos) > 1 else "", "goles": int(numeros[-1])})
    if filas and not salida:
        AVISOS.append("No entendí la tabla de goleadores de Wikipedia.")
    salida.sort(key=lambda g: -g["goles"])
    return salida[:n]


# ---------------------------------------------------------------- estrenos (TMDB)
def leer_estrenos():
    """Próximas películas en Guatemala y series nuevas, de TMDB. Necesita llave."""
    llave = os.environ.get("TMDB_API_KEY", "").strip()
    if not llave:
        return [], []
    base = "https://api.themoviedb.org/3"
    hoy = AHORA.date()
    en_un_mes = (AHORA + dt.timedelta(days=30)).date()
    pelis, series = [], []
    try:
        datos = descargar(f"{base}/movie/upcoming", params={"api_key": llave, "language": "es-MX",
                                                            "region": config.REGION_CINE}).json()
        for p in datos.get("results", []):
            fecha = p.get("release_date") or ""
            if fecha and hoy.isoformat() <= fecha <= en_un_mes.isoformat():
                pelis.append({"titulo": p.get("title", ""), "fecha": dt.date.fromisoformat(fecha),
                              "resumen": recortar(p.get("overview", ""), 160),
                              "url": f"https://www.themoviedb.org/movie/{p.get('id')}"})
        datos = descargar(f"{base}/discover/tv", params={"api_key": llave, "language": "es-MX",
                                                         "sort_by": "popularity.desc",
                                                         "first_air_date.gte": hoy.isoformat(),
                                                         "first_air_date.lte": en_un_mes.isoformat()}).json()
        for s in datos.get("results", []):
            fecha = s.get("first_air_date") or ""
            if fecha:
                series.append({"titulo": s.get("name", ""), "fecha": dt.date.fromisoformat(fecha),
                               "resumen": recortar(s.get("overview", ""), 160),
                               "url": f"https://www.themoviedb.org/tv/{s.get('id')}"})
    except Exception as err:
        AVISOS.append(f"No pude leer los estrenos de TMDB ({type(err).__name__}).")
    pelis.sort(key=lambda x: x["fecha"])
    return pelis[:config.MAX_ESTRENOS], series[:config.MAX_ESTRENOS]


# ---------------------------------------------------------------- cuenta regresiva
def semana_santa(anio):
    """Jueves Santo de ese año (calculado con la fecha de la Pascua)."""
    a, b, c = anio % 19, anio // 100, anio % 100
    d, e_ = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e_ + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = (h + l - 7 * m + 114) % 31 + 1
    return dt.date(anio, mes, dia) - dt.timedelta(days=3)


def cuenta_regresiva():
    hoy = AHORA.date()
    fechas = []
    for item in config.FECHAS_ESPECIALES:
        nombre, dia, mes = item[0], item[1], item[2]
        anios = [item[3]] if len(item) > 3 else [hoy.year, hoy.year + 1]
        for anio in anios:
            try:
                fechas.append((nombre, dt.date(anio, mes, dia)))
            except ValueError:
                pass
    for anio in (hoy.year, hoy.year + 1):
        fechas.append(("Semana Santa", semana_santa(anio)))
    proximas, ya = [], set()
    for nombre, fecha in sorted(fechas, key=lambda x: x[1]):
        if fecha >= hoy and nombre not in ya:
            ya.add(nombre)
            proximas.append((nombre, fecha, (fecha - hoy).days))
    return proximas[:config.MAX_CUENTA_REGRESIVA]


# ---------------------------------------------------------------- el cielo
PLANETAS = [("Mercurio", "Mercury"), ("Venus", "Venus"), ("Marte", "Mars"),
            ("Júpiter", "Jupiter"), ("Saturno", "Saturn")]
RUMBOS = ["el norte", "el noreste", "el este", "el sureste", "el sur", "el suroeste", "el oeste", "el noroeste"]


def leer_cielo():
    """Luna y planetas que se ven esta noche desde tu casa (cálculo local, sin internet)."""
    try:
        import ephem
    except ImportError:
        AVISOS.append("Falta la librería ephem para el cielo de esta noche.")
        return None
    casa = ephem.Observer()
    casa.lat, casa.lon, casa.elevation = str(config.LATITUD), str(config.LONGITUD), 1500
    sol = ephem.Sun()

    # Revisamos el cielo cada 15 minutos, de 6:30 p. m. a 5:30 a. m.
    inicio = AHORA.replace(hour=18, minute=30, second=0, microsecond=0)
    momentos = [inicio + dt.timedelta(minutes=15 * i) for i in range(45)]
    planetas = []
    for nombre, clase in PLANETAS:
        cuerpo = getattr(ephem, clase)()
        visibles = []
        for m in momentos:
            casa.date = ephem.Date(m.astimezone(dt.timezone.utc).replace(tzinfo=None))
            sol.compute(casa)
            cuerpo.compute(casa)
            alto = float(cuerpo.alt) * 57.2958
            if float(sol.alt) * 57.2958 < -8 and alto > 10:
                visibles.append((m, alto, float(cuerpo.az) * 57.2958))
        info = {"nombre": nombre, "visible": bool(visibles)}
        if visibles:
            mejor = max(visibles, key=lambda v: v[1])
            info.update(desde=visibles[0][0], hasta=visibles[-1][0], hora_mejor=mejor[0],
                        rumbo=RUMBOS[int(((mejor[2] + 22.5) % 360) // 45)])
        if clase == "Mars":
            info["distancia"] = cuerpo.earth_distance * 149.6  # millones de km
        planetas.append(info)

    casa.date = ephem.Date(AHORA.astimezone(dt.timezone.utc).replace(tzinfo=None))
    luna = ephem.Moon(casa)
    luz = luna.phase  # porcentaje iluminado
    llena = ephem.next_full_moon(casa.date)
    nueva = ephem.next_new_moon(casa.date)
    creciendo = llena < nueva
    if luz < 3:
        fase = "Luna nueva"
    elif luz > 97:
        fase = "Luna llena"
    elif 45 <= luz <= 55:
        fase = "Cuarto creciente" if creciendo else "Cuarto menguante"
    else:
        fase = "Luna creciente" if creciendo else "Luna menguante"
    a_fecha = lambda d: ephem.Date(d).datetime().replace(tzinfo=dt.timezone.utc).astimezone(TZ).date()
    return {"fase": fase, "luz": round(luz), "llena": a_fecha(llena), "nueva": a_fecha(nueva), "planetas": planetas}


# ---------------------------------------------------------------- datos del día
CLIMA_WMO = {
    0: ("Despejado", "sol"), 1: ("Mayormente despejado", "sol"), 2: ("Parcialmente nublado", "parcial"),
    3: ("Nublado", "nublado"), 45: ("Neblina", "nublado"), 48: ("Neblina", "nublado"),
    51: ("Llovizna ligera", "lluvia"), 53: ("Llovizna", "lluvia"), 55: ("Llovizna fuerte", "lluvia"),
    61: ("Lluvia ligera", "lluvia"), 63: ("Lluvia", "lluvia"), 65: ("Lluvia fuerte", "lluvia"),
    80: ("Chubascos", "lluvia"), 81: ("Chubascos", "lluvia"), 82: ("Aguaceros fuertes", "tormenta"),
    95: ("Tormenta", "tormenta"), 96: ("Tormenta con granizo", "tormenta"), 99: ("Tormenta con granizo", "tormenta"),
}


def leer_clima():
    url = ("https://api.open-meteo.com/v1/forecast"
           f"?latitude={config.LATITUD}&longitude={config.LONGITUD}"
           "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"
           f"&timezone={config.ZONA_HORARIA.replace('/', '%2F')}&forecast_days=4")
    try:
        d = descargar(url).json()["daily"]
    except Exception as err:
        AVISOS.append(f"No pude leer el clima ({type(err).__name__}).")
        return []
    dias = []
    for i, fecha in enumerate(d["time"]):
        texto, _ = CLIMA_WMO.get(d["weather_code"][i], ("Variable", "parcial"))
        dias.append({"fecha": dt.date.fromisoformat(fecha), "texto": texto,
                     "max": round(d["temperature_2m_max"][i]), "min": round(d["temperature_2m_min"][i]),
                     "lluvia": d["precipitation_probability_max"][i]})
    return dias


def leer_cambio():
    """Tipo de cambio de referencia del Banguat (servicio SOAP oficial)."""
    cuerpo = ('<?xml version="1.0" encoding="utf-8"?>'
              '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
              '<soap:Body><TipoCambioDia xmlns="http://www.banguat.gob.gt/variables/ws/" />'
              '</soap:Body></soap:Envelope>')
    try:
        r = requests.post("https://www.banguat.gob.gt/variables/ws/TipoCambio.asmx", data=cuerpo.encode(),
                          headers={**UA, "Content-Type": "text/xml; charset=utf-8",
                                   "SOAPAction": '"http://www.banguat.gob.gt/variables/ws/TipoCambioDia"'},
                          timeout=25)
        r.raise_for_status()
        raiz = ET.fromstring(r.content)
        ns = "{http://www.banguat.gob.gt/variables/ws/}"
        var = raiz.find(f".//{ns}VarDolar")
        return {"fecha": var.find(f"{ns}fecha").text, "valor": float(var.find(f"{ns}referencia").text)}
    except Exception as err:
        AVISOS.append(f"No pude leer el tipo de cambio del Banguat ({type(err).__name__}).")
        return None


def limpiar_wiki(t):
    t = re.sub(r"(?s)<ref.*?(</ref>|/>)", "", t)
    t = re.sub(r"\{\{[^{}]*\}\}", "", t)
    t = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", t)
    t = re.sub(r"'{2,}", "", t)
    t = re.sub(r"<[^>]+>", "", t)
    return re.sub(r"\s+", " ", html.unescape(t)).strip(" .") + "."


def leer_efemerides(n=3):
    """Tres hechos de esta fecha, de la Wikipedia en español (Guatemala primero)."""
    hechos = []
    try:  # 1) API de "un día como hoy"
        url = f"https://es.wikipedia.org/api/rest_v1/feed/onthisday/events/{AHORA.month:02d}/{AHORA.day:02d}"
        for ev in descargar(url).json().get("events", []):
            hechos.append((int(ev["year"]), ev["text"].strip()))
    except Exception:
        try:  # 2) La página "11 de noviembre" de Wikipedia
            pagina = f"{AHORA.day} de {MESES[AHORA.month - 1]}"
            r = descargar("https://es.wikipedia.org/w/api.php",
                          params={"action": "parse", "page": pagina, "prop": "wikitext",
                                  "format": "json", "formatversion": 2})
            texto = r.json()["parse"]["wikitext"]
            parte = re.split(r"==\s*Nacimientos\s*==", texto)[0]
            for linea in parte.splitlines():
                m = re.match(r"^\*\s*\[\[(\d{3,4})\]\]\s*(?::|—|-)\s*(.+)$", linea.strip())
                if m:
                    hechos.append((int(m.group(1)), limpiar_wiki(m.group(2))))
        except Exception as err:
            AVISOS.append(f"No pude leer las efemérides ({type(err).__name__}).")
            return []
    hechos = [(a, t) for a, t in hechos if not any(p in normal(t) for p in config.NOTA_ROJA)
              and "muere" not in normal(t) and "asesin" not in normal(t)]
    chapines = [h for h in hechos if "guatemal" in normal(h[1])]
    otros = [h for h in hechos if h not in chapines]
    random.Random(AHORA.strftime("%Y%m%d")).shuffle(otros)
    return sorted((chapines[:2] + otros)[:n])


def leer_tendencias(n=5):
    try:
        raiz = ET.fromstring(descargar(config.FEED_TRENDS).content)
    except Exception as err:
        AVISOS.append(f"No pude leer Google Trends ({type(err).__name__}).")
        return []
    ht = "{https://trends.google.com/trending/rss}"
    salida = []
    for it in raiz.iter("item"):
        noticia = it.find(f"{ht}news_item")
        salida.append({
            "tema": it.findtext("title", ""),
            "volumen": it.findtext(f"{ht}approx_traffic", ""),
            "contexto": noticia.findtext(f"{ht}news_item_title", "") if noticia is not None else "",
            "fuente": noticia.findtext(f"{ht}news_item_source", "") if noticia is not None else "",
            "url": noticia.findtext(f"{ht}news_item_url", "") if noticia is not None else "",
        })
        if len(salida) == n:
            break
    return salida


# ---------------------------------------------------------------- HTML
def articulo(n, corto=False):
    extra = " (en inglés)" if n["idioma"] == "en" else ""
    hora = f" · {hora_corta(n['fecha'])}" if n["fecha"] and n["fecha"].date() == AHORA.date() else ""
    if corto:
        return (f'<article class="breve"><p class="tipo">Cortita · {e(n["medio"])}</p>'
                f'<p><b>{e(n["titulo"])}</b> <a class="src" href="{e(n["enlace"])}">Leer →</a></p></article>')
    resumen = f"<p>{e(n['resumen'])}</p>" if n["resumen"] else ""
    return (f'<article><h3>{e(n["titulo"])}</h3>{resumen}'
            f'<a class="src" href="{e(n["enlace"])}">Leer en {e(n["medio"])}{extra} →</a>'
            f'<span class="pie" style="margin:0 0 0 6px">{e(hora[3:])}</span></article>')


def cabecera_pag(num, sec):
    return (f'<div class="pag-cab"><span class="pag-num">Página {num}</span>'
            f'<h2>{e(sec["titulo"])}</h2><span class="lema">{e(sec["lema"])}</span></div>')


def vacio(texto="Hoy no encontré notas nuevas en estas fuentes."):
    return f'<p class="hint">{e(texto)}</p>'


def pagina_noticias(num, clave, notas):
    sec = config.SECCIONES[clave]
    principales = notas[:sec["max_notas"]]
    cuerpo = "".join(articulo(n) for n in principales) or vacio()
    html_ = (f'<section class="pag" id="{clave}" style="--c:{sec["color"]}">{cabecera_pag(num, sec)}'
             f'<div class="flujo">{cuerpo}</div>')
    if sec.get("max_cortitas"):
        cortas = notas[sec["max_notas"]:sec["max_notas"] + sec["max_cortitas"]]
        if cortas:
            html_ += ('<div class="sub" style="--c:var(--c-infra)"><p class="sub-t">Cortitas</p>'
                      f'<div class="flujo">{"".join(articulo(n, True) for n in cortas)}</div></div>')
    return html_ + "</section>"


def svg_calendario():
    mes = MESES[AHORA.month - 1][:3].upper()
    return ('<svg viewBox="0 0 64 70" role="img" aria-label="Hoja de calendario: '
            f'{AHORA.day} de {MESES[AHORA.month - 1]}"><rect x="2" y="8" width="60" height="60" rx="6" '
            'fill="var(--paper)" stroke="var(--wood)" stroke-width="2"/><rect x="2" y="8" width="60" height="18" '
            'rx="6" fill="var(--c)"/><rect x="2" y="20" width="60" height="6" fill="var(--c)"/>'
            '<circle cx="18" cy="8" r="4" fill="var(--wood)"/><circle cx="46" cy="8" r="4" fill="var(--wood)"/>'
            f'<text x="32" y="21" text-anchor="middle" fill="var(--paper)" font-family="Inter, system-ui, sans-serif" '
            f'font-weight="700" font-size="10" letter-spacing="1">{mes}</text><text x="32" y="56" text-anchor="middle" '
            'fill="var(--ink)" font-family="Playfair Display, Georgia, serif" font-weight="900" font-size="26">'
            f'{AHORA.day}</text></svg>')


def pagina_datos(num, clima, cambio, efemerides, tendencias, proximas=None, cielo=None):
    partes = [bloque_cuenta(proximas)] if proximas else []
    # Clima
    if clima:
        hoy = clima[0]
        tiles = (f'<div class="dato"><b>{hoy["max"]}° / {hoy["min"]}°</b><span>Hoy · {e(hoy["texto"])}</span></div>'
                 f'<div class="dato"><b>{hoy["lluvia"]} %</b><span>Probabilidad de lluvia</span></div>')
        for d in clima[1:]:
            tiles += (f'<div class="dato"><b>{d["max"]}° / {d["min"]}°</b>'
                      f'<span>{DIAS[d["fecha"].weekday()][:3]} {d["fecha"].day} · {e(d["texto"])} · {d["lluvia"]} %</span></div>')
        partes.append('<div class="sub" style="--c:var(--c-clima)"><p class="sub-t">El clima en la zona 21</p>'
                      f'<div class="datos">{tiles}</div><p class="hint">Pronóstico de Open-Meteo. '
                      'Para alertas oficiales, Insivumeh y Conred.</p></div>')
    # Tipo de cambio
    if cambio:
        partes.append('<div class="sub" style="--c:var(--c-bolsillo)"><p class="sub-t">Tipo de cambio</p>'
                      f'<div class="datos"><div class="dato"><b>Q{cambio["valor"]:.5f}</b>'
                      f'<span>por US$1 · referencia del Banguat, {e(cambio["fecha"])}</span></div></div></div>')
    # Efemérides
    if efemerides:
        lis = "".join(f'<li><span class="anio">{a}</span><p>{e(t)}</p></li>' for a, t in efemerides)
        partes.append('<div class="sub" style="--c:var(--c-lectura)"><p class="sub-t">Un día como hoy</p>'
                      f'<div class="efem-cab">{svg_calendario()}<h3 style="font:700 21px/1.2 \'Playfair Display\',Georgia,serif;margin:0">'
                      f'Lo que pasó un {AHORA.day} de {MESES[AHORA.month - 1]}</h3></div>'
                      f'<ol class="efem">{lis}</ol><p class="hint">De la Wikipedia en español.</p></div>')
    # Tendencias
    if tendencias:
        lis = ""
        for t in tendencias:
            ctx = f'{e(t["contexto"])} ({e(t["fuente"])})' if t["contexto"] else "Sin contexto en el feed"
            enlace = f' <a class="src" href="{e(t["url"])}">→</a>' if t["url"] else ""
            lis += f'<li><b>{e(t["tema"])}</b><span>{ctx}. {e(t["volumen"])}{enlace}</span></li>'
        partes.append('<div class="sub" style="--c:var(--accent)"><p class="sub-t">Lo que más busca Guatemala en Google</p>'
                      f'<div class="tend"><div><ol>{lis}</ol></div></div></div>')
    if cielo:
        partes.append(bloque_cielo(cielo))
    partes.append(bloque_ingles())
    partes = [p for p in partes if p]
    if not partes:
        return ""
    return (f'<section class="pag" id="datos" style="--c:var(--c-clima)">'
            f'<div class="pag-cab"><span class="pag-num">Página {num}</span><h2>El día en datos</h2>'
            f'<span class="lema">Fechas, clima, cielo y más</span></div>{"".join(partes)}</section>')


def cab_pagina(num, clave, titulo, lema, color):
    return (f'<section class="pag" id="{clave}" style="--c:{color}">'
            f'<div class="pag-cab"><span class="pag-num">Página {num}</span><h2>{e(titulo)}</h2>'
            f'<span class="lema">{e(lema)}</span></div>')


def pagina_lo_tuyo(num, lo_tuyo):
    if not lo_tuyo:
        return ""
    arts = ""
    for n, gusto in lo_tuyo:
        extra = " (en inglés)" if n["idioma"] == "en" else ""
        resumen = f"<p>{e(n['resumen'])}</p>" if n["resumen"] else ""
        arts += (f'<article><p class="tipo-gusto">Por: {e(gusto)}</p><h3>{e(n["titulo"])}</h3>{resumen}'
                 f'<a class="src" href="{e(n["enlace"])}">Leer en {e(n["medio"])}{extra} →</a></article>')
    return (cab_pagina(num, "lo-tuyo", "Lo tuyo", "Noticias de lo que te gusta", "var(--c-reco)")
            + f'<div class="flujo">{arts}</div></section>')


def linea_partido(p, con_marcador=False):
    if con_marcador:
        centro = f'{e(p["goles_local"])} - {e(p["goles_visita"])}'
        hora = ""
    else:
        centro = "vs"
        hora = (hora_corta(p["fecha"]) if p["hora_ok"] else "Hora por confirmar") + " · "
        if "postpon" in normal(p["detalle"]) or "pospuesto" in normal(p["detalle"]):
            hora = "Pospuesto · "
    etiqueta = f' · <em>{e(p["motivo"])}</em>' if p["motivo"] else ""
    return (f'{hora}<strong>{e(p["local"])} {centro} {e(p["visita"])}</strong> '
            f'<span class="liga">({e(p["liga"])}){etiqueta}</span>')


def lista_por_dia(partidos, con_marcador=False):
    dias = {}
    for p in partidos:
        dias.setdefault(p["fecha"].date(), []).append(p)
    lis = ""
    for dia in sorted(dias, reverse=con_marcador):
        clase = ' class="hoy"' if dia == AHORA.date() else ""
        lineas = "<br>".join(linea_partido(p, con_marcador) for p in dias[dia])
        lis += (f'<li{clase}><span class="dia">{DIAS[dia.weekday()][:3]}<b>{dia.day}</b>'
                f'{MESES[dia.month - 1][:3]}</span><p>{lineas}</p></li>')
    return f'<ol class="agenda">{lis}</ol>'


def pagina_futbol(num, proximos, resultados, tabla, fuente_tabla, goleadores):
    partes = []
    if proximos:
        partes.append('<div class="sub"><p class="sub-t">Próximos partidos</p>'
                      f'{lista_por_dia(proximos)}<p class="hint">Hora de Guatemala. Partidos de tus equipos, '
                      'clásicos y duelos del big 6, de los próximos días.</p></div>')
    else:
        partes.append('<div class="sub"><p class="sub-t">Próximos partidos</p>'
                      f'{vacio("No hay partidos de tus equipos en los próximos días.")}</div>')
    if resultados:
        partes.append('<div class="sub"><p class="sub-t">Resultados recientes</p>'
                      f'{lista_por_dia(resultados, True)}</div>')
    if tabla:
        filas = ""
        for i, f in enumerate(tabla, 1):
            clases = []
            if i <= config.LUGARES_LIGUILLA:
                clases.append("dir")
            if config.MI_EQUIPO_TABLA and tiene(f["equipo"], config.MI_EQUIPO_TABLA):
                clases.append("yo")
            clase = f' class="{" ".join(clases)}"' if clases else ""
            dif = f"+{f['dif']}" if f["dif"] > 0 else str(f["dif"])
            filas += (f'<tr{clase}><td>{i}</td><td>{e(f["equipo"])}</td><td>{f["pj"]}</td><td>{f["g"]}</td>'
                      f'<td>{f["e"]}</td><td>{f["p"]}</td><td>{dif}</td><td>{f["pts"]}</td></tr>')
        partes.append('<div class="sub"><p class="sub-t">Tabla de la Liga Nacional</p><div class="tabla-wrap">'
                      '<table class="tabla"><thead><tr><th>#</th><th>Equipo</th><th>PJ</th><th>G</th><th>E</th>'
                      f'<th>P</th><th>Dif</th><th>Pts</th></tr></thead><tbody>{filas}</tbody>'
                      f'<caption><i style="background:var(--c-mundo)"></i>Zona de clasificación · '
                      f'Fuente: {e(fuente_tabla)}</caption></table></div></div>')
    if goleadores:
        lis = "".join(f'<li><b>{e(g["jugador"])}</b><span>{e(g["club"])} · {g["goles"]} '
                      f'gol{"es" if g["goles"] != 1 else ""}</span></li>' for g in goleadores)
        partes.append('<div class="sub"><p class="sub-t">Goleadores</p>'
                      f'<div class="tend"><div><ol>{lis}</ol></div></div>'
                      f'<p class="hint">De la Wikipedia en español ({e(torneo_actual())}).</p></div>')
    return (cab_pagina(num, "futbol", "Fútbol", "Partidos, tabla y goleadores", "var(--c-fut)")
            + "".join(partes) + "</section>")


def lista_estrenos(titulo, items):
    if not items:
        return ""
    lis = "".join(f'<li><b>{e(x["titulo"])}</b><span>{x["fecha"].day} de {MESES[x["fecha"].month - 1]}'
                  f'{" · " + e(x["resumen"]) if x["resumen"] else ""} <a class="src" href="{e(x["url"])}">→</a>'
                  f'</span></li>' for x in items)
    return f'<div><h4>{e(titulo)}</h4><ol>{lis}</ol></div>'


def pagina_entretenimiento(num, notas, pelis, series):
    sec = config.SECCIONES["entretenimiento"]
    principales = notas[:sec["max_notas"]]
    cuerpo = "".join(articulo(n) for n in principales) or vacio()
    html_ = (cab_pagina(num, "entretenimiento", sec["titulo"], sec["lema"], sec["color"])
             + f'<div class="flujo">{cuerpo}</div>')
    if pelis or series:
        html_ += ('<div class="sub" style="--c:var(--c-estrenos)"><p class="sub-t">Lo que viene</p>'
                  f'<div class="tend">{lista_estrenos("Películas en cines de Guatemala", pelis)}'
                  f'{lista_estrenos("Series nuevas", series)}</div><p class="hint">Fechas de TMDB.</p></div>')
    return html_ + "</section>"


def bloque_cuenta(proximas):
    if not proximas:
        return ""
    tiles = ""
    for nombre, fecha, dias in proximas:
        cuanto = "¡Es hoy!" if dias == 0 else "Mañana" if dias == 1 else f"{dias} días"
        tiles += (f'<div class="dato"><b>{cuanto}</b><span>{e(nombre)} · {fecha.day} de '
                  f'{MESES[fecha.month - 1]}</span></div>')
    return ('<div class="sub" style="--c:var(--c-tse)"><p class="sub-t">Cuenta regresiva</p>'
            f'<div class="datos">{tiles}</div></div>')


def bloque_cielo(cielo):
    if not cielo:
        return ""
    lis = (f'<li><b>{e(cielo["fase"])}</b><span>{cielo["luz"]} % iluminada. Próxima luna llena: '
           f'{cielo["llena"].day} de {MESES[cielo["llena"].month - 1]}.</span></li>')
    for p in cielo["planetas"]:
        if p["visible"]:
            texto = (f'Se ve de {hora_corta(p["desde"])} a {hora_corta(p["hasta"])}, '
                     f'y mejor a las {hora_corta(p["hora_mejor"])}, hacia {p["rumbo"]}.')
        else:
            texto = "No se ve esta noche."
        if p.get("distancia"):
            texto += f' Está a {p["distancia"]:.0f} millones de km de la Tierra.'
        lis += f'<li><b>{e(p["nombre"])}</b><span>{e(texto)}</span></li>'
    return ('<div class="sub" style="--c:var(--c-ovni)"><p class="sub-t">El cielo de esta noche</p>'
            f'<div class="tend"><div><ol class="cielo">{lis}</ol></div></div>'
            '<p class="hint">Calculado para la zona 21, con el cielo despejado. Los planetas se ven como '
            'estrellas que no titilan.</p></div>')


def bloque_ingles():
    if not config.PALABRAS_INGLES:
        return ""
    palabra, significado, ejemplo = config.PALABRAS_INGLES[AHORA.timetuple().tm_yday % len(config.PALABRAS_INGLES)]
    return ('<div class="sub" style="--c:var(--c-cursos)"><p class="sub-t">Palabra en inglés</p>'
            f'<div class="relleno"><p class="tipo">English</p><h4>{e(palabra)}</h4>'
            f'<p>{e(significado)}.</p><p class="hint" style="margin-top:6px"><i>“{e(ejemplo)}”</i></p></div></div>')


def armar_html(noticias, alertas, clima, cambio, efemerides, tendencias,
               futbol=None, estrenos=([], []), proximas=None, cielo=None):
    css = open(os.path.join(AQUI, "estilo.css"), encoding="utf-8").read()
    dia_semana = AHORA.weekday()
    edicion = "Edición dominical" if dia_semana == 6 else "Edición de fin de semana" if dia_semana == 5 else "Edición diaria"
    frase = config.FRASES[AHORA.timetuple().tm_yday % len(config.FRASES)]

    bloques = []
    if alertas:
        items = "".join(f'<p><strong>{e(n["titulo"])}</strong> <a class="src" style="--c:var(--alert-bd)" '
                        f'href="{e(n["enlace"])}">{e(n["medio"])} →</a></p>' for n in alertas)
        bloques.append(f'<div class="alert"><h2>Ojo con esto</h2>{items}</div>')
    cumple = [nombre for nombre, d, m in config.CUMPLEANOS if d == AHORA.day and m == AHORA.month]
    if cumple:
        bloques.append(f'<div class="alert" style="--alert-bd:var(--c-buenas)"><h2>Hoy cumple años</h2>'
                       f'<p>{e(", ".join(cumple))}. ¡No te olvidés de felicitar!</p></div>')

    cortos = {"guatemala": "Nacionales", "analisis": "Para leer con calma", "mundo": "Internacionales",
              "deportes": "Deportes", "ciencia": "Ciencia y tecnología", "entretenimiento": "Entretenimiento",
              "eventos": "Eventos"}
    paginas, indice, num = [], [], 1

    def agregar(html_pag, clave, corto):
        nonlocal num
        if html_pag:
            paginas.append(html_pag)
            indice.append(f'<a href="#{clave}"><b>{num}</b>{corto}</a>')
            num += 1

    agregar(pagina_lo_tuyo(num, noticias.get("lo_tuyo", [])), "lo-tuyo", "Lo tuyo")
    for clave in config.ORDEN_PAGINAS:
        if clave not in config.SECCIONES:
            continue
        if clave == "entretenimiento":
            agregar(pagina_entretenimiento(num, noticias.get(clave, []), *estrenos), clave, cortos[clave])
        else:
            agregar(pagina_noticias(num, clave, noticias.get(clave, [])), clave,
                    cortos.get(clave, config.SECCIONES[clave]["titulo"]))
        if clave == "deportes" and futbol:
            agregar(pagina_futbol(num, *futbol), "futbol", "Fútbol")
    datos = pagina_datos(num, clima, cambio, efemerides, tendencias, proximas, cielo)
    if datos:
        paginas.append(datos)
        indice.append(f'<a href="#datos"><b>{num}</b>El día en datos</a>')
    indice.append('<a href="archivo/">Archivo</a>')

    medios = sorted({f["medio"] for s in config.SECCIONES.values() for f in s["fuentes"]})
    avisos = "".join(f"<li>{e(a)}</li>" for a in AVISOS)
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Diario de Pedro {AHORA:%Y-%m-%d}</title>
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700;900&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&family=Inter:wght@500;700&display=swap" rel="stylesheet">
<style>
{css}
.pie{{font:500 12px Inter,system-ui,sans-serif;color:var(--muted)}}
.flujo>article{{break-inside:avoid;-webkit-column-break-inside:avoid}}
.tipo-gusto{{font:700 10px Inter,system-ui,sans-serif;text-transform:uppercase;letter-spacing:.12em;color:var(--c);margin:0 0 2px}}
ol.agenda .liga{{font:500 12px Inter,system-ui,sans-serif;color:var(--muted)}}
ol.agenda .liga em{{color:var(--c);font-style:normal;font-weight:700}}
ol.cielo{{list-style:none;padding-left:0}}
.cierre{{text-align:center;font:italic 600 20px/1.4 "Source Serif 4",Georgia,serif;margin:28px 0 8px;padding:18px 0;border-top:3px double var(--wood);border-bottom:3px double var(--wood)}}
</style></head><body>
<div class="wrap">
<header>
  <div class="meta"><span>Ciudad de Guatemala</span><span>{e(fecha_larga(AHORA))}</span><span>{edicion}</span></div>
  <h1 class="mast">El Diario de Pedro</h1>
  <p class="tag">Lo que importa hoy, sin el ruido de las redes</p>
</header>
<div class="frase"><blockquote>“{e(frase)}”</blockquote><cite>Refrán popular</cite></div>
{"".join(bloques)}
<nav class="indice-pag" aria-label="Páginas de hoy">{"".join(indice)}</nav>
<main class="paginas">
{"".join(paginas)}
</main>
<p class="cierre">{e(config.CIERRE)}</p>
<footer>
  <h2>Cómo se hizo</h2>
  <p>Armado automáticamente a las {hora_corta(AHORA)}, sin inteligencia artificial. Los resúmenes son las primeras líneas que publica cada medio. Las notas de nota roja se esconden con una lista de palabras (en config.py).</p>
  <p>Fuentes: {e(", ".join(medios))}, ESPN, Open-Meteo, Banguat, Wikipedia, Google Trends{", TMDB" if estrenos[0] or estrenos[1] else ""}. El cielo se calcula con la librería ephem.</p>
  {f"<h2>Avisos de hoy</h2><ul>{avisos}</ul>" if avisos else ""}
</footer>
</div></body></html>
"""


def actualizar_archivo():
    carpeta = os.path.join(SALIDA, "archivo")
    dias = sorted((f[:-5] for f in os.listdir(carpeta) if re.match(r"\d{4}-\d{2}-\d{2}\.html$", f)), reverse=True)
    lis = "".join(f'<li><a href="{d}.html">{e(fecha_larga(dt.date.fromisoformat(d)))}</a></li>' for d in dias)
    with open(os.path.join(carpeta, "index.html"), "w", encoding="utf-8") as f:
        f.write('<!doctype html><html lang="es"><head><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width,initial-scale=1"><title>Archivo del Diario de Pedro</title>'
                '<style>body{font:17px/1.6 Georgia,serif;max-width:40rem;margin:0 auto;padding:24px 16px;'
                'background:#fffdf8;color:#1b1a17}a{color:#1f5fa8}@media (prefers-color-scheme:dark){body{background:#1c1b19;'
                'color:#ece8df}a{color:#7fb0ec}}</style></head><body><h1>Archivo del Diario</h1>'
                f'<p><a href="../">← Diario de hoy</a></p><ul>{lis}</ul></body></html>')


def main():
    noticias, alertas = juntar_noticias()
    proximos, resultados = leer_partidos()
    tabla, fuente_tabla = leer_tabla()
    futbol = (proximos, resultados, tabla, fuente_tabla, leer_goleadores())
    pagina = armar_html(noticias, alertas, leer_clima(), leer_cambio(), leer_efemerides(), leer_tendencias(),
                        futbol=futbol, estrenos=leer_estrenos(), proximas=cuenta_regresiva(), cielo=leer_cielo())
    os.makedirs(os.path.join(SALIDA, "archivo"), exist_ok=True)
    for ruta in (os.path.join(SALIDA, "index.html"),
                 os.path.join(SALIDA, "archivo", f"{AHORA:%Y-%m-%d}.html")):
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(pagina.replace('href="archivo/"', 'href="./"') if "archivo" in os.path.dirname(ruta) else pagina)
    actualizar_archivo()
    total = sum(len(v) for v in noticias.values())  # incluye "Lo tuyo"
    print(f"Listo: {total} notas, {len(alertas)} alertas, {len(AVISOS)} avisos.")
    for a in AVISOS:
        print("  -", a)


if __name__ == "__main__":
    sys.exit(main())
