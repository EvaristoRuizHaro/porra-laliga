# Agente de la porra: predice todos los partidos de LaLiga y de Champions de esta semana
# (lunes a domingo)
#   Uso normal:          python porra.py
#   Probar otra semana:  python porra.py 2026-10-12      (cualquier día de esa semana)
#   Sin enviar ni tocar el historial:  python porra.py --prueba
import os
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

import champions
import datos
import historial
from explicacion import estadisticas, justificar, justificar_champions
from modelo import ajustar, predecir

load_dotenv()
MADRID = ZoneInfo("Europe/Madrid")
DIAS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
LIMITE_TELEGRAM = 4000  # Telegram admite 4096 caracteres por mensaje; dejamos margen
FASES_CHAMPIONS = {"PLAYOFFS": "playoff", "LAST_16": "octavos", "QUARTER_FINALS": "cuartos",
                   "SEMI_FINALS": "semifinal", "FINAL": "final"}


def _trozos(texto):
    """Parte el texto en mensajes que quepan en Telegram, sin cortar un partido a la mitad."""
    trozos, actual = [], ""
    for bloque in texto.split("\n\n"):
        if actual and len(actual) + len(bloque) + 2 > LIMITE_TELEGRAM:
            trozos.append(actual)
            actual = bloque
        else:
            actual = f"{actual}\n\n{bloque}" if actual else bloque
    return trozos + [actual]


def enviar_telegram(texto):
    for trozo in _trozos(texto):
        r = requests.post(
            f"https://api.telegram.org/bot{os.getenv('TELEGRAM_TOKEN')}/sendMessage",
            json={"chat_id": os.getenv("TELEGRAM_CHAT_ID"), "text": trozo},
            timeout=30,
        )
        r.raise_for_status()  # si el token o el chat_id están mal, lo veremos aquí


def semana_de(dia):
    """Lunes y domingo de la semana que contiene 'dia'."""
    lunes = dia - timedelta(days=dia.weekday())
    return lunes, lunes + timedelta(days=6)


def etiqueta(p):
    """(J8) en LaLiga; (🏆 Champions J3) o (🏆 Champions cuartos) en Champions."""
    if p["competicion"] == "PD":
        return f"J{p['matchday']}"
    fase = FASES_CHAMPIONS.get(p.get("stage"))
    return f"🏆 Champions {fase or 'J' + str(p.get('matchday') or '?')}"


def partidos_champions(lunes, domingo):
    try:
        return datos.partidos_entre(lunes.isoformat(), domingo.isoformat(), "CL")
    except Exception as e:
        datos._avisar(f"Calendario de Champions no disponible ({e.__class__.__name__})")
        return []


def predecir_laliga(partidos, jugados, corte):
    """Pronósticos de LaLiga con el modelo de Poisson. Devuelve {id: (pred, justificación, hay_cuotas)}."""
    equipos = {p[k] for p in partidos for k in ("local", "visitante")}
    modelo = ajustar(jugados, corte, elo=datos.elo(corte, jugados), equipos_extra=equipos)
    cuotas = datos.cuotas_semana()
    stats = estadisticas(jugados, corte)
    res = {}
    for p in partidos:
        c = cuotas.get((p["local"], p["visitante"]))
        pred = predecir(modelo, p["local"], p["visitante"], cuotas=c)
        local, visit = datos.nombre(p["homeTeam"]), datos.nombre(p["awayTeam"])
        res[p["id"]] = (pred, justificar(p, local, visit, pred, modelo, stats), c is not None)
    return res


def predecir_champions(partidos, corte):
    """Pronósticos de Champions con el Elo europeo + cuotas. Devuelve {id: (pred, justificación, hay_cuotas)}."""
    elos = datos.elo_europa(corte)
    if not elos:
        datos._avisar("Elo europeo no disponible: en Champions solo cuentan las cuotas")
    try:
        cuotas = champions.emparejar_cuotas(partidos, datos.eventos_odds_api("CL"))
        print(f"Cuotas de Champions: {len(cuotas)}/{len(partidos)} partidos")
    except Exception as e:
        print(f"Cuotas de Champions no disponibles ({e.__class__.__name__})")
        cuotas = {}
    res, sin_datos = {}, []
    for p in partidos:
        c = cuotas.get(p["id"])
        pred, el, ev = champions.predecir_partido(p, elos, c)
        local, visit = datos.nombre(p["homeTeam"]), datos.nombre(p["awayTeam"])
        if elos:
            for nombre, e in ((local, el), (visit, ev)):
                if e is None:
                    print(f"⚠️  Sin Elo para '{nombre}' (añádelo a ALIAS_ELO en champions.py)")
        if c is None and (el is None or ev is None):
            sin_datos.append(f"{local}-{visit}")
        res[p["id"]] = (pred, justificar_champions(local, visit, pred, el, ev), c is not None)
    if sin_datos:
        datos._avisar("Champions sin Elo ni cuotas (pronóstico a ciegas): " + ", ".join(sin_datos))
    return res


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    prueba = "--prueba" in sys.argv
    hoy = datetime.now(MADRID).date()
    lunes, domingo = semana_de(date.fromisoformat(args[0]) if args else hoy)
    corte = min(hoy, lunes)  # solo usamos partidos jugados antes de empezar la semana
    print(f"Semana del {lunes} al {domingo}")

    liga = datos.partidos_entre(lunes.isoformat(), domingo.isoformat())
    copa = partidos_champions(lunes, domingo)
    partidos = sorted(liga + copa, key=lambda p: p["utcDate"])
    jugados, terminados_api = datos.historico(corte)
    try:  # resultados de Champions para apuntarlos en el historial
        terminados_api = terminados_api + datos.terminados_api(competicion="CL")
    except Exception as e:
        print(f"Resultados de Champions no disponibles ({e.__class__.__name__})")

    # Historial: apuntamos resultados de semanas anteriores y sacamos el balance
    filas = historial.cargar()
    historial.apuntar_resultados(filas, terminados_api)
    balance = historial.resumen(filas, lunes)

    if not partidos:
        lineas = [f"⚽ Esta semana ({lunes:%d/%m} - {domingo:%d/%m}) no hay partidos de LaLiga "
                  f"ni de Champions."]
    else:
        preds = {}
        if liga:
            preds.update(predecir_laliga(liga, jugados, corte))
        if copa:
            try:
                preds.update(predecir_champions(copa, corte))
            except Exception as e:  # que un fallo de Champions no impida enviar LaLiga
                datos._avisar(f"No se pudo pronosticar la Champions ({e.__class__.__name__}: {e})")
                partidos = [p for p in partidos if p["id"] in preds]
                copa = []

        titulo = "LaLiga + Champions" if liga and copa else "Champions" if copa else ""
        lineas = [f"⚽ PORRA {lunes:%d/%m} - {domingo:%d/%m}" + (f" ({titulo})" if titulo else "")]
        total, con_cuotas, nuevas = 0, 0, []
        for p in partidos:
            pred, porque, hay_cuotas = preds[p["id"]]
            local, visit = datos.nombre(p["homeTeam"]), datos.nombre(p["awayTeam"])
            fecha = datos._fecha_api(p).astimezone(MADRID)
            a, b = pred["resultado"]
            total += pred["puntos_esperados"]
            con_cuotas += hay_cuotas
            nuevas.append(historial.fila(p, pred, fecha.date()))
            lineas.append(
                f"{DIAS[fecha.weekday()]} {fecha:%d/%m %H:%M} ({etiqueta(p)})\n"
                f"  {local} {a}-{b} {visit}\n"
                f"  1: {pred['p1']:.0%} | X: {pred['px']:.0%} | 2: {pred['p2']:.0%}\n"
                f"  💬 {porque}"
            )
        lineas.append(f"📊 Puntos esperados esta semana: {total:.1f}"
                      f"\n💶 Cuotas de las casas en {con_cuotas}/{len(partidos)} partidos")
        historial.anadir(filas, nuevas)

    if balance:
        lineas.append(balance)
    if datos.avisos:
        lineas.append("⚠️ " + " · ".join(datos.avisos))

    mensaje = "\n\n".join(lineas)
    print(mensaje)
    if prueba:
        print("\n(--prueba: no se envía a Telegram ni se guarda el historial)")
        return
    historial.guardar(filas)
    enviar_telegram(mensaje)


if __name__ == "__main__":
    main()
