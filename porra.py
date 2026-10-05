# Agente de la porra: predice todos los partidos de LaLiga de esta semana (lunes a domingo)
#   Uso normal:          python porra.py
#   Probar otra semana:  python porra.py 2026-10-12      (cualquier día de esa semana)
#   Sin enviar ni tocar el historial:  python porra.py --prueba
import os
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

import datos
import historial
from explicacion import estadisticas, justificar
from modelo import ajustar, predecir

load_dotenv()
MADRID = ZoneInfo("Europe/Madrid")
DIAS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
LIMITE_TELEGRAM = 4000  # Telegram admite 4096 caracteres por mensaje; dejamos margen


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


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    prueba = "--prueba" in sys.argv
    hoy = datetime.now(MADRID).date()
    lunes, domingo = semana_de(date.fromisoformat(args[0]) if args else hoy)
    corte = min(hoy, lunes)  # solo usamos partidos jugados antes de empezar la semana
    print(f"Semana del {lunes} al {domingo}")

    partidos = datos.partidos_entre(lunes.isoformat(), domingo.isoformat())
    partidos.sort(key=lambda p: p["utcDate"])
    jugados, terminados_api = datos.historico(corte)

    # Historial: apuntamos resultados de semanas anteriores y sacamos el balance
    filas = historial.cargar()
    historial.apuntar_resultados(filas, terminados_api)
    balance = historial.resumen(filas, lunes)

    if not partidos:
        lineas = [f"⚽ Esta semana ({lunes:%d/%m} - {domingo:%d/%m}) no hay partidos de LaLiga."]
    else:
        equipos = {p[k] for p in partidos for k in ("local", "visitante")}
        modelo = ajustar(jugados, corte, elo=datos.elo(corte, jugados), equipos_extra=equipos)
        cuotas = datos.cuotas_semana()
        stats = estadisticas(jugados, corte)

        lineas = [f"⚽ PORRA {lunes:%d/%m} - {domingo:%d/%m}"]
        total, con_cuotas, nuevas = 0, 0, []
        for p in partidos:
            local, visit = datos.nombre(p["homeTeam"]), datos.nombre(p["awayTeam"])
            fecha = datos._fecha_api(p).astimezone(MADRID)
            c = cuotas.get((p["local"], p["visitante"]))
            con_cuotas += c is not None
            pred = predecir(modelo, p["local"], p["visitante"], cuotas=c)
            a, b = pred["resultado"]
            total += pred["puntos_esperados"]
            nuevas.append(historial.fila(p, pred, fecha.date()))
            lineas.append(
                f"{DIAS[fecha.weekday()]} {fecha:%d/%m %H:%M} (J{p['matchday']})\n"
                f"  {local} {a}-{b} {visit}\n"
                f"  1: {pred['p1']:.0%} | X: {pred['px']:.0%} | 2: {pred['p2']:.0%}\n"
                f"  💬 {justificar(p, local, visit, pred, modelo, stats)}"
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
