# Modelo de goles para la porra.
#
# Idea: cada equipo tiene un "ataque" y una "defensa". Los goles esperados de un partido son
#   λ_local     = exp(base + ventaja_casa + ataque_local     + defensa_visitante)
#   λ_visitante = exp(base +                ataque_visitante + defensa_local)
# (defensa alta = encaja mucho). Los valores se ajustan por máxima verosimilitud con:
#   - las dos últimas temporadas, dando más peso a lo reciente (semivida),
#   - goles "mezclados" con tiros a puerta (menos suerte que los goles),
#   - un punto de partida (a priori) según el Elo del equipo o si es recién ascendido.
# Después se corrige la probabilidad de 0-0, 1-0, 0-1 y 1-1 (Dixon-Coles) y, si hay cuotas
# de las casas de apuestas, se mezcla el modelo con lo que dice el mercado.
import math
from datetime import date, timedelta

import numpy as np

# Hiperparámetros: ajustados con backtest.py sobre temporadas pasadas de LaLiga
CONFIG = {
    "semivida_dias": 365,    # un partido de hace un año cuenta la mitad que uno de hoy
    "ventana_dias": 600,     # no miramos más atrás de esto (~2 temporadas)
    "ridge": 20.0,           # cuánto "tira" el a priori de cada equipo (más = más prudente)
    "peso_tiros": 0.2,       # 0 = solo goles, 1 = solo tiros a puerta
    "rho": -0.08,            # corrección Dixon-Coles (negativo = más 0-0 y 1-1)
    "elo_escala": 0.2,       # cuánto mueve el Elo el a priori (por cada 100 puntos)
    "ascendido": 0.15,       # a priori de un recién ascendido sin Elo (peor ataque y defensa)
    "peso_mercado": 0.75,    # 0 = solo modelo, 1 = solo cuotas de las casas
}

# Reglas de la porra
PUNTOS_EXACTO = 8    # aciertas el resultado exacto
PUNTOS_SIGNO = 3     # aciertas solo quién gana (o el empate)

MAX_GOLES = 10       # la matriz de marcadores llega hasta 10-10
MAX_PRONOSTICO = 6   # pero solo pronosticamos hasta 6-6


def inicio_temporada(dia):
    """1 de julio de la temporada que contiene 'dia'."""
    return date(dia.year if dia.month >= 7 else dia.year - 1, 7, 1)


class Modelo:
    def __init__(self, base, casa, ataque, defensa, priori):
        self.base, self.casa = base, casa
        self.ataque, self.defensa, self.priori = ataque, defensa, priori

    def _equipo(self, nombre):
        if nombre in self.ataque:
            return self.ataque[nombre], self.defensa[nombre]
        return self.priori.get(nombre, (0.0, 0.0))

    def lambdas(self, local, visitante):
        al, dl = self._equipo(local)
        av, dv = self._equipo(visitante)
        return (math.exp(self.base + self.casa + al + dv),
                math.exp(self.base + av + dl))


def ajustar(partidos, hoy, elo=None, equipos_extra=(), cfg=None):
    """Ajusta el modelo con los partidos jugados antes de 'hoy'.

    partidos: lista de dicts con fecha, local, visitante, gl, gv y opcionalmente tl, tv
              (tiros a puerta). elo: dict equipo -> Elo (opcional).
    equipos_extra: equipos que vamos a predecir aunque no tengan partidos (recién ascendidos).
    """
    cfg = {**CONFIG, **(cfg or {})}
    desde = hoy - timedelta(days=cfg["ventana_dias"])
    usados = [p for p in partidos if desde <= p["fecha"] < hoy]

    equipos = sorted({p["local"] for p in usados} | {p["visitante"] for p in usados}
                     | set(equipos_extra))
    idx = {e: i for i, e in enumerate(equipos)}
    n = len(equipos)

    # --- A priori de cada equipo: Elo si lo hay; si no, ¿es recién ascendido? ---
    temporada = inicio_temporada(hoy)
    veteranos = {p[k] for p in usados if p["fecha"] < temporada for k in ("local", "visitante")}
    elo = {e: v for e, v in (elo or {}).items() if e in idx}
    elo_medio = np.mean(list(elo.values())) if elo else 0
    priori = {}
    for e in equipos:
        if e in elo:
            z = (elo[e] - elo_medio) / 100 * cfg["elo_escala"]
            priori[e] = (z, -z)
        elif e not in veteranos and veteranos:
            priori[e] = (-cfg["ascendido"], cfg["ascendido"])
        else:
            priori[e] = (0.0, 0.0)
    pa = np.array([priori[e][0] for e in equipos])
    pd = np.array([priori[e][1] for e in equipos])

    if not usados:
        return Modelo(math.log(1.3), 0.25, {}, {}, priori)

    # --- Goles "mezclados" con tiros a puerta ---
    con_tiros = [p for p in usados if p.get("tl") is not None and p.get("tv") is not None]
    tiros = sum(p["tl"] + p["tv"] for p in con_tiros)
    conversion = sum(p["gl"] + p["gv"] for p in con_tiros) / tiros if tiros else 0
    alfa = cfg["peso_tiros"] if conversion else 0

    def mezcla(goles, tiros_puerta):
        if tiros_puerta is None:
            return goles
        return (1 - alfa) * goles + alfa * conversion * tiros_puerta

    loc = np.array([idx[p["local"]] for p in usados])
    vis = np.array([idx[p["visitante"]] for p in usados])
    yl = np.array([mezcla(p["gl"], p.get("tl")) for p in usados], dtype=float)
    yv = np.array([mezcla(p["gv"], p.get("tv")) for p in usados], dtype=float)
    dias = np.array([(hoy - p["fecha"]).days for p in usados], dtype=float)
    w = 0.5 ** (dias / cfg["semivida_dias"])
    ridge = cfg["ridge"]

    # --- Máxima verosimilitud de Poisson (con pesos) + penalización hacia el a priori ---
    # Cada fila de X dice qué parámetros suman en un "log λ":
    #   columnas = [base, casa, ataque de cada equipo..., defensa de cada equipo...]
    m = len(usados)
    filas = np.arange(m)
    X = np.zeros((2 * m, 2 + 2 * n))
    X[:, 0] = 1                                                   # base
    X[:m, 1] = 1                                                  # ventaja de casa (solo local)
    X[filas, 2 + loc] = X[m + filas, 2 + vis] = 1                 # ataque del que marca
    X[filas, 2 + n + vis] = X[m + filas, 2 + n + loc] = 1         # defensa del que encaja
    y, pesos = np.concatenate([yl, yv]), np.concatenate([w, w])
    priori_x = np.concatenate([[0, 0], pa, pd])
    penal = np.full(2 + 2 * n, ridge)
    penal[:2] = 0                                                 # base y casa sin penalizar

    def coste(x):
        eta = X @ x
        return np.sum(pesos * (np.exp(eta) - y * eta)) + np.sum(penal / 2 * (x - priori_x) ** 2)

    # Método de Newton: el problema es convexo, así que converge en pocas iteraciones
    x = np.concatenate([[math.log(1.2), 0.2], pa, pd])
    for _ in range(100):
        lam = np.exp(X @ x)
        gradiente = X.T @ (pesos * (lam - y)) + penal * (x - priori_x)
        hessiana = (X.T * (pesos * lam)) @ X + np.diag(penal)
        paso = np.linalg.solve(hessiana, gradiente)
        t, actual = 1.0, coste(x)
        while coste(x - t * paso) > actual and t > 1e-6:   # si el paso se pasa, lo acortamos
            t /= 2
        x = x - t * paso
        if np.max(np.abs(t * paso)) < 1e-9:
            break
    ataque = {e: x[2 + i] for e, i in idx.items()}
    defensa = {e: x[2 + n + i] for e, i in idx.items()}
    return Modelo(x[0], x[1], ataque, defensa, priori)


# ---------------------------------------------------------------- probabilidades


def matriz(lambda_local, lambda_visit, rho):
    """Probabilidad de cada marcador (filas = goles local, columnas = visitante)."""
    k = np.arange(MAX_GOLES + 1)
    fact = np.array([math.factorial(i) for i in k], dtype=float)
    pl = np.exp(-lambda_local) * lambda_local ** k / fact
    pv = np.exp(-lambda_visit) * lambda_visit ** k / fact
    m = np.outer(pl, pv)
    # Dixon-Coles: los marcadores bajos no son del todo independientes
    m[0, 0] *= max(1 - lambda_local * lambda_visit * rho, 0)
    m[0, 1] *= max(1 + lambda_local * rho, 0)
    m[1, 0] *= max(1 + lambda_visit * rho, 0)
    m[1, 1] *= max(1 - rho, 0)
    return m / m.sum()


def probabilidades_1x2(m):
    return float(np.tril(m, -1).sum()), float(np.trace(m)), float(np.triu(m, 1).sum())


def probabilidades_mercado(cuotas):
    """Cuotas decimales -> probabilidades (quitando el margen de la casa)."""
    q = [1 / cuotas["1"], 1 / cuotas["X"], 1 / cuotas["2"]]
    s = sum(q)
    res = {"1x2": [x / s for x in q]}
    if cuotas.get("mas25") and cuotas.get("menos25"):
        o, u = 1 / cuotas["mas25"], 1 / cuotas["menos25"]
        res["mas25"] = o / (o + u)
    return res


def lambdas_mercado(cuotas, rho, inicio=(1.4, 1.1)):
    """Goles esperados que encajan con las cuotas (1X2 y, si hay, más/menos de 2,5)."""
    mercado = probabilidades_mercado(cuotas)

    objetivo = list(mercado["1x2"]) + ([mercado["mas25"]] if "mas25" in mercado else [])

    def residuos(x):
        m = matriz(math.exp(x[0]), math.exp(x[1]), rho)
        r = list(probabilidades_1x2(m))
        if "mas25" in mercado:
            r.append(1 - sum(m[a, b] for a in range(3) for b in range(3 - a)))
        return np.array(r) - objetivo

    # Levenberg-Marquardt con derivadas numéricas (solo 2 incógnitas: log λ local y visitante)
    x, mu = np.log(np.array(inicio, dtype=float)), 1e-3
    r = residuos(x)
    for _ in range(100):
        J = np.column_stack([(residuos(x + h) - r) / 1e-6 for h in np.eye(2) * 1e-6])
        paso = np.linalg.solve(J.T @ J + mu * np.eye(2), -J.T @ r)
        r_nuevo = residuos(x + paso)
        if r_nuevo @ r_nuevo < r @ r:
            x, r, mu = x + paso, r_nuevo, mu / 3
            if np.max(np.abs(paso)) < 1e-7:
                break
        else:
            mu *= 4
            if mu > 1e6:
                break
    return math.exp(x[0]), math.exp(x[1])


def _signo(a, b):
    return "1" if a > b else ("X" if a == b else "2")


def puntos_porra(pronostico, real):
    """Puntos que da un pronóstico (a, b) si el resultado real es (c, d)."""
    if tuple(pronostico) == tuple(real):
        return PUNTOS_EXACTO
    return PUNTOS_SIGNO if _signo(*pronostico) == _signo(*real) else 0


def mejor_pronostico(m):
    """Marcador que maximiza los puntos esperados:
    E = 8·P(exacto) + 3·P(signo pero no exacto) = 3·P(signo) + 5·P(exacto)."""
    p = dict(zip("1X2", probabilidades_1x2(m)))

    def esperados(r):
        return PUNTOS_SIGNO * p[_signo(*r)] + (PUNTOS_EXACTO - PUNTOS_SIGNO) * m[r]

    mejor = max(((a, b) for a in range(MAX_PRONOSTICO + 1) for b in range(MAX_PRONOSTICO + 1)),
                key=esperados)
    return mejor, float(esperados(mejor))


def predecir(modelo, local, visitante, cuotas=None, cfg=None):
    """Pronóstico para la porra de un partido."""
    cfg = {**CONFIG, **(cfg or {})}
    rho = cfg["rho"]
    lm = modelo.lambdas(local, visitante)
    p_modelo = probabilidades_1x2(matriz(*lm, rho))

    lambdas, p_mercado = lm, None
    if cuotas and cfg["peso_mercado"] > 0:
        lk = lambdas_mercado(cuotas, rho, inicio=lm)
        p_mercado = probabilidades_1x2(matriz(*lk, rho))
        w = cfg["peso_mercado"]
        # mezcla en escala logarítmica (media geométrica ponderada)
        lambdas = tuple(math.exp((1 - w) * math.log(a) + w * math.log(b)) for a, b in zip(lm, lk))

    m = matriz(*lambdas, rho)
    resultado, puntos = mejor_pronostico(m)
    p1, px, p2 = probabilidades_1x2(m)
    return {
        "resultado": resultado,
        "puntos_esperados": puntos,
        "p_exacto": float(m[resultado]),
        "p1": p1, "px": px, "p2": p2,
        "goles_esperados": lambdas,
        "modelo": p_modelo,       # 1X2 solo con estadísticas
        "mercado": p_mercado,     # 1X2 según las casas (o None)
        "matriz": m,
    }
