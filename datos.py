# De dónde salen los datos (todo gratis):
#   - football-data.org (API, con clave): calendario de la semana y resultados al momento.
#   - football-data.co.uk (CSV): resultados + tiros a puerta + cuotas, temporada actual y pasada.
#   - ClubElo (API abierta): puntuación Elo de cada club, incluidos los de Segunda.
#   - The Odds API (opcional, con clave gratis): cuotas de los partidos de la semana
#     (LaLiga y Champions).
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
API = "https://api.football-data.org/v4/competitions/{comp}/matches"  # PD = Primera, CL = Champions
CABECERAS = {"X-Auth-Token": os.getenv("FOOTBALL_DATA_KEY")}
CSV_TEMPORADA = "https://www.football-data.co.uk/mmz4281/{codigo}/{liga}.csv"  # SP1/SP2
CSV_PROXIMOS = "https://www.football-data.co.uk/fixtures.csv"
CLUBELO = "http://api.clubelo.com/{fecha}"
ODDS_API = "https://api.the-odds-api.com/v4/sports/{deporte}/odds"
DEPORTE_ODDS = {"PD": "soccer_spain_la_liga", "CL": "soccer_uefa_champs_league"}

avisos = []  # problemas con las fuentes, para mostrarlos al final del mensaje


def _avisar(texto):
    print(f"⚠️  {texto}")
    avisos.append(texto)


# ------------------------------------------------------------ football-data.org (API)


def _pedir_api(params, competicion="PD"):
    r = requests.get(API.format(comp=competicion), headers=CABECERAS, params=params, timeout=30)
    if r.status_code == 429:  # plan gratis: 10 peticiones por minuto; esperamos y repetimos
        espera = int(r.headers.get("X-RequestCounter-Reset", 60)) + 1
        print(f"football-data.org: límite de peticiones, espero {espera} s")
        time.sleep(min(espera, 65))
        r = requests.get(API.format(comp=competicion), headers=CABECERAS, params=params, timeout=30)
    r.raise_for_status()  # si la clave está mal, aquí salta un error 403/400
    return r.json()["matches"]


def nombre(equipo):
    """Nombre corto del equipo para mostrar (con respaldo por si la API no lo trae)."""
    return equipo.get("shortName") or equipo.get("name") or "?"


def _canonico_api(equipo, competicion="PD"):
    if competicion != "PD":
        # Champions: los españoles con su nombre de siempre; los demás, tal cual los da la API
        # (sin parecidos aproximados: "Celtic" no debe convertirse en "Celta")
        return canonico(equipo.get("name") or nombre(equipo), avisar=False, difuso=False)
    return canonico(equipo.get("name") or nombre(equipo))


def _fecha_api(p):
    return datetime.fromisoformat(p["utcDate"].replace("Z", "+00:00"))


def partidos_entre(desde, hasta, competicion="PD"):
    """Partidos programados entre dos fechas (formato AAAA-MM-DD), tal cual los da la API."""
    partidos = _pedir_api({"dateFrom": desde, "dateTo": hasta}, competicion)
    for p in partidos:
        p["competicion"] = competicion
        p["local"] = _canonico_api(p["homeTeam"], competicion)
        p["visitante"] = _canonico_api(p["awayTeam"], competicion)
    return partidos


def _goles_90(p):
    """Goles a los 90 minutos (en eliminatorias de Champions puede haber prórroga y penaltis)."""
    marcador = p["score"]
    if marcador.get("duration", "REGULAR") != "REGULAR" and marcador.get("regularTime"):
        return marcador["regularTime"]["home"], marcador["regularTime"]["away"]
    return marcador["fullTime"]["home"], marcador["fullTime"]["away"]


def terminados_api(temporada=None, competicion="PD"):
    """Partidos terminados según la API (solo goles a los 90'), en el formato común."""
    params = {"status": "FINISHED"}
    if temporada:
        params["season"] = temporada
    res = []
    for p in _pedir_api(params, competicion):
        gl, gv = _goles_90(p)
        if gl is None or gv is None:
            continue
        res.append({"id": p["id"], "fecha": _fecha_api(p).date(),
                    "local": _canonico_api(p["homeTeam"], competicion),
                    "visitante": _canonico_api(p["awayTeam"], competicion),
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
        if liga in ("SP1", "SP2"):
            local, visit = canonico(f["HomeTeam"], avisar), canonico(f["AwayTeam"], avisar)
        else:  # ligas extranjeras (Elo europeo): tal cual, sin parecidos con equipos españoles
            local, visit = f["HomeTeam"].strip(), f["AwayTeam"].strip()
        res.append({"fecha": fecha, "local": local,
                    "visitante": visit, "gl": int(gl), "gv": int(gv),
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


@lru_cache(maxsize=None)  # LaLiga y Champions usan la misma descarga
def _clubelo(dia):
    """Tabla de ClubElo (todos los clubes de Europa). Su servidor a veces falla:
    reintenta y prueba días anteriores. Devuelve una lista de filas (vacía si no hay)."""
    for intento in range(3):
        fecha = dia - timedelta(days=intento)
        try:
            r = requests.get(CLUBELO.format(fecha=fecha.isoformat()), timeout=30)
            r.raise_for_status()
            filas = list(csv.DictReader(io.StringIO(r.text)))  # vienen de mejor a peor
            if filas:
                return filas
        except Exception as e:
            print(f"ClubElo {fecha}: {e.__class__.__name__}")
        time.sleep(3)
    return []


def _elo_clubelo(dia):
    res = {}
    for f in _clubelo(dia):
        if f.get("Country") == "ESP":
            res.setdefault(canonico(f["Club"], avisar=False, difuso=False), float(f["Elo"]))
    return res


ELO_EUROPA_CACHE = "elo_europa.csv"   # última tabla buena de ClubElo, por si se cae


def elo_europa(dia):
    """Elo de ClubElo de todos los clubes europeos, con su nombre de ClubElo: {"Bayern": 1990, ...}.
    Cada vez que ClubElo responde se guarda una copia en elo_europa.csv (ver elo_europa_copia).
    Devuelve (elos, fecha) o ({}, None) si ClubElo no responde."""
    res = {}
    for f in _clubelo(dia):
        try:
            res.setdefault(f["Club"], float(f["Elo"]))
        except (KeyError, TypeError, ValueError):
            continue
    if res:
        with open(ELO_EUROPA_CACHE, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["club", "elo", "fecha"])
            w.writerows([club, f"{elo:.0f}", dia.isoformat()] for club, elo in res.items())
        return res, dia
    return {}, None


def elo_europa_copia():
    """Última copia guardada de ClubElo: (elos, fecha) o ({}, None)."""
    try:
        with open(ELO_EUROPA_CACHE, newline="", encoding="utf-8") as fh:
            filas = list(csv.DictReader(fh))
        if filas:
            return {f["club"]: float(f["elo"]) for f in filas}, date.fromisoformat(filas[0]["fecha"])
    except (OSError, KeyError, ValueError):
        pass
    return {}, None


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


def eventos_odds_api(competicion="PD"):
    """Partidos con cuotas de The Odds API (mediana de las casas), con sus nombres originales:
    [{"inicio": datetime, "local": "...", "visitante": "...", "cuotas": {...}}, ...]"""
    clave = os.getenv("ODDS_API_KEY")
    if not clave:
        raise RuntimeError("falta ODDS_API_KEY")
    r = requests.get(ODDS_API.format(deporte=DEPORTE_ODDS[competicion]), timeout=30, params={
        "apiKey": clave, "regions": "eu", "markets": "h2h,totals", "oddsFormat": "decimal"})
    if r.status_code != 200:
        # 401 = clave mal o créditos agotados; 422 = parámetros; 429 = demasiadas peticiones
        try:
            detalle = r.json().get("error_code") or r.json().get("message", "")
        except ValueError:
            detalle = ""
        raise RuntimeError(f"HTTP {r.status_code} {detalle}".strip())
    print(f"The Odds API: quedan {r.headers.get('x-requests-remaining', '?')} créditos este mes")
    res = []
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
            inicio = datetime.fromisoformat(ev["commence_time"].replace("Z", "+00:00"))
            res.append({"inicio": inicio, "local": local, "visitante": visit, "cuotas": c})
    return res


def _cuotas_odds_api():
    if not os.getenv("ODDS_API_KEY"):
        return {}
    return {(canonico(e["local"]), canonico(e["visitante"])): e["cuotas"]
            for e in eventos_odds_api("PD")}


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
