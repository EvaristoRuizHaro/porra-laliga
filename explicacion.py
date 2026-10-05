# Genera dos o tres frases que justifican cada pronóstico a partir de los números del modelo
from modelo import inicio_temporada


def estadisticas(partidos, hoy):
    """Goles y tiros a puerta por partido de cada equipo en la temporada actual."""
    desde = inicio_temporada(hoy)
    eq = {}
    for p in partidos:
        if not desde <= p["fecha"] < hoy:
            continue
        for equipo, gf, gc, tp in ((p["local"], p["gl"], p["gv"], p.get("tl")),
                                   (p["visitante"], p["gv"], p["gl"], p.get("tv"))):
            e = eq.setdefault(equipo, {"pj": 0, "gf": 0, "gc": 0, "tp": 0, "pj_tiros": 0})
            e["pj"] += 1
            e["gf"] += gf
            e["gc"] += gc
            if tp is not None:
                e["tp"] += tp
                e["pj_tiros"] += 1
    return eq


def _razon(favorito, rival, modelo, stats):
    """Por qué gana el favorito: su mejor argumento, ataque o defensa.
    favorito y rival son tuplas (nombre interno, nombre para mostrar)."""
    (favorito, _), (rival, rival_txt) = favorito, rival
    f, r = stats.get(favorito), stats.get(rival)
    if not f or not r or min(f["pj"], r["pj"]) < 3:
        return "con pocos partidos esta temporada, pesan su Elo y la temporada pasada"
    fa, fd = modelo._equipo(favorito)
    ra, rd = modelo._equipo(rival)
    gf, gc = f["gf"] / f["pj"], f["gc"] / f["pj"]
    rgf, rgc = r["gf"] / r["pj"], r["gc"] / r["pj"]
    # Ventaja en ataque: su ataque + la defensa rival; en defensa: lo contrario
    if fa + rd >= -(fd + ra):
        if gf >= 1.3 or rgc >= 1.3:   # solo si los números de esta temporada lo respaldan
            texto = f"marca {gf:.1f} goles por partido y {rival_txt} encaja {rgc:.1f}"
            if f["pj_tiros"]:
                texto += f" ({f['tp'] / f['pj_tiros']:.1f} tiros a puerta por partido)"
            return texto
    elif gc <= 1.2 or rgf <= 1.0:
        return f"encaja {gc:.1f} goles por partido y {rival_txt} marca {rgf:.1f}"
    return "pesa más su nivel (Elo y temporada pasada) que cómo ha empezado la temporada"


def _frase_mercado(pred):
    if not pred["mercado"]:
        return ""
    m1, mx, m2 = pred["mercado"]
    e1, ex, e2 = pred["modelo"]
    mayor = max(("1", m1, e1), ("X", mx, ex), ("2", m2, e2), key=lambda t: abs(t[1] - t[2]))
    if abs(mayor[1] - mayor[2]) < 0.08:
        return f" Las casas de apuestas lo ven parecido (1: {m1:.0%} | X: {mx:.0%} | 2: {m2:.0%})."
    return (f" Ojo: las casas dan al {mayor[0]} un {mayor[1]:.0%} y las estadísticas un "
            f"{mayor[2]:.0%}; el pronóstico mezcla ambos.")


def justificar(partido, local, visitante, pred, modelo, stats):
    """Por qué ese signo, qué dicen las casas y por qué ese marcador.
    local y visitante son los nombres para mostrar; partido trae los internos."""
    eq_local, eq_visit = (partido["local"], local), (partido["visitante"], visitante)
    a, b = pred["resultado"]
    gl, gv = pred["goles_esperados"]

    if a > b:
        frase1 = (f"{local} parte como favorito en casa ({pred['p1']:.0%} de victoria): "
                  f"{_razon(eq_local, eq_visit, modelo, stats)}.")
    elif a < b:
        frase1 = (f"{visitante} es favorito incluso fuera ({pred['p2']:.0%} de victoria): "
                  f"{_razon(eq_visit, eq_local, modelo, stats)}.")
    else:
        frase1 = (f"Partido muy igualado: se esperan {gl:.1f} goles de {local} "
                  f"y {gv:.1f} de {visitante}, y el empate tiene un {pred['px']:.0%}.")

    frase2 = (f" Con {gl:.1f}-{gv:.1f} goles esperados, el {a}-{b} es el marcador más probable "
              f"de ese signo ({pred['p_exacto']:.0%}) y da {pred['puntos_esperados']:.1f} puntos esperados.")
    return frase1 + _frase_mercado(pred) + frase2
