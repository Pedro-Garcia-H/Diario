# -*- coding: utf-8 -*-
"""
CONFIGURACIÓN DEL DIARIO DE PEDRO
=================================
Aquí cambiás todo sin tocar el programa: medios, palabras que suben o bajan
una noticia, frases, cumpleaños y tu ubicación.

Reglas rápidas de Python para editar sin romper nada:
- Los textos van entre comillas: "así".
- Cada elemento de una lista termina en coma.
- Lo que empieza con # es un comentario y el programa lo ignora.
"""

ZONA_HORARIA = "America/Guatemala"

# Ubicación para el clima (colonia Nimajuyú, zona 21).
LATITUD = 14.574
LONGITUD = -90.550

# Cuántas horas hacia atrás buscar noticias.
HORAS_ATRAS = 36

# ---------------------------------------------------------------------------
# MEDIOS (feeds RSS). Cada sección del diario junta las notas de sus fuentes.
# "peso": de 1 a 3; más alto = ese medio pesa más al ordenar.
# "excluir_categorias": categorías del feed que no querés en esa sección.
# Las notas de deportes de los medios nacionales se pasan solas a Deportes.
# ---------------------------------------------------------------------------
SECCIONES = {
    "guatemala": {
        "titulo": "Noticias nacionales",
        "lema": "Lo más importante del país",
        "color": "var(--c-gt)",
        "max_notas": 5,
        "max_cortitas": 6,   # las siguientes van como "Cortitas"
        "fuentes": [
            {"medio": "Prensa Libre", "url": "https://www.prensalibre.com/feed/", "peso": 3,
             "excluir_categorias": ["Escenario", "Vida", "Sucesos", "Internacional", "Hemeroteca"]},
            {"medio": "La Hora", "url": "https://lahora.gt/feed/", "peso": 2,
             "excluir_categorias": ["Opinión", "Internacionales"]},
            {"medio": "República", "url": "https://republica.com/feed", "peso": 2,
             "excluir_categorias": ["Opinión", "Columnas"]},
            {"medio": "Publinews", "url": "https://www.publinews.gt/arc/outboundfeeds/rss/?outputType=xml", "peso": 2},
            {"medio": "Infobae", "url": "https://www.infobae.com/arc/outboundfeeds/rss/category/guatemala/", "peso": 1},
        ],
    },
    "analisis": {
        "titulo": "Para leer con calma",
        "lema": "Reportajes e investigación",
        "color": "var(--c-entender)",
        "max_notas": 3,
        "fuentes": [
            {"medio": "Plaza Pública", "url": "https://www.plazapublica.com.gt/feed/", "peso": 2,
             "excluir_categorias": ["Opinión"]},
            {"medio": "Agencia Ocote", "url": "https://www.agenciaocote.com/feed/", "peso": 2},
        ],
        "horas_atras": 96,  # publican poco, así que miramos más días
    },
    "mundo": {
        "titulo": "Internacionales",
        "lema": "Lo que pasa afuera",
        "color": "var(--c-mundo)",
        "max_notas": 5,
        "fuentes": [
            {"medio": "BBC Mundo", "url": "https://feeds.bbci.co.uk/mundo/rss.xml", "peso": 3},
            {"medio": "DW", "url": "https://rss.dw.com/xml/rss-sp-all", "peso": 2},
        ],
    },
    "deportes": {
        "titulo": "Deportes",
        "lema": "Nacional e internacional",
        "color": "var(--c-fut)",
        "max_notas": 7,
        "fuentes": [
            {"medio": "Guatefutbol", "url": "https://guatefutbol.com/feed/", "peso": 3},
            {"medio": "Emisoras Unidas", "url": "https://emisorasunidas.com/feed/", "peso": 2,
             "solo_categorias": ["Deportes"]},
            {"medio": "Infobae Deportes", "url": "https://www.infobae.com/arc/outboundfeeds/rss/category/deportes/", "peso": 1},
            {"medio": "Marca", "url": "https://www.marca.com/rss/googlenews/portada.xml", "peso": 1},
        ],
    },
    "ciencia": {
        "titulo": "Ciencia y tecnología",
        "lema": "El espacio, descubrimientos y tecnología",
        "color": "var(--c-cien)",
        "max_notas": 6,
        "fuentes": [
            {"medio": "NASA", "url": "https://www.nasa.gov/news-release/feed/", "peso": 2, "idioma": "en"},
            {"medio": "ScienceDaily", "url": "https://www.sciencedaily.com/rss/space_time.xml", "peso": 2, "idioma": "en"},
            {"medio": "Xataka", "url": "https://www.xataka.com/index.xml", "peso": 2},
        ],
        "horas_atras": 72,
    },
}

# Google Trends de Guatemala (lo más buscado).
FEED_TRENDS = "https://trends.google.com/trending/rss?geo=GT"

# ---------------------------------------------------------------------------
# PALABRAS QUE SUBEN UNA NOTICIA (más puntos = más arriba).
# Escribilas en minúsculas y sin tildes; el programa compara así.
# ---------------------------------------------------------------------------
PRIORIDAD = {
    # Fútbol (tu orden: Cremas, Rojos, Barça, Madrid, Selección y clásicos)
    "comunicaciones": 10, "cremas": 10, "crema": 6,
    "municipal": 6, "rojos": 4,
    "barcelona": 6, "barca": 6, "real madrid": 6, "mbappe": 3, "lamine": 3,
    "seleccion de guatemala": 8, "seleccion nacional": 6, "la azul y blanco": 6, "bicolor": 6,
    "liga de naciones": 5, "copa oro": 5, "concacaf": 3, "eliminatoria": 4,
    "clasico": 4, "champions": 4, "liga nacional": 3, "apertura": 2,
    # Temas que te interesan
    "tse": 4, "elecciones 2027": 5, "tribunal supremo electoral": 4,
    "corrupcion": 3, "congreso": 2, "presupuesto": 2,
    "doroteo guamuch": 6, "mario camposeco": 6, "el trebol": 4, "estadio": 3,
    "aerometro": 5, "metroriel": 5, "carretera": 2, "puente": 2, "infraestructura": 3,
    "sismo": 3, "insivumeh": 3, "conred": 3,
    "marte": 6, "mars": 6, "nasa": 3, "artemis": 3, "telescopio": 2, "asteroide": 2,
    "ovni": 4, "uap": 4, "fenomenos anomalos": 4,
    "inteligencia artificial": 2, "ia ": 1,
    "zona 21": 8, "nimajuyu": 10, "villa nueva": 2,
    "curso libre": 5, "cursos libres": 5, "intecap": 4, "usac": 2, "inscripciones": 2,
}

# Palabras que esconden una nota (nota roja y morbo). Si el titular o el
# resumen tiene alguna, la nota no sale en el diario.
NOTA_ROJA = [
    "ataque armado", "asesinad", "cadaver", "balacera", "baleado", "balean",
    "sicari", "decapitad", "descuartizad", "ultimad", "fallece tras ataque",
    "hallan muerto", "hallan sin vida", "localizan sin vida", "osamenta",
    "violacion", "abuso sexual", "feminicidio", "linchad", "masacre",
    "accidente de transito deja", "mueren en accidente", "pierde la vida",
]

# Palabras que mandan una nota al recuadro "Ojo con esto" (arriba del diario).
ALERTAS = [
    "corte de agua", "cortes de agua", "sin agua", "empagua",
    "corte de energia", "suspension de energia", "corte de luz", "eegsa",
    "frente frio", "alerta roja", "alerta naranja", "alerta amarilla",
    "ceniza", "erupcion", "conred declara", "lluvias fuertes",
    "convocatoria del tse", "tse convoca", "juntas electorales",
]
# Para que una alerta de agua o luz salga, además debe mencionar alguna de
# estas zonas. Las alertas del clima salen siempre.
ZONAS_CERCANAS = ["zona 21", "nimajuyu", "zona 12", "zona 7", "villa nueva", "todo el pais",
                  "ciudad de guatemala", "area metropolitana"]

# ---------------------------------------------------------------------------
# FRASE DEL DÍA: refranes populares. Cambia sola cada día.
# Podés agregar los tuyos.
# ---------------------------------------------------------------------------
FRASES = [
    "Poco a poco se anda lejos.",
    "El que madruga, Dios le ayuda.",
    "Más vale tarde que nunca.",
    "No hay mal que por bien no venga.",
    "Al mal tiempo, buena cara.",
    "El que busca, encuentra.",
    "Camarón que se duerme se lo lleva la corriente.",
    "De tal palo, tal astilla.",
    "En boca cerrada no entran moscas.",
    "Más vale prevenir que lamentar.",
    "No dejes para mañana lo que puedas hacer hoy.",
    "A caballo regalado no se le ve el colmillo.",
    "El que mucho abarca, poco aprieta.",
    "Despacio se llega lejos.",
    "Dime con quién andas y te diré quién eres.",
    "Haz el bien sin mirar a quién.",
    "La práctica hace al maestro.",
    "Del dicho al hecho hay mucho trecho.",
    "Querer es poder.",
    "Gota a gota, el agua horada la piedra.",
    "Hoy por ti, mañana por mí.",
    "No hay peor ciego que el que no quiere ver.",
    "Árbol que nace torcido, jamás su tronco endereza.",
    "Agua que no has de beber, déjala correr.",
    "El que con lobos anda, a aullar se enseña.",
    "Al que no quiere caldo, se le dan dos tazas.",
    "Más vale pájaro en mano que cien volando.",
    "Cuando el río suena, piedras trae.",
    "No por mucho madrugar amanece más temprano.",
    "Ojos que no ven, corazón que no siente.",
    "Quien siembra vientos, recoge tempestades.",
    "A buen entendedor, pocas palabras.",
    "El tiempo es oro.",
    "Lo que bien se aprende, nunca se olvida.",
    "Una golondrina no hace verano.",
    "Zapatero, a tus zapatos.",
]

# ---------------------------------------------------------------------------
# CUMPLEAÑOS: ("Nombre", día, mes). Ojo: si publicás el diario en GitHub
# Pages gratis, la página es pública. Mejor poné solo el primer nombre o un
# apodo.
# ---------------------------------------------------------------------------
CUMPLEANOS = [
    # ("Ronald", 14, 3),
]
