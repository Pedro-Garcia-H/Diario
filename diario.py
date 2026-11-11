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
    for clave, sec in config.SECCIONES.items():
        horas = sec.get("horas_atras", config.HORAS_ATRAS)
        crudas[clave] = [n for f in sec["fuentes"] for n in leer_feed(f, horas)]

    todas = [n for lista in crudas.values() for n in lista]
    alertas = buscar_alertas(todas)

    # Las notas deportivas que llegan por los medios nacionales pasan a Deportes.
    deportivas = [n for n in crudas.get("guatemala", []) if es_deporte(n)]
    crudas["guatemala"] = [n for n in crudas.get("guatemala", []) if not es_deporte(n)]
    crudas.setdefault("deportes", []).extend(deportivas)

    vistas, finales = list(alertas), {}  # lo que ya sale en "Ojo con esto" no se repite
    for clave, lista in crudas.items():
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


def pagina_datos(num, clima, cambio, efemerides, tendencias):
    partes = []
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
    if not partes:
        return ""
    return (f'<section class="pag" id="datos" style="--c:var(--c-clima)">'
            f'<div class="pag-cab"><span class="pag-num">Página {num}</span><h2>El día en datos</h2>'
            f'<span class="lema">Clima, cambio, efemérides y búsquedas</span></div>{"".join(partes)}</section>')


def armar_html(noticias, alertas, clima, cambio, efemerides, tendencias):
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

    orden = [("guatemala", "Nacionales"), ("analisis", "Para leer con calma"), ("mundo", "Internacionales"),
             ("deportes", "Deportes"), ("ciencia", "Ciencia y tecnología")]
    paginas, indice, num = [], [], 1
    for clave, corto in orden:
        if clave not in config.SECCIONES:
            continue
        paginas.append(pagina_noticias(num, clave, noticias.get(clave, [])))
        indice.append(f'<a href="#{clave}"><b>{num}</b>{corto}</a>')
        num += 1
    datos = pagina_datos(num, clima, cambio, efemerides, tendencias)
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
<footer>
  <h2>Cómo se hizo</h2>
  <p>Armado automáticamente a las {hora_corta(AHORA)}, sin inteligencia artificial. Los resúmenes son las primeras líneas que publica cada medio. Las notas de nota roja se esconden con una lista de palabras (en config.py).</p>
  <p>Fuentes: {e(", ".join(medios))}, Open-Meteo, Banguat, Wikipedia y Google Trends.</p>
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
    pagina = armar_html(noticias, alertas, leer_clima(), leer_cambio(), leer_efemerides(), leer_tendencias())
    os.makedirs(os.path.join(SALIDA, "archivo"), exist_ok=True)
    for ruta in (os.path.join(SALIDA, "index.html"),
                 os.path.join(SALIDA, "archivo", f"{AHORA:%Y-%m-%d}.html")):
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(pagina.replace('href="archivo/"', 'href="./"') if "archivo" in os.path.dirname(ruta) else pagina)
    actualizar_archivo()
    total = sum(len(v) for v in noticias.values())
    print(f"Listo: {total} notas, {len(alertas)} alertas, {len(AVISOS)} avisos.")
    for a in AVISOS:
        print("  -", a)


if __name__ == "__main__":
    sys.exit(main())
