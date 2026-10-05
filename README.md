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
  1: 78% | X: 16% | 2: 7%
  💬 Barça parte como favorito en casa (78% de victoria): encaja 1.0 goles por
  partido y Getafe marca 0.6. Las casas de apuestas lo ven parecido (1: 77% |
  X: 16% | 2: 7%). Con 2.5-0.6 goles esperados, el 2-0 es el marcador más
  probable de ese signo (14%) y da 2.7 puntos esperados.

📊 Puntos esperados esta semana: 16.6
💶 Cuotas de las casas en 9/9 partidos

📒 Semana pasada: 21 pts (6/10 signos, 1 exactos; el modelo esperaba 19.8)
🏆 Temporada: 118 pts en 60 partidos (1.97 por partido, 53% de signos)
```

Para cada partido: **marcador recomendado**, **probabilidades 1X2**, **por qué** y **qué dicen las casas de apuestas**. Al final, el **balance real** de la semana pasada y de la temporada.

## 🧠 Cómo funciona

1. **Datos** (todos gratis):
   | Fuente | Qué aporta |
   |---|---|
   | [football-data.org](https://www.football-data.org) | Calendario de la semana y resultados al momento |
   | [football-data.co.uk](https://www.football-data.co.uk) | Resultados, **tiros a puerta** y cuotas de esta temporada y la pasada |
   | [ClubElo](http://clubelo.com) | **Elo** de cada club (también de Segunda, para los recién ascendidos). Si está caído, el agente calcula su propio Elo con los resultados de Primera y Segunda |
   | [The Odds API](https://the-odds-api.com) *(opcional)* | **Cuotas** de los partidos de la semana |

   Si una fuente falla, el agente sigue con las demás y lo avisa al final del mensaje.

2. **Fuerza de cada equipo.** Cada equipo tiene un ataque y una defensa, ajustados por máxima verosimilitud con un modelo de Poisson:

   $$\lambda_{local} = e^{\,\text{base} + \text{casa} + \text{ataque}_{local} + \text{defensa}_{visitante}}$$

   - Usa **las dos últimas temporadas**, pero un partido de hace un año cuenta la mitad que uno de hoy.
   - Mezcla los goles con los **tiros a puerta** (80/20): los goles tienen mucha suerte, los tiros menos.
   - Parte de un **a priori por Elo**: con pocos partidos, un equipo se parece a lo que dice su Elo, no a "la media".

3. **Corrección Dixon-Coles.** Poisson infravalora los 0-0 y 1-1; esta corrección lo arregla.

4. **Mezcla con las casas de apuestas.** Si hay cuotas, se calculan los goles esperados que implican y se mezclan con los del modelo (75 % casas, 25 % modelo). Las cuotas ya incluyen lesiones y alineaciones, que el modelo no ve.

5. **Elige el marcador que más puntos da**, no el más probable:

   | Acierto | Puntos |
   |---|---|
   | Resultado exacto | 6 |
   | Solo el signo (1, X, 2) | 3 |

   $$E[\text{puntos}] = 3 \cdot \big(P(\text{signo}) + P(\text{exacto})\big)$$

6. **Historial.** Cada pronóstico se guarda en `historial.csv`; el lunes siguiente se apunta el resultado real y los puntos.

## 📈 ¿Funciona?

`backtest.py` simula cada lunes de temporadas pasadas usando solo lo que se sabía ese día. En las temporadas 2022-23 a 2025-26 (1.520 partidos):

| Versión | Puntos por partido | Signo | Exacto |
|---|---|---|---|
| Modelo inicial (solo goles de esta temporada) | 1,88 | 49,7 % | 12,8 % |
| Modelo nuevo, solo estadísticas | 2,01 | 53,5 % | 13,6 % |
| Modelo nuevo + cuotas | **2,06** | **54,3 %** | **14,2 %** |

En una semana de 10 partidos son ~1,8 puntos más que la versión inicial. Los hiperparámetros (`CONFIG` en `modelo.py`) se ajustaron con 2015-2022 y se validaron con 2022-2026.

```bash
python backtest.py      # repite el backtest con los CSV de football-data.co.uk
```

## 🗂️ Estructura

| Archivo | Qué hace |
|---|---|
| `porra.py` | Punto de entrada: calcula la semana, predice, guarda el historial y envía a Telegram |
| `datos.py` | Descarga resultados, tiros, cuotas y Elo de las distintas fuentes |
| `elo.py` | Calcula un Elo propio con Primera y Segunda si ClubElo no responde |
| `nombres.py` | Traduce los nombres de los equipos de cada fuente a uno común |
| `modelo.py` | Modelo de Poisson con Elo, tiros, Dixon-Coles y cuotas; elige el mejor marcador |
| `explicacion.py` | Genera las frases que justifican cada pronóstico |
| `historial.py` | Guarda pronósticos y resultados en `historial.csv` y calcula el balance |
| `backtest.py` | Evalúa el modelo en temporadas pasadas |
| `obtener_chat_id.py` | Utilidad para averiguar tu `chat_id` de Telegram |
| `.github/workflows/porra.yml` | Ejecución automática cada lunes |

## 🚀 Ponerlo en marcha

### 1. Claves necesarias (gratis)

- **football-data.org**: regístrate en [football-data.org/client/register](https://www.football-data.org/client/register) y te llega la clave por email.
- **Bot de Telegram**: crea uno con [@BotFather](https://t.me/BotFather) (`/newbot`) y guarda el token.
- *(Opcional)* **The Odds API**: regístrate en [the-odds-api.com](https://the-odds-api.com) (plan gratis, 500 créditos al mes; el agente gasta 2 por semana). Sin ella se usan las cuotas de football-data.co.uk, que no siempre están el lunes.

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
python porra.py --prueba       # solo muestra el mensaje (no envía ni guarda historial)
python porra.py                # semana actual
python porra.py 2026-10-12     # cualquier otra semana (vale cualquier día de ella)
```

### 3. Automático con GitHub Actions

1. Haz un fork de este repositorio.
2. En **Settings → Secrets and variables → Actions** añade `FOOTBALL_DATA_KEY`, `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID` y, si la tienes, `ODDS_API_KEY`.
3. Listo: se ejecuta cada lunes a las 7:47 (hora de Madrid, con el cambio de hora ya contemplado) y sube `historial.csv` al repositorio. Para probarlo al momento, entra en **Actions → Porra semanal → Run workflow**.

> 💡 ¿Lo quieres para tu grupo de amigos? Mete el bot en el grupo, escribe algo allí y usa como `TELEGRAM_CHAT_ID` el id del grupo (empieza por `-`).

## ⚠️ Aviso

Proyecto hecho por diversión para una porra entre amigos. Las predicciones son estadísticas, no consejos de apuestas.

## 📄 Licencia

[MIT](LICENSE) © Evaristo Ruiz Haro
