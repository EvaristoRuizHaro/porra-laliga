# Cada fuente escribe los equipos a su manera ("Barça", "FC Barcelona", "Barcelona"...).
# Aquí los traducimos todos a un único nombre "canónico" (el de football-data.co.uk)
# para poder cruzar resultados, tiros, cuotas y Elo del mismo equipo.
import difflib
import re
import unicodedata

# nombre canónico -> otras formas de escribirlo (en minúsculas y sin tildes)
ALIAS = {
    "Alaves": ["deportivo alaves"],
    "Albacete": ["albacete balompie"],
    "Almeria": ["ud almeria"],
    "Ath Bilbao": ["athletic", "athletic club", "athletic bilbao", "bilbao"],
    "Ath Madrid": ["atletico", "atleti", "atletico madrid", "atletico de madrid",
                   "club atletico de madrid"],
    "Barcelona": ["barca", "fc barcelona"],
    "Betis": ["real betis", "real betis balompie"],
    "Burgos": ["burgos cf"],
    "Cadiz": ["cadiz cf"],
    "Castellon": ["cd castellon"],
    "Celta": ["celta vigo", "celta de vigo", "rc celta", "rc celta de vigo"],
    "Cordoba": ["cordoba cf"],
    "Eibar": ["sd eibar"],
    "Elche": ["elche cf"],
    "Espanol": ["espanyol", "rcd espanyol", "rcd espanyol de barcelona"],
    "Getafe": ["getafe cf"],
    "Girona": ["girona fc"],
    "Granada": ["granada cf"],
    "Huesca": ["sd huesca"],
    "La Coruna": ["deportivo", "depor", "deportivo la coruna", "rc deportivo",
                  "rc deportivo la coruna"],
    "Las Palmas": ["ud las palmas"],
    "Leganes": ["cd leganes"],
    "Levante": ["levante ud"],
    "Malaga": ["malaga cf"],
    "Mallorca": ["rcd mallorca"],
    "Mirandes": ["cd mirandes"],
    "Osasuna": ["ca osasuna"],
    "Oviedo": ["real oviedo"],
    "Real Madrid": ["real madrid cf"],
    "Santander": ["racing", "racing santander", "racing club", "real racing club",
                  "real racing club de santander"],
    "Sevilla": ["sevilla fc"],
    "Sociedad": ["real sociedad", "real sociedad de futbol"],
    "Sp Gijon": ["sporting", "sporting gijon", "real sporting", "real sporting de gijon"],
    "Tenerife": ["cd tenerife"],
    "Valencia": ["valencia cf"],
    "Valladolid": ["real valladolid", "real valladolid cf"],
    "Vallecano": ["rayo", "rayo vallecano", "rayo vallecano de madrid"],
    "Villarreal": ["villarreal cf"],
    "Zaragoza": ["real zaragoza"],
}

# Palabras que no ayudan a distinguir equipos (siglas de club, "de"...)
_RELLENO = {"fc", "cf", "ud", "cd", "rc", "rcd", "sd", "ca", "club", "de", "sad"}


def _normalizar(texto):
    """'Atlético de Madrid' -> 'atletico de madrid'."""
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", texto.lower()).strip()


def _sin_relleno(texto):
    return " ".join(p for p in texto.split() if p not in _RELLENO)


_TABLA = {}
for _canon, _otros in ALIAS.items():
    for _forma in [_canon, *_otros]:
        _TABLA[_normalizar(_forma)] = _canon
        _TABLA.setdefault(_sin_relleno(_normalizar(_forma)), _canon)

_avisados = set()


def canonico(nombre, avisar=True, difuso=True):
    """Devuelve el nombre canónico de un equipo, venga de la fuente que venga."""
    n = _normalizar(nombre)
    if n in _TABLA:
        return _TABLA[n]
    if _sin_relleno(n) in _TABLA:
        return _TABLA[_sin_relleno(n)]
    # Último recurso: el nombre conocido más parecido
    parecido = difuso and difflib.get_close_matches(_sin_relleno(n), list(_TABLA), n=1, cutoff=0.8)
    if parecido:
        return _TABLA[parecido[0]]
    if avisar and nombre not in _avisados:
        _avisados.add(nombre)
        print(f"⚠️  Equipo desconocido: '{nombre}' (añádelo a ALIAS en nombres.py)")
    return nombre
