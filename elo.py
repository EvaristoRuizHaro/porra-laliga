# Elo propio a partir de resultados de Primera y Segunda (sin depender de webs externas).
# Cada partido mueve puntos del perdedor al ganador; más puntos si la victoria era inesperada
# o por goleada. Los equipos de Segunda empiezan más abajo y, con los ascensos y descensos,
# el sistema aprende solo cuánto peor es Segunda.

INICIAL = {"SP1": 1500, "SP2": 1350}  # Elo con el que aparece un equipo nuevo
K = 20              # cuánto se mueve el Elo en cada partido
VENTAJA_CASA = 60   # puntos Elo que vale jugar en casa
REGRESION = 0.15    # en verano, cada equipo se acerca un 15 % a la media de su liga


def _multiplicador(diferencia):
    """Ganar por más goles mueve más puntos (como el Elo de selecciones)."""
    d = abs(diferencia)
    return 1 if d <= 1 else 1.5 if d == 2 else (11 + d) / 8


def calcular(partidos, hasta, inicial=None, defecto=1500, sin_liga=("EUR",)):
    """Elo de cada equipo con los partidos jugados antes de 'hasta'.
    partidos: dicts con fecha, local, visitante, gl, gv y 'liga' (por defecto 'SP1').
    inicial: Elo con el que aparece un equipo nuevo según su liga (por defecto INICIAL).
    sin_liga: 'ligas' que no son ligas (p. ej. la Champions): sus partidos no cambian la liga
    del equipo ni se regresan a ninguna media; sirven de puente entre ligas."""
    inicial = inicial or INICIAL
    elo, liga_de, temporada = {}, {}, None
    for p in sorted(partidos, key=lambda p: p["fecha"]):
        if p["fecha"] >= hasta:
            break
        t = p["fecha"].year if p["fecha"].month >= 7 else p["fecha"].year - 1
        if temporada is not None and t != temporada:
            # cambio de temporada: regresión hacia la media de cada liga
            # (la media de la liga se conserva, así lo aprendido entre ligas no se pierde)
            for liga in set(liga_de.values()) - set(sin_liga):
                equipos = [e for e in elo if liga_de[e] == liga]
                media = sum(elo[e] for e in equipos) / len(equipos)
                for e in equipos:
                    elo[e] += REGRESION * (media - elo[e])
        temporada = t
        liga = p.get("liga", "SP1")
        for e in (p["local"], p["visitante"]):
            if e not in elo:
                elo[e] = inicial.get(liga, defecto)
                liga_de[e] = liga
            elif liga not in sin_liga:
                liga_de[e] = liga          # ascensos y descensos
        ventaja = 0 if p.get("neutral") else VENTAJA_CASA
        esperado = 1 / (1 + 10 ** ((elo[p["visitante"]] - elo[p["local"]] - ventaja) / 400))
        real = 1 if p["gl"] > p["gv"] else 0.5 if p["gl"] == p["gv"] else 0
        cambio = K * _multiplicador(p["gl"] - p["gv"]) * (real - esperado)
        elo[p["local"]] += cambio
        elo[p["visitante"]] -= cambio
    return elo
