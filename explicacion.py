# Genera dos frases que justifican cada pronóstico a partir de los números del modelo


def _razon(favorito, rival, fuerzas):
    """Por qué gana el favorito: elige su mejor argumento, el ataque o la defensa."""
    f, r = fuerzas.get(favorito), fuerzas.get(rival)
    if not f or not r:
        return "aún hay pocos datos de esta temporada, así que el modelo se apoya en la media de la liga"

    # Ventaja en ataque: su ataque contra la defensa rival (>1 = marcará más de lo normal)
    ventaja_ataque = f["ataque"] * r["defensa"]
    # Ventaja en defensa: cuanto peor ataque rival y mejor defensa propia, mayor (>1)
    ventaja_defensa = 1 / (f["defensa"] * r["ataque"])

    if ventaja_ataque >= ventaja_defensa:
        return (f"marca {f['gf_pj']:.1f} goles por partido y {rival} "
                f"encaja {r['gc_pj']:.1f}")
    return (f"encaja {f['gc_pj']:.1f} goles por partido y {rival} "
            f"marca {r['gf_pj']:.1f}")


def justificar(local, visitante, pred, fuerzas):
    """Devuelve dos frases: por qué ese signo y por qué ese marcador."""
    a, b = pred["resultado"]
    gl, gv = pred["goles_esperados"]

    # Frase 1: el signo (1, X o 2)
    if a > b:
        frase1 = (f"{local} parte como favorito en casa ({pred['p1']:.0%} de victoria): "
                  f"{_razon(local, visitante, fuerzas)}.")
    elif a < b:
        frase1 = (f"{visitante} es favorito incluso fuera ({pred['p2']:.0%} de victoria): "
                  f"{_razon(visitante, local, fuerzas)}.")
    else:
        frase1 = (f"Partido muy igualado: el modelo espera {gl:.1f} goles de {local} "
                  f"y {gv:.1f} de {visitante}, y el empate tiene un {pred['px']:.0%}.")

    # Frase 2: el marcador exacto
    frase2 = (f"Con {gl:.1f}-{gv:.1f} goles esperados, el {a}-{b} es el marcador más probable "
              f"de ese signo ({pred['p_exacto']:.0%}) y da {pred['puntos_esperados']:.1f} puntos esperados.")

    return f"{frase1} {frase2}"
