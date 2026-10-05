# Guarda cada pronóstico en historial.csv y, cuando el partido se juega, apunta el resultado
# y los puntos de la porra. Así sabemos si el agente acierta de verdad.
import csv
import os
from datetime import date, timedelta

from modelo import _signo, inicio_temporada

ARCHIVO = "historial.csv"
COLUMNAS = ["id", "fecha", "jornada", "local", "visitante", "pronostico",
            "p1", "px", "p2", "puntos_esperados", "resultado", "puntos"]


def cargar():
    if not os.path.exists(ARCHIVO):
        return []
    with open(ARCHIVO, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def guardar(filas):
    filas = sorted(filas, key=lambda f: (f["fecha"], f["id"]))
    with open(ARCHIVO, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNAS)
        w.writeheader()
        w.writerows(filas)


def _puntos(pronostico, resultado):
    if pronostico == resultado:
        return 6
    return 3 if _signo(*pronostico) == _signo(*resultado) else 0


def _marcador(texto):
    a, b = texto.split("-")
    return int(a), int(b)


def apuntar_resultados(filas, terminados):
    """Rellena resultado y puntos de los partidos ya jugados (terminados = lista de la API)."""
    por_id = {str(p["id"]): (p["gl"], p["gv"]) for p in terminados if "id" in p}
    for f in filas:
        if not f["resultado"] and f["id"] in por_id:
            real = por_id[f["id"]]
            f["resultado"] = f"{real[0]}-{real[1]}"
            f["puntos"] = _puntos(_marcador(f["pronostico"]), real)


def anadir(filas, nuevas):
    """Añade los pronósticos nuevos (si se relanza la semana, sustituye los no jugados)."""
    nuevas_ids = {n["id"] for n in nuevas}
    jugados = {f["id"] for f in filas if f["resultado"]}
    filas[:] = [f for f in filas if f["id"] not in nuevas_ids or f["resultado"]]
    filas += [n for n in nuevas if n["id"] not in jugados]


def _balance(filas):
    jugadas = [f for f in filas if f["resultado"]]
    pts = sum(int(f["puntos"]) for f in jugadas)
    return {"n": len(jugadas), "pts": pts,
            "signos": sum(int(f["puntos"]) >= 3 for f in jugadas),
            "exactos": sum(int(f["puntos"]) == 6 for f in jugadas),
            "esperados": sum(float(f["puntos_esperados"]) for f in jugadas)}


def resumen(filas, lunes):
    """Texto con el balance de la semana pasada y de la temporada (o None si no hay nada)."""
    anterior = (lunes - timedelta(days=7)).isoformat()
    semana = _balance([f for f in filas if anterior <= f["fecha"] < lunes.isoformat()])
    temporada = _balance([f for f in filas
                          if inicio_temporada(lunes).isoformat() <= f["fecha"] < lunes.isoformat()])
    if not temporada["n"]:
        return None
    lineas = []
    if semana["n"]:
        lineas.append(f"📒 Semana pasada: {semana['pts']} pts "
                      f"({semana['signos']}/{semana['n']} signos, {semana['exactos']} exactos; "
                      f"el modelo esperaba {semana['esperados']:.1f})")
    lineas.append(f"🏆 Temporada: {temporada['pts']} pts en {temporada['n']} partidos "
                  f"({temporada['pts'] / temporada['n']:.2f} por partido, "
                  f"{temporada['signos'] / temporada['n']:.0%} de signos)")
    return "\n".join(lineas)


def fila(partido, pred, fecha):
    a, b = pred["resultado"]
    return {"id": str(partido["id"]), "fecha": fecha.isoformat(),
            "jornada": partido.get("matchday", ""),
            "local": partido["local"], "visitante": partido["visitante"],
            "pronostico": f"{a}-{b}", "p1": f"{pred['p1']:.3f}", "px": f"{pred['px']:.3f}",
            "p2": f"{pred['p2']:.3f}", "puntos_esperados": f"{pred['puntos_esperados']:.2f}",
            "resultado": "", "puntos": ""}


if __name__ == "__main__":
    # python historial.py -> balance rápido por consola
    print(resumen(cargar(), date.today() + timedelta(days=7 - date.today().weekday())))
