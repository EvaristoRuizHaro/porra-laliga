# Elo propio de los clubes de Europa (para la Champions cuando ClubElo está caído).
#
# Idea: el Elo de cada equipo sale de sus partidos de liga, y las ligas se comparan entre sí
# gracias a los partidos entre ligas:
#   - Ligas (football-data.co.uk, 5 temporadas): Inglaterra, España, Italia, Alemania, Francia
#     (Primera y Segunda), Países Bajos, Portugal, Bélgica, Turquía, Grecia, Escocia, Austria,
#     Suiza, Dinamarca, Noruega, Suecia, Polonia, Rumanía...
#   - Champions (football-data.org): cuando un equipo inglés le gana a uno portugués, pasan
#     puntos de Portugal a Inglaterra. Así se ajusta cuánto vale cada liga.
#   - Ascensos y descensos conectan Primera y Segunda de cada país.
# Cada liga empieza con un Elo inicial aproximado (lo que vale la liga en Europa) y los
# resultados lo corrigen. En verano cada equipo se acerca a la media de SU liga, pero la
# media de la liga se mantiene: lo aprendido en Europa no se pierde.
import csv
import io
from datetime import date
from functools import lru_cache

import datos
import elo as elo_calc
from champions import _tokens, parecido
from modelo import inicio_temporada
from nombres import _normalizar, canonico

TEMPORADAS = 5

# Ligas con el formato de siempre (mmz4281/2526/E0.csv): código -> Elo inicial aproximado
LIGAS = {
    "E0": 1760, "SP1": 1700, "I1": 1690, "D1": 1680, "F1": 1630,
    "E1": 1560, "P1": 1560, "N1": 1560, "B1": 1530, "T1": 1520, "D2": 1520,
    "SP2": 1500, "I2": 1480, "F2": 1470, "G1": 1470, "SC0": 1430,
}
# Ligas "extra" (new/AUT.csv, un archivo con todas las temporadas)
LIGAS_EXTRA = {"AUT": 1480, "SWZ": 1460, "DNK": 1460, "NOR": 1430, "SWE": 1420,
               "POL": 1420, "ROU": 1400}
CSV_EXTRA = "https://www.football-data.co.uk/new/{codigo}.csv"
CHAMPIONS = "EUR"
ELO_SIN_LIGA = 1480   # equipo de Champions de una liga que no tenemos (Kazajistán, Azerbaiyán...)
# Clubes habituales de Europa cuyas ligas no tenemos: punto de partida aproximado
# (después lo corrigen sus partidos de Champions). Forma normalizada del nombre -> Elo
SIN_LIGA = {
    "sk slavia praha": 1640, "ac sparta praha": 1610, "fc viktoria plzen": 1570,
    "fc shakhtar donetsk": 1620, "fc dynamo kyiv": 1590, "gnk dinamo zagreb": 1600,
    "hnk rijeka": 1500, "fk crvena zvezda": 1600, "fk partizan": 1520,
    "ferencvarosi tc": 1560, "qarabag agdam fk": 1560, "qarabag fk": 1560,
    "sk slovan bratislava": 1500, "pfc ludogorets 1945": 1540, "maccabi tel aviv fc": 1530,
    "maccabi haifa fc": 1520, "apoel fc": 1480, "pafos fc": 1520, "fc midtjylland": 1580,
    "fc sheriff tiraspol": 1460, "fc kairat": 1460, "sabah fk": 1460, "fk bodo glimt": 1660,
}
_SIN_LIGA = {" ".join(_tokens(k)): v for k, v in SIN_LIGA.items()}   # sin FC/FK/años

# football-data.org escribe algunos equipos muy distinto que football-data.co.uk.
# Forma normalizada -> nombre en football-data.co.uk (si no aparece, se busca por parecido)
ALIAS = {
    "manchester city fc": "Man City", "manchester united fc": "Man United",
    "tottenham hotspur fc": "Tottenham", "newcastle united fc": "Newcastle",
    "wolverhampton wanderers fc": "Wolves", "nottingham forest fc": "Nott'm Forest",
    "fc bayern munchen": "Bayern Munich", "bayer 04 leverkusen": "Leverkusen",
    "eintracht frankfurt": "Ein Frankfurt", "borussia monchengladbach": "M'gladbach",
    "borussia dortmund": "Dortmund", "vfb stuttgart": "Stuttgart",
    "fc internazionale milano": "Inter", "ac milan": "Milan", "ssc napoli": "Napoli",
    "paris saint germain fc": "Paris SG", "olympique de marseille": "Marseille",
    "olympique lyonnais": "Lyon", "as monaco fc": "Monaco", "stade brestois 29": "Brest",
    "racing club de lens": "Lens", "lille osc": "Lille",
    "psv": "PSV Eindhoven", "afc ajax": "Ajax", "feyenoord rotterdam": "Feyenoord",
    "sport lisboa e benfica": "Benfica", "sporting clube de portugal": "Sp Lisbon",
    "sporting cp": "Sp Lisbon", "sporting clube de braga": "Sp Braga", "fc porto": "Porto",
    "club brugge kv": "Club Brugge", "royale union saint gilloise": "St. Gilloise",
    "olympiakos sfp": "Olympiakos", "olympiacos fc": "Olympiakos", "pae aek": "AEK",
    "paok fc": "PAOK", "fc red bull salzburg": "Salzburg", "sk sturm graz": "Sturm Graz",
    "lask linz": "LASK", "bsc young boys": "Young Boys", "fc kobenhavn": "FC Copenhagen",
    "fk bodo glimt": "Bodo/Glimt", "fk bod glimt": "Bodo/Glimt",
}


# ------------------------------------------------------------ resultados de las ligas


def _ligas(hoy):
    """Partidos de liga de las últimas temporadas en el formato común (con 'liga')."""
    partidos, fallos = [], []
    inicio = inicio_temporada(hoy).year
    for codigo in LIGAS:
        for anio in range(inicio - TEMPORADAS + 1, inicio + 1):
            try:
                for p in datos.historico_csv(date(anio, 8, 1), codigo):
                    p["liga"] = codigo
                    partidos.append(p)
            except Exception:
                if anio == inicio:
                    fallos.append(codigo)
    for codigo in LIGAS_EXTRA:
        try:
            filas = datos._descargar_csv(CSV_EXTRA.format(codigo=codigo))
        except Exception:
            fallos.append(codigo)
            continue
        for f in filas:
            fecha = datos._fecha_csv(f.get("Date", ""))
            gl, gv = datos._num(f, "HG", "FTHG"), datos._num(f, "AG", "FTAG")
            if not fecha or gl is None or gv is None or fecha.year < inicio - TEMPORADAS:
                continue
            partidos.append({"fecha": fecha, "local": f["Home"].strip(),
                             "visitante": f["Away"].strip(), "gl": int(gl), "gv": int(gv),
                             "liga": codigo})
    return partidos, fallos


def _champions(hoy):
    """Partidos de Champions de football-data.org (esta temporada y las que deje el plan gratis)."""
    res, inicio = [], inicio_temporada(hoy).year
    for anio in range(inicio, inicio - TEMPORADAS, -1):
        try:
            res += _partidos_cl(anio)
        except Exception as e:
            print(f"Champions {anio}: {e.__class__.__name__}")
            if anio < inicio:
                break   # el plan gratis no da temporadas antiguas: no seguimos pidiendo
    return [p for p in res if p["fecha"] < hoy]


@lru_cache(maxsize=None)
def _partidos_cl(anio):
    res = []
    for p in datos._pedir_api({"status": "FINISHED", "season": anio}, "CL"):
        gl, gv = datos._goles_90(p)
        if gl is None or gv is None:
            continue
        res.append({"fecha": datos._fecha_api(p).date(), "local_api": p["homeTeam"],
                    "visitante_api": p["awayTeam"], "gl": gl, "gv": gv, "liga": CHAMPIONS,
                    "neutral": p.get("stage") == "FINAL"})
    return res


# ------------------------------------------------------------ nombres


def _nombres(equipo):
    return [x for x in (equipo.get("name"), equipo.get("shortName")) if x]


def clave(equipo, conocidos):
    """Nombre de football-data.co.uk de un equipo de football-data.org (o su propio nombre
    si no juega en ninguna liga que tengamos)."""
    normal = {_normalizar(c): c for c in conocidos}
    for forma in _nombres(equipo):
        espanol = canonico(forma, avisar=False, difuso=False)   # equipos españoles: nombres.py
        if espanol in conocidos:
            return espanol
        n = _normalizar(forma)
        if ALIAS.get(n) in conocidos:
            return ALIAS[n]
        if n in normal:
            return normal[n]
    mejor, nota = None, 0.0
    for c in conocidos:
        s = max(parecido(forma, c) for forma in _nombres(equipo))
        if s > nota:
            mejor, nota = c, s
    return mejor if nota >= 0.85 else _nombres(equipo)[0]


# ------------------------------------------------------------ cálculo


def calcular(hoy, al_partido=None):
    """Elo de los clubes de Europa con todo lo jugado antes de 'hoy'.
    Devuelve (elo, buscar) donde buscar(equipo_de_football_data_org) -> Elo o None."""
    ligas, fallos = _ligas(hoy)
    if fallos:
        print(f"Elo europeo: ligas no disponibles: {', '.join(fallos)}")
    if not ligas:
        return {}, lambda equipo: None

    # Equipos que juegan ahora en alguna liga (para no emparejar con un club que ya no está)
    reciente = inicio_temporada(hoy).replace(year=inicio_temporada(hoy).year - 1)
    conocidos = {p[k] for p in ligas if p["fecha"] >= reciente for k in ("local", "visitante")}
    cache = {}

    def nombre(equipo):
        n = _nombres(equipo)[0]
        if n not in cache:
            cache[n] = clave(equipo, conocidos)
        return cache[n]

    europa, inicial_equipo = [], {}
    for p in _champions(hoy):
        for eq in (p["local_api"], p["visitante_api"]):
            n = " ".join(_tokens(eq.get("name", "")))
            if n in _SIN_LIGA and nombre(eq) not in conocidos:
                inicial_equipo[nombre(eq)] = _SIN_LIGA[n]
        europa.append({**p, "local": nombre(p["local_api"]), "visitante": nombre(p["visitante_api"])})
    print(f"Elo europeo: {len(ligas)} partidos de liga, {len(europa)} de Champions")
    sueltos = sorted({p[k] for p in europa for k in ("local", "visitante")} - conocidos)
    if sueltos:
        print(f"Elo europeo: equipos de Champions sin liga en los datos ({len(sueltos)}): "
              + ", ".join(sueltos))
    if not europa:
        datos._avisar("Elo europeo sin partidos de Champions: las ligas no se comparan entre sí")

    inicial = {**LIGAS, **LIGAS_EXTRA}
    tabla = elo_calc.calcular(ligas + europa, hoy, inicial=inicial, defecto=ELO_SIN_LIGA,
                              sin_liga=(CHAMPIONS,), inicial_equipo=inicial_equipo,
                              al_partido=al_partido)

    def buscar(equipo):
        return tabla.get(nombre(equipo))

    return tabla, buscar


def evaluar(hoy, desde, ventajas=(40, 70, 100), goles=(1.3, 1.45, 1.6)):
    """¿Acierta este Elo en Champions? Para cada partido de Champions desde 'desde', pronostica
    con el Elo que había justo antes (sin mirar el futuro) y mide log-loss 1X2 y acierto,
    probando varias ventajas de campo y goles por equipo. Devuelve una lista ordenada
    de (log-loss, acierto, ventaja, goles) y (n, log-loss sin información)."""
    import math
    from champions import lambdas_elo
    from modelo import CONFIG, matriz, probabilidades_1x2
    partidos = []

    def al_partido(p, el, ev):
        if p["liga"] == CHAMPIONS and p["fecha"] >= desde:
            real = 0 if p["gl"] > p["gv"] else 1 if p["gl"] == p["gv"] else 2
            partidos.append((el, ev, p.get("neutral", False), real))

    calcular(hoy, al_partido)
    if not partidos:
        return None
    n = len(partidos)
    frec = [sum(r == i for *_, r in partidos) / n for i in range(3)]
    base = -sum(math.log(frec[r]) for *_, r in partidos) / n
    res = []
    for v in ventajas:
        for g in goles:
            ll = ac = 0
            for el, ev, neutral, real in partidos:
                pr = probabilidades_1x2(matriz(*lambdas_elo(
                    el, ev, neutral, cfg={"ventaja_casa_elo": v, "goles_equipo": g}), CONFIG["rho"]))
                ll -= math.log(max(pr[real], 1e-9))
                ac += max(range(3), key=lambda i: pr[i]) == real
            res.append((ll / n, ac / n, v, g))
    return sorted(res), (n, base)


if __name__ == "__main__":
    # python elo_europa.py -> los 40 mejores, la media de cada liga y cuánto acierta en Champions
    hoy = date.today()
    tabla, _ = calcular(hoy)
    for i, (e, v) in enumerate(sorted(tabla.items(), key=lambda t: -t[1])[:40], 1):
        print(f"{i:2}. {e:22} {v:.0f}")
    ligas, _ = _ligas(hoy)
    ultima = {}
    for p in sorted(ligas, key=lambda p: p["fecha"]):
        for k in ("local", "visitante"):
            ultima[p[k]] = p["liga"]
    print("\nMedia de cada liga (inicial -> ahora, equipos de la última temporada):")
    reciente = inicio_temporada(hoy).replace(year=inicio_temporada(hoy).year - 1)
    medias = {}
    for p in ligas:
        if p["fecha"] >= reciente:
            for k in ("local", "visitante"):
                if p[k] in tabla and ultima[p[k]] == p["liga"]:
                    medias.setdefault(p["liga"], {})[p[k]] = tabla[p[k]]
    inicial = {**LIGAS, **LIGAS_EXTRA}
    for liga, v in sorted(medias.items(), key=lambda t: -sum(t[1].values()) / len(t[1])):
        print(f"  {liga:4} {inicial.get(liga, 0):5} -> {sum(v.values()) / len(v):.0f}  ({len(v)} equipos)")
    r = evaluar(hoy, date(inicio_temporada(hoy).year - 1, 7, 1))
    if r:
        pruebas, (n, base) = r
        print(f"\nChampions desde la temporada pasada ({n} partidos, sin mirar el futuro)."
              f" Log-loss sin información: {base:.3f}")
        for ll, ac, v, g in pruebas:
            print(f"  ventaja casa {v:3} | goles/equipo {g:.2f} -> log-loss {ll:.3f}, signo {ac:.0%}")
