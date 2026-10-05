<div align="center">

# ⚽ Porra LaLiga

**Un agente que cada lunes predice todos los partidos de LaLiga de la semana y te los manda por Telegram.**

[![Porra semanal](https://github.com/EvaristoRuizHaro/porra-laliga/actions/workflows/porra.yml/badge.svg)](https://github.com/EvaristoRuizHaro/porra-laliga/actions/workflows/porra.yml)
![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Telegram](https://img.shields.io/badge/Telegram-bot-26A5E4?logo=telegram&logoColor=white)
![Licencia](https://img.shields.io/badge/licencia-MIT-green)

</div>

---

## 📲 Qué recibes

Cada lunes a las 7:47 (hora de España) llega un mensaje así:

```text
⚽ PORRA 05/10 - 11/10

Sáb 10/10 18:30 (J8)
  Barça 2-0 Getafe
  1: 81% | X: 11% | 2: 5%
  💬 Barça parte como favorito en casa (81% de victoria): encaja 1.0 goles por
  partido y Getafe marca 0.6. Con 3.0-0.6 goles esperados, el 2-0 es el marcador
  más probable de ese signo (12%) y da 2.8 puntos esperados.

Sáb 10/10 21:00 (J8)
  Real Madrid 2-1 Villarreal
  1: 65% | X: 17% | 2: 16%
  💬 Real Madrid parte como favorito en casa (65% de victoria): marca 2.6 goles
  por partido y Villarreal encaja 1.7. Con 2.7-1.3 goles esperados, el 2-1 es el
  marcador más probable de ese signo (9%) y da 2.2 puntos esperados.

📊 Puntos esperados esta semana: 17.1
```

Para cada partido: **marcador recomendado**, **probabilidades 1X2** y **dos frases que justifican la elección**.

## 🧠 Cómo funciona

El agente no adivina: usa un **modelo de Poisson**, el clásico de la estadística deportiva.

1. **Fuerza de cada equipo.** Con todos los partidos jugados esta temporada calcula el ataque y la defensa de cada equipo respecto a la media de la liga. Si un equipo lleva pocos partidos, sus valores se acercan a la media para no sacar conclusiones de dos jornadas.
2. **Goles esperados.** Combina el ataque de uno con la defensa del otro y la ventaja de jugar en casa:

   $$\lambda_{local} = \text{media}_{local} \times \text{ataque}_{local} \times \text{defensa}_{visitante}$$

3. **Probabilidad de cada marcador.** Con la distribución de Poisson calcula la probabilidad de cada resultado, del 0-0 al 6-6.
4. **Elige el marcador que más puntos da.** No elige el resultado más probable, sino el que maximiza los puntos esperados según las reglas de la porra:

   | Acierto | Puntos |
   |---|---|
   | Resultado exacto | 6 |
   | Solo el signo (1, X, 2) | 3 |

   $$E[\text{puntos}] = 3 \cdot \big(P(\text{signo}) + P(\text{exacto})\big)$$

Por eso casi nunca recomienda empates: aunque el 1-1 sea muy probable, apostar por el favorito suele dar más puntos de media.

## 🗂️ Estructura

| Archivo | Qué hace |
|---|---|
| `porra.py` | Punto de entrada: calcula la semana, predice y envía a Telegram |
| `datos.py` | Descarga partidos de [football-data.org](https://www.football-data.org) |
| `modelo.py` | Modelo de Poisson y elección del mejor marcador |
| `explicacion.py` | Genera las dos frases que justifican cada pronóstico |
| `obtener_chat_id.py` | Utilidad para averiguar tu `chat_id` de Telegram |
| `.github/workflows/porra.yml` | Ejecución automática cada lunes |

## 🚀 Ponerlo en marcha

### 1. Claves necesarias (gratis)

- **football-data.org**: regístrate en [football-data.org/client/register](https://www.football-data.org/client/register) y te llega la clave por email.
- **Bot de Telegram**: crea uno con [@BotFather](https://t.me/BotFather) (`/newbot`) y guarda el token.

### 2. En local

```bash
git clone https://github.com/EvaristoRuizHaro/porra-laliga.git
cd porra-laliga
python -m venv venv
venv\Scripts\activate          # Windows  (en Linux/macOS: source venv/bin/activate)
pip install -r requirements.txt
cp .env.example .env           # y rellénalo con tus claves
```

Escríbele "hola" a tu bot y averigua tu `chat_id`:

```bash
python obtener_chat_id.py
```

Y lanza la porra:

```bash
python porra.py                # semana actual
python porra.py 2026-10-12     # cualquier otra semana (vale cualquier día de ella)
```

### 3. Automático con GitHub Actions

1. Haz un fork de este repositorio.
2. En **Settings → Secrets and variables → Actions** añade `FOOTBALL_DATA_KEY`, `TELEGRAM_TOKEN` y `TELEGRAM_CHAT_ID`.
3. Listo: se ejecuta cada lunes a las 7:47 (hora de Madrid, con el cambio de hora ya contemplado). Para probarlo al momento, entra en **Actions → Porra semanal → Run workflow**.

> 💡 ¿Lo quieres para tu grupo de amigos? Mete el bot en el grupo, escribe algo allí y usa como `TELEGRAM_CHAT_ID` el id del grupo (empieza por `-`).

## ⚠️ Aviso

Proyecto hecho por diversión para una porra entre amigos. Las predicciones son estadísticas, no consejos de apuestas.

## 📄 Licencia

[MIT](LICENSE) © Evaristo Ruiz Haro
