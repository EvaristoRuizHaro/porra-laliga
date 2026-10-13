# Pronósticos de Champions League.
#
# El modelo de LaLiga no sirve aquí: solo conoce equipos españoles. Para la Champions usamos:
#   1. Elo europeo: el de ClubElo (cubre todos los clubes de Europa) o, si está caído, el que
#      calculamos nosotros con las ligas y los cruces de Champions (elo_europa.py).
#      Del Elo sacamos los goles esperados: buscamos λ_local y λ_visitante tales que la
#      "expectativa" del partido (P(gana local) + ½·P(empate)) sea la que dice el Elo.
#   2. Cuotas de The Odds API, que pesan más que en LaLiga (el Elo solo es más flojo que
#      nuestro modelo de LaLiga, que también mira tiros, goles, defensa...).
# Si no hay Elo ni cuotas de un equipo, se usa un pronóstico neutro y se avisa.
import difflib
import math
from datetime import datetime

from modelo import CONFIG, matriz, predecir, probabilidades_1x2
from nombres import _normalizar

CONFIG_CHAMPIONS = {
    "ventaja_casa_elo": 70,     # puntos Elo que vale jugar en casa en Europa
    "goles_equipo": 1.6,        # goles por equipo en un partido igualado (ajustado con elo_europa.py)
    "peso_mercado": 0.9,        # 0 = solo Elo, 1 = solo cuotas
    "elo_desconocido": 1600,    # Elo de un equipo que no encontramos (los más flojos de la fase liga)
}

# football-data.org / The Odds API escriben algunos equipos muy distinto que ClubElo.
# Forma normalizada (minúsculas, sin tildes) -> nombre en ClubElo
ALIAS_ELO = {
    "paris saint germain": "Paris SG", "psg": "Paris SG",
    "manchester city": "Man City", "manchester united": "Man United",
    "fc bayern munchen": "Bayern", "bayern munich": "Bayern",
    "borussia dortmund": "Dortmund", "bayer 04 leverkusen": "Leverkusen",
    "bayer leverkusen": "Leverkusen", "eintracht frankfurt": "Frankfurt",
    "rb leipzig": "RB Leipzig", "vfb stuttgart": "Stuttgart",
    "fc internazionale milano": "Inter", "inter milan": "Inter", "ac milan": "Milan",
    "sport lisboa e benfica": "Benfica", "sporting clube de portugal": "Sporting",
    "sporting cp": "Sporting", "sporting lisbon": "Sporting", "sc braga": "Braga",
    "club brugge kv": "Brugge", "club brugge": "Brugge",
    "royale union saint gilloise": "Union SG", "union saint gilloise": "Union SG",
    "fc red bull salzburg": "Salzburg", "red bull salzburg": "Salzburg",
    "olympiacos": "Olympiakos", "olympiacos fc": "Olympiakos",
    "olympiakos piraeus": "Olympiakos",
    "fc kobenhavn": "FC Kobenhavn", "fc copenhagen": "FC Kobenhavn",
    "crvena zvezda": "Crvena Zvezda", "red star belgrade": "Crvena Zvezda",
    "slavia praha": "Slavia Praha", "slavia prague": "Slavia Praha",
    "sparta praha": "Sparta Praha", "sparta prague": "Sparta Praha",
    "gnk dinamo zagreb": "Dinamo Zagreb", "fk bod glimt": "Bodoe/Glimt",
    "bodo glimt": "Bodoe/Glimt", "fk bodo glimt": "Bodoe/Glimt",
    "shakhtar donetsk": "Shakhtar", "fc shakhtar donetsk": "Shakhtar",
    "bsc young boys": "Young Boys",
    "club atletico de madrid": "Atletico", "atletico madrid": "Atletico",
    "athletic club": "Bilbao", "athletic bilbao": "Bilbao",
    "real sociedad de futbol": "Sociedad", "real sociedad": "Sociedad",
    "real betis balompie": "Betis", "real betis": "Betis",
    "ath madrid": "Atletico", "ath bilbao": "Bilbao", "sociedad": "Sociedad",
}

# Palabras que no distinguen equipos
_RELLENO = {"fc", "cf", "ac", "as", "sc", "afc", "sk", "fk", "nk", "gnk", "bsc", "kv", "ssc",
            "club", "de", "e", "sport", "1", "04", "1899", "1909", "1913"}


def _tokens(texto):
    return [t for t in _normalizar(texto).split() if t not in _RELLENO] or _normalizar(texto).split()


def parecido(a, b):
    """0..1: cuánto se parecen dos nombres de equipo ('Bayern Munich' vs 'FC Bayern München')."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    # Palabras en común: iguales, una empieza por la otra ('inter'/'internazionale')
    # o casi iguales ('munich'/'munchen'); 'celta'/'celtic' NO cuenta
    def igual(x, y):
        if x == y:
            return True
        if min(len(x), len(y)) >= 4 and (x.startswith(y) or y.startswith(x)):
            return True
        return difflib.SequenceMatcher(None, x, y).ratio() >= 0.75
    comunes = sum(any(igual(x, y) for y in tb) for x in ta)
    por_palabras = comunes / max(len(ta), len(tb))
    por_letras = difflib.SequenceMatcher(None, " ".join(ta), " ".join(tb)).ratio()
    return max(por_palabras * 0.95, por_letras)


def _nombres(equipo):
    """Todas las formas en que la API escribe un equipo (nombre, corto, siglas)."""
    return [x for x in (equipo.get("name"), equipo.get("shortName")) if x]


def buscar_elo(equipo, elos):
    """Elo de un equipo de football-data.org en la tabla de ClubElo (o None)."""
    if not elos:
        return None
    normal = {_normalizar(c): c for c in elos}
    for forma in _nombres(equipo):
        n = _normalizar(forma)
        if n in ALIAS_ELO and ALIAS_ELO[n] in elos:
            return elos[ALIAS_ELO[n]]
        if n in normal:
            return elos[normal[n]]
        if " ".join(_tokens(forma)) in normal:
            return elos[normal[" ".join(_tokens(forma))]]
    mejor, nota = None, 0.0
    for club in elos:
        s = max(parecido(forma, club) for forma in _nombres(equipo))
        if s > nota:
            mejor, nota = club, s
    return elos[mejor] if nota >= 0.85 else None


def emparejar_cuotas(partidos, eventos, max_horas=3):
    """Asigna a cada partido de football-data.org sus cuotas de The Odds API.
    Se emparejan por hora de inicio (±max_horas) y por parecido de los dos nombres."""
    candidatos = []
    for i, p in enumerate(partidos):
        inicio = datetime.fromisoformat(p["utcDate"].replace("Z", "+00:00"))
        for j, ev in enumerate(eventos):
            if abs((ev["inicio"] - inicio).total_seconds()) > max_horas * 3600:
                continue
            s = (max(parecido(n, ev["local"]) for n in _nombres(p["homeTeam"]))
                 + max(parecido(n, ev["visitante"]) for n in _nombres(p["awayTeam"])))
            if s >= 1.2:
                candidatos.append((s, i, j))
    res, usados_p, usados_e = {}, set(), set()
    for s, i, j in sorted(candidatos, reverse=True):   # primero las parejas más claras
        if i not in usados_p and j not in usados_e:
            res[partidos[i]["id"]] = eventos[j]["cuotas"]
            usados_p.add(i)
            usados_e.add(j)
    return res


def lambdas_elo(elo_local, elo_visit, neutral=False, cfg=None):
    """Goles esperados (λ_local, λ_visitante) que encajan con la diferencia de Elo."""
    cfg = {**CONFIG_CHAMPIONS, **(cfg or {})}
    dif = elo_local - elo_visit + (0 if neutral else cfg["ventaja_casa_elo"])
    objetivo = 1 / (1 + 10 ** (-dif / 400))          # lo que espera el Elo (1 = gana, ½ = empate)
    g = cfg["goles_equipo"]

    def expectativa(d):
        p1, px, _ = probabilidades_1x2(matriz(g * math.exp(d / 2), g * math.exp(-d / 2),
                                              CONFIG["rho"]))
        return p1 + px / 2

    bajo, alto = -4.0, 4.0                            # búsqueda binaria de d = log(λl/λv)
    for _ in range(50):
        medio = (bajo + alto) / 2
        if expectativa(medio) < objetivo:
            bajo = medio
        else:
            alto = medio
    d = (bajo + alto) / 2
    return g * math.exp(d / 2), g * math.exp(-d / 2)


class ModeloElo:
    """Se comporta como modelo.Modelo (tiene .lambdas) para reutilizar predecir()."""

    def __init__(self, elo_local, elo_visit, neutral):
        self.elo_local, self.elo_visit, self.neutral = elo_local, elo_visit, neutral

    def lambdas(self, local, visitante):
        return lambdas_elo(self.elo_local, self.elo_visit, self.neutral)


def predecir_partido(partido, buscar, cuotas=None):
    """Pronóstico de un partido de Champions. buscar(equipo) -> Elo o None.
    Devuelve (pred, elo_local, elo_visitante), con los Elo a None si no se encontraron."""
    el, ev = buscar(partido["homeTeam"]), buscar(partido["awayTeam"])
    neutral = partido.get("stage") == "FINAL"          # la final es en campo neutral
    desconocido = CONFIG_CHAMPIONS["elo_desconocido"]
    modelo = ModeloElo(el or desconocido, ev or desconocido, neutral)
    peso = CONFIG_CHAMPIONS["peso_mercado"]
    if cuotas and (el is None or ev is None):
        peso = 1.0                                     # sin Elo fiable, mandan las casas
    pred = predecir(modelo, partido["local"], partido["visitante"], cuotas=cuotas,
                    cfg={"peso_mercado": peso})
    return pred, el, ev
