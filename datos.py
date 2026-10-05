# De dónde salen los datos (todo gratis):
#   - football-data.org (API, con clave): calendario de la semana y resultados al momento.
#   - football-data.co.uk (CSV): resultados + tiros a puerta + cuotas, temporada actual y pasada.
#   - ClubElo (API abierta): puntuación Elo de cada club, incluidos los de Segunda.
#   - The Odds API (opcional, con clave gratis): cuotas de los partidos de la semana.
#     Si no hay clave, se usan las cuotas de fixtures.csv de football-data.co.uk.
# Si una fuente falla, el agente sigue con las demás y lo avisa en el mensaje.
import csv
import io
import os
import statistics
import time
from datetime import date, datetime, timedelta
from functools import lru_cache

import requests
from dotenv import load_dotenv

import elo as elo_propio
from modelo import inicio_temporada
from nombres import canonico

load_dotenv()
API = "https://api.football-data.org/v4/competitions/PD/matches"  # PD = Primera División
CABECERAS = {"X-Auth-Token": os.getenv("FOOTBALL_DATA_KEY")}
CSV_TEMPORADA = "https://www.football-data.co.uk/mmz4281/{codigo}/{liga}.csv"  # SP1/SP2
CSV_PROXIMOS = "https://www.football-data.co.uk/fixtures.csv"
CLUBELO = "http://api.clubelo.com/{fecha}"
ODDS_API = "https://api.the-odds-api.com/v4/sports/soccer_spain_la_liga/odds"

avisos = []  # problemas con las fuentes, para mostrarlos al final del mensaje


def _avisar(texto):
    print(f"⚠️  {texto}")
    avisos.append(texto)


# ------------------------------------------------------------ football-data.org (API)


def _pedir_api(params):
    r = requests.get(API, headers=CABECERAS, params=params, timeout=30)
    r.raise_for_status()  # si la clave está mal, aquí salta un error 403/400
    return r.json()["matches"]


def nombre(equipo):
    """Nombre corto del equipo para mostrar (con respaldo por si la API no lo trae)."""
    return equipo.get("shortName") or equipo.get("name") or "?"


def _canonico_api(equipo):
    return canonico(equipo.get("name") or nombre(equipo))


def _fecha_api(p):
    return datetime.fromisoformat(p["utcDate"].replace("Z", "+00:00"))


def partidos_entre(desde, hasta):
    """Partidos programados entre dos fechas (formato AAAA-MM-DD), tal cual los da la API."""
    partidos = _pedir_api({"dateFrom": desde, "dateTo": hasta})
    for p in partidos:
        p["local"], p["visitante"] = _canonico_api(p["homeTeam"]), _canonico_api(p["awayTeam"])
    return partidos


def terminados_api(temporada=None):
    """Partidos terminados según la API (solo goles), en el formato común."""
    params = {"status": "FINISHED"}
    if temporada:
        params["season"] = temporada
    res = []
    for p in _pedir_api(params):
        gl, gv = p["score"]["fullTime"]["home"], p["score"]["fullTime"]["away"]
        if gl is None or gv is None:
            continue
        res.append({"id": p["id"], "fecha": _fecha_api(p).date(),
                    "local": _canonico_api(p["homeTeam"]),
                    "visitante": _canonico_api(p["awayTeam"]),
                    "gl": gl, "gv": gv, "tl": None, "tv": None})
    return res


# ------------------------------------------------------------ football-data.co.uk (CSV)


@lru_cache(maxsize=None)  # si se pide dos veces el mismo CSV, solo se descarga una
def _descargar_csv(url):
    r = requests.get(url, timeout=30, headers={"User-Agent": "porra-laliga"})
    r.raise_for_status()
    return list(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig", errors="replace"))))


def _num(fila, *columnas):
    """Primer valor numérico que encuentre entre varias columnas posibles."""
    for c in columnas:
        try:
            return float(fila[c])
        except (KeyError, TypeError, ValueError):
            continue
    return None


def _cuotas_fila(fila):
    c = {"1": _num(fila, "AvgH", "B365H", "PSH"), "X": _num(fila, "AvgD", "B365D", "PSD"),
         "2": _num(fila, "AvgA", "B365A", "PSA"),
         "mas25": _num(fila, "Avg>2.5", "B365>2.5", "P>2.5"),
         "menos25": _num(fila, "Avg<2.5", "B365<2.5", "P<2.5")}
    return c if c["1"] and c["X"] and c["2"] else None


def _fecha_csv(texto):
    for formato in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    return None


def codigo_temporada(dia):
    """date(2026, 10, 5) -> '2627'."""
    a = inicio_temporada(dia).year % 100
    return f"{a:02d}{(a + 1) % 100:02d}"


def historico_csv(dia, liga="SP1"):
    """Partidos de la temporada que contiene 'dia', con tiros a puerta y cuotas de cierre."""
    res = []
    for f in _descargar_csv(CSV_TEMPORADA.format(codigo=codigo_temporada(dia), liga=liga)):
        fecha, gl, gv = _fecha_csv(f.get("Date", "")), _num(f, "FTHG"), _num(f, "FTAG")
        if not fecha or gl is None or gv is None:
            continue
        tl, tv = _num(f, "HST"), _num(f, "AST")
        avisar = liga == "SP1"  # en Segunda hay muchos equipos que no están en ALIAS (da igual)
        res.append({"fecha": fecha, "local": canonico(f["HomeTeam"], avisar),
                    "visitante": canonico(f["AwayTeam"], avisar), "gl": int(gl), "gv": int(gv),
                    "tl": tl, "tv": tv, "cuotas": _cuotas_fila(f), "liga": liga})
    return res


# ------------------------------------------------------------ todo junto


def historico(hoy):
    """Temporada pasada + actual. Prioriza el CSV (trae tiros); la API rellena lo que falte."""
    partidos = []
    temporada = inicio_temporada(hoy)
    for dia, etiqueta in ((date(temporada.year - 1, 8, 1), "pasada"), (hoy, "actual")):
        try:
            partidos += historico_csv(dia)
        except Exception as e:
            _avisar(f"CSV temporada {etiqueta} no disponible ({e.__class__.__name__})")
            if etiqueta == "pasada":
                try:  # el plan gratis de la API a veces deja ver la temporada anterior
                    partidos += terminados_api(temporada.year - 1)
                except Exception:
                    pass

    # La API va al día; el CSV puede tardar 1-2 días en actualizarse
    try:
        ya = {(p["local"], p["visitante"], inicio_temporada(p["fecha"])) for p in partidos}
        api = terminados_api()
        nuevos = [p for p in api
                  if (p["local"], p["visitante"], inicio_temporada(p["fecha"])) not in ya]
        partidos += nuevos
        print(f"Histórico: {len(partidos)} partidos ({len(nuevos)} recientes solo de la API)")
    except Exception as e:
        _avisar(f"API de resultados no disponible ({e.__class__.__name__})")
        api = []
    return partidos, api


def _elo_clubelo(dia):
    """Elo de ClubElo. Su servidor a veces falla: reintenta y prueba días anteriores."""
    for intento in range(3):
        fecha = dia - timedelta(days=intento)
        try:
            r = requests.get(CLUBELO.format(fecha=fecha.isoformat()), timeout=30)
            r.raise_for_status()
            res = {}
            for f in csv.DictReader(io.StringIO(r.text)):  # vienen de mejor a peor
                if f.get("Country") == "ESP":
                    res.setdefault(canonico(f["Club"], avisar=False, difuso=False), float(f["Elo"]))
            if res:
                return res
        except Exception as e:
            print(f"ClubElo {fecha}: {e.__class__.__name__}")
        time.sleep(3)
    return {}


def _elo_calculado(dia, jugados):
    """Elo propio con 5 temporadas de Primera y Segunda de football-data.co.uk."""
    partidos = [p for p in jugados if p["fecha"] < dia]
    ya = {(p["local"], p["visitante"], p["fecha"]) for p in partidos}
    inicio = inicio_temporada(dia).year
    for anio in range(inicio - 4, inicio + 1):
        for liga in ("SP1", "SP2"):
            try:
                partidos += [p for p in historico_csv(date(anio, 8, 1), liga)
                             if (p["local"], p["visitante"], p["fecha"]) not in ya]
            except Exception as e:
                print(f"CSV {liga} {anio}: {e.__class__.__name__}")
    return elo_propio.calcular(partidos, dia)


def elo(dia, jugados=()):
    """Elo de los clubes españoles: ClubElo y, si falla, calculado por nosotros."""
    res = _elo_clubelo(dia)
    if res:
        print(f"Elo de ClubElo: {len(res)} clubes españoles")
        return res
    res = _elo_calculado(dia, list(jugados))
    if res:
        print(f"ClubElo caído: Elo calculado con resultados de Primera y Segunda ({len(res)} equipos)")
        return res
    _avisar("Elo no disponible")
    return {}


# ------------------------------------------------------------ cuotas de la semana


def _cuotas_odds_api():
    clave = os.getenv("ODDS_API_KEY")
    if not clave:
        return {}
    r = requests.get(ODDS_API, timeout=30, params={
        "apiKey": clave, "regions": "eu", "markets": "h2h,totals", "oddsFormat": "decimal"})
    r.raise_for_status()
    print(f"The Odds API: quedan {r.headers.get('x-requests-remaining', '?')} créditos este mes")
    res = {}
    for ev in r.json():
        local, visit = ev["home_team"], ev["away_team"]
        precios = {"1": [], "X": [], "2": [], "mas25": [], "menos25": []}
        for casa in ev.get("bookmakers", []):
            for mercado in casa.get("markets", []):
                for o in mercado.get("outcomes", []):
                    if mercado["key"] == "h2h":
                        clave_o = "1" if o["name"] == local else "2" if o["name"] == visit else "X"
                        precios[clave_o].append(o["price"])
                    elif mercado["key"] == "totals" and o.get("point") == 2.5:
                        precios["mas25" if o["name"] == "Over" else "menos25"].append(o["price"])
        c = {k: statistics.median(v) if v else None for k, v in precios.items()}
        if c["1"] and c["X"] and c["2"]:
            res[(canonico(local), canonico(visit))] = c
    return res


def _cuotas_fixtures():
    res = {}
    for f in _descargar_csv(CSV_PROXIMOS):
        if f.get("Div") == "SP1" and _cuotas_fila(f):
            res[(canonico(f["HomeTeam"]), canonico(f["AwayTeam"]))] = _cuotas_fila(f)
    return res


def cuotas_semana():
    """Cuotas de los próximos partidos: {(local, visitante): {"1", "X", "2", "mas25", "menos25"}}."""
    res = {}
    for fuente, funcion in (("football-data.co.uk", _cuotas_fixtures),
                            ("The Odds API", _cuotas_odds_api)):
        try:
            nuevas = funcion()
            res.update(nuevas)  # The Odds API va después: si las tiene, manda
            print(f"Cuotas de {fuente}: {len(nuevas)} partidos")
        except Exception as e:
            print(f"Cuotas de {fuente} no disponibles ({e.__class__.__name__})")
    return res
