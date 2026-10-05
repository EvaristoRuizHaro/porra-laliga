# Backtest: "¿cuántos puntos habría sacado el agente en temporadas pasadas?"
# Simula cada lunes: ajusta el modelo solo con lo jugado hasta ese día y pronostica la semana.
#   Uso:  python backtest.py            (últimas 3 temporadas, datos de football-data.co.uk)
import math
import sys
from collections import defaultdict
from datetime import date, timedelta

from modelo import _signo, ajustar, predecir


def puntos_porra(pronostico, real):
    if pronostico == real:
        return 6
    return 3 if _signo(*pronostico) == _signo(*real) else 0


def evaluar(partidos, desde, hasta, elo_en=None, cfg=None, usar_cuotas=True):
    """Simula la porra entre dos fechas. elo_en(fecha) -> dict de Elo (opcional)."""
    semanas = defaultdict(list)
    for p in partidos:
        if desde <= p["fecha"] < hasta:
            semanas[p["fecha"] - timedelta(days=p["fecha"].weekday())].append(p)

    pts = signos = exactos = n = 0
    logloss = rps = 0.0
    for lunes in sorted(semanas):
        semana = semanas[lunes]
        equipos = {p[k] for p in semana for k in ("local", "visitante")}
        modelo = ajustar(partidos, lunes, elo=elo_en(lunes) if elo_en else None,
                         equipos_extra=equipos, cfg=cfg)
        for p in semana:
            pred = predecir(modelo, p["local"], p["visitante"],
                            cuotas=p.get("cuotas") if usar_cuotas else None, cfg=cfg)
            real = (p["gl"], p["gv"])
            puntos = puntos_porra(pred["resultado"], real)
            pts += puntos
            signos += puntos >= 3
            exactos += puntos == 6
            n += 1
            probs = [pred["p1"], pred["px"], pred["p2"]]
            k = "1X2".index(_signo(*real))
            logloss -= math.log(max(probs[k], 1e-12))
            acum = [probs[0], probs[0] + probs[1]]
            obs = [k <= 0, k <= 1]
            rps += sum((a - b) ** 2 for a, b in zip(acum, obs)) / 2
    return {"partidos": n, "pts_partido": pts / n, "signos": signos / n,
            "exactos": exactos / n, "logloss": logloss / n, "rps": rps / n}


def mostrar(nombre, r):
    print(f"{nombre:<34} {r['partidos']:>5}  {r['pts_partido']:.3f} pts/partido  "
          f"signo {r['signos']:.1%}  exacto {r['exactos']:.1%}  "
          f"logloss {r['logloss']:.4f}  RPS {r['rps']:.4f}")


if __name__ == "__main__":
    from datos import historico_csv

    hoy = date.today()
    anios = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    inicio = hoy.year - anios - 2 if hoy.month >= 7 else hoy.year - anios - 3
    partidos = []
    for anio in range(inicio, hoy.year + 1):
        if date(anio, 8, 1) <= hoy:
            partidos += historico_csv(date(anio, 8, 1))
    desde = date(inicio + 2, 7, 1)
    mostrar("Solo estadísticas", evaluar(partidos, desde, hoy, usar_cuotas=False))
    mostrar("Estadísticas + cuotas", evaluar(partidos, desde, hoy))
    mostrar("Solo cuotas", evaluar(partidos, desde, hoy, cfg={"peso_mercado": 1.0}))
