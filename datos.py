# Descarga partidos de LaLiga desde football-data.org (gratis con registro)
import os
import requests
from dotenv import load_dotenv

load_dotenv()
API = "https://api.football-data.org/v4/competitions/PD/matches"  # PD = Primera División
CABECERAS = {"X-Auth-Token": os.getenv("FOOTBALL_DATA_KEY")}


def _pedir(params):
    r = requests.get(API, headers=CABECERAS, params=params, timeout=30)
    r.raise_for_status()  # si la clave está mal, aquí salta un error 403/400
    return r.json()["matches"]


def partidos_terminados():
    """Todos los partidos ya jugados esta temporada (para calcular estadísticas)."""
    return _pedir({"status": "FINISHED"})


def partidos_entre(desde, hasta):
    """Partidos programados entre dos fechas (formato AAAA-MM-DD)."""
    return _pedir({"dateFrom": desde, "dateTo": hasta})


def nombre(equipo):
    """Nombre corto del equipo (con respaldo por si la API no lo trae)."""
    return equipo.get("shortName") or equipo.get("name") or "?"
