# Agente de la porra: predice todos los partidos de LaLiga de esta semana (lunes a domingo)
#   Uso normal:          python porra.py
#   Probar otra semana:  python porra.py 2026-10-12      (cualquier día de esa semana)
import os
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

from datos import nombre, partidos_entre, partidos_terminados
from explicacion import justificar
from modelo import calcular_fuerzas, predecir

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
    # Si pasas una fecha por consola usamos esa semana; si no, la actual
    dia = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else datetime.now(MADRID).date()
    lunes, domingo = semana_de(dia)
    print(f"Semana del {lunes} al {domingo}")

    fuerzas, media_local, media_visit = calcular_fuerzas(partidos_terminados())
    partidos = partidos_entre(lunes.isoformat(), domingo.isoformat())
    partidos.sort(key=lambda p: p["utcDate"])

    if not partidos:
        mensaje = f"⚽ Esta semana ({lunes:%d/%m} - {domingo:%d/%m}) no hay partidos de LaLiga."
        print(mensaje)
        enviar_telegram(mensaje)
        return

    lineas = [f"⚽ PORRA {lunes:%d/%m} - {domingo:%d/%m}"]
    total = 0
    for p in partidos:
        local, visit = nombre(p["homeTeam"]), nombre(p["awayTeam"])
        fecha = datetime.fromisoformat(p["utcDate"].replace("Z", "+00:00")).astimezone(MADRID)
        pred = predecir(local, visit, fuerzas, media_local, media_visit)
        a, b = pred["resultado"]
        total += pred["puntos_esperados"]
        lineas.append(
            f"{DIAS[fecha.weekday()]} {fecha:%d/%m %H:%M} (J{p['matchday']})\n"
            f"  {local} {a}-{b} {visit}\n"
            f"  1: {pred['p1']:.0%} | X: {pred['px']:.0%} | 2: {pred['p2']:.0%}\n"
            f"  💬 {justificar(local, visit, pred, fuerzas)}"
        )

    lineas.append(f"📊 Puntos esperados esta semana: {total:.1f}")
    mensaje = "\n\n".join(lineas)
    print(mensaje)
    enviar_telegram(mensaje)


if __name__ == "__main__":
    main()
