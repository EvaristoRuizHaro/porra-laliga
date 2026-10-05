# Modelo estadístico de Poisson para predecir resultados de fútbol
import math

from datos import nombre

MAX_GOLES = 6     # calculamos probabilidades de 0-0 hasta 6-6
CONFIANZA = 4     # partidos necesarios para "fiarse" de las estadísticas de un equipo


def poisson(k, media):
    """Probabilidad de marcar exactamente k goles si la media esperada es 'media'."""
    return math.exp(-media) * media ** k / math.factorial(k)


def calcular_fuerzas(partidos):
    """Calcula el ataque y la defensa de cada equipo comparados con la media de la liga."""
    equipos = {}
    goles_local = goles_visitante = 0

    for p in partidos:
        local, visit = nombre(p["homeTeam"]), nombre(p["awayTeam"])
        gl, gv = p["score"]["fullTime"]["home"], p["score"]["fullTime"]["away"]
        goles_local += gl
        goles_visitante += gv
        for equipo, marcados, encajados in [(local, gl, gv), (visit, gv, gl)]:
            e = equipos.setdefault(equipo, {"pj": 0, "gf": 0, "gc": 0})
            e["pj"] += 1
            e["gf"] += marcados
            e["gc"] += encajados

    n = max(len(partidos), 1)
    media_local = goles_local / n if partidos else 1.5        # goles medios del equipo local
    media_visit = goles_visitante / n if partidos else 1.1    # goles medios del visitante
    media_equipo = (media_local + media_visit) / 2            # goles medios por equipo y partido

    fuerzas = {}
    for equipo, e in equipos.items():
        ataque = (e["gf"] / e["pj"]) / media_equipo
        defensa = (e["gc"] / e["pj"]) / media_equipo
        # Con pocos partidos, acercamos los valores a 1 (la media) para no exagerar
        peso = e["pj"] / (e["pj"] + CONFIANZA)
        fuerzas[equipo] = {
            "ataque": peso * ataque + (1 - peso) * 1,
            "defensa": peso * defensa + (1 - peso) * 1,
            # Datos "en bruto" para poder explicar el pronóstico
            "pj": e["pj"],
            "gf_pj": e["gf"] / e["pj"],   # goles a favor por partido
            "gc_pj": e["gc"] / e["pj"],   # goles en contra por partido
        }
    return fuerzas, media_local, media_visit


def predecir(local, visitante, fuerzas, media_local, media_visit):
    """Devuelve el mejor pronóstico para la porra (6 pts exacto / 3 pts signo)."""
    neutro = {"ataque": 1, "defensa": 1}
    fl, fv = fuerzas.get(local, neutro), fuerzas.get(visitante, neutro)

    # Goles esperados de cada equipo
    lambda_local = media_local * fl["ataque"] * fv["defensa"]
    lambda_visit = media_visit * fv["ataque"] * fl["defensa"]

    # Probabilidad de cada resultado posible (0-0, 1-0, 0-1, ...)
    probs = {(a, b): poisson(a, lambda_local) * poisson(b, lambda_visit)
             for a in range(MAX_GOLES + 1) for b in range(MAX_GOLES + 1)}

    signo = lambda a, b: "1" if a > b else ("X" if a == b else "2")
    p_signo = {"1": 0.0, "X": 0.0, "2": 0.0}
    for (a, b), p in probs.items():
        p_signo[signo(a, b)] += p

    # Puntos esperados de apostar a (a, b):
    #   6 * P(exacto) + 3 * P(mismo signo pero no exacto) = 3 * (P(signo) + P(exacto))
    def puntos_esperados(res):
        return 3 * (p_signo[signo(*res)] + probs[res])

    mejor = max(probs, key=puntos_esperados)
    return {
        "resultado": mejor,
        "puntos_esperados": puntos_esperados(mejor),
        "p_exacto": probs[mejor],
        "p1": p_signo["1"], "px": p_signo["X"], "p2": p_signo["2"],
        "goles_esperados": (lambda_local, lambda_visit),
    }
