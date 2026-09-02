[![Chequear butacas La Odisea IMAX Norcenter](https://github.com/matiszpek/imax-odisea-bot/actions/workflows/check-seats.yml/badge.svg)](https://github.com/matiszpek/imax-odisea-bot/actions/workflows/check-seats.yml)

# Bot de butacas — La Odisea, IMAX Theatre (Norcenter)

Cada 10 minutos revisa las funciones IMAX de **La Odisea** en el
**IMAX Theatre (Norcenter)** de Showcase, dentro de un rango horario
(por defecto **16:00 a 24:00**), y manda un email cuando encuentra un
par de butacas contiguas y bien centradas. Avisa **una sola vez por
función**.

## Estado actual

- ✅ **Todo el flujo funciona y está probado en vivo** (07/09/2026): login
  con cuenta de Showcase, lectura de la grilla (`op_data`), navegación a
  cada función, extracción del mapa de butacas y envío del email.
- El sitio **exige iniciar sesión** (DNI/email + contraseña, sin opción de
  invitado) para llegar al mapa de butacas — por eso el bot usa una
  cuenta de Showcase (`SHOWCASE_USER` / `SHOWCASE_PASS`).
- Pendiente fino: la clasificación horizontal de butacas (bloques /
  pasillos) está calibrada solo contra la fila I/J/K; ver sección 6.

## Estructura

```
scraper.py       -> login + lee op_data + navega a cada función + extrae el mapa de butacas
seat_ranking.py  -> decide qué asientos son "los mejores" (más centrados)
notifier.py      -> arma y envía el email de aviso
main.py          -> orquesta todo; maneja el "avisar una sola vez"
state/notified.json -> qué funciones ya se avisaron (lo actualiza el propio bot)
requirements.txt -> dependencias
.github/workflows/check-seats.yml -> programa la corrida en GitHub Actions
```

## Datos del sitio que ya relevamos (02/09/2026)

- "La Odisea" es `filmid=5875`.
- IMAX Theatre (Norcenter) es el cine con `id=18`; formato
  "IMAX-Subtitulado" (`showId=86868A`).
- Elegir un horario arma una URL directa:
  `pelicula.aspx?filmid=5875&perf=<id>&cinema=18&date=<YYYY-MM-DD>&show=86868A`
  — pero si no estás logueado, te patea a `ingresar.aspx`.
- Campos de login: `#ctl00_Contenido_txtIdOrMail`, `#ctl00_Contenido_txtpass`,
  botón `#ctl00_Contenido_btnGet`. No hay captcha.

Si el bot deja de encontrar funciones, lo primero a revisar es si
`filmid` sigue siendo 5875 (mirá la URL de "La Odisea" en la cartelera).
Se puede pisar sin tocar código con la variable `SHOWCASE_FILM_ID`.

## 1. Probar en tu compu primero

```bash
pip install -r requirements.txt
playwright install chromium
```

Definí las variables de entorno y corré el scraper con el navegador
visible (`HEADLESS=0`):

```bash
# PowerShell (Windows)
$env:SHOWCASE_USER="tu_dni_o_email"
$env:SHOWCASE_PASS="tu_password_de_showcase"
$env:HEADLESS="0"
python scraper.py
```

```bash
# bash / macOS / Linux
SHOWCASE_USER="tu_dni_o_email" SHOWCASE_PASS="tu_password_de_showcase" HEADLESS=0 python scraper.py
```

Mirá que:

1. **Login**: llena DNI/email y contraseña y entra (deja de verse el
   campo de contraseña). Si falla, revisá las credenciales; el bot
   imprime el mensaje de error del sitio.
2. **Grilla**: imprime "Funciones IMAX encontradas en la grilla: N".
   Esto ya sabemos que anda.
3. **Cada función en rango**: navega a su URL y llega al mapa de butacas
   (ya probado). Si alguna vez cambia el sitio y falla, tira un
   `TimeoutError` con un dump de HTML para ver qué ajustar en
   `_intentar_setear_cantidad` / `_navegar_hasta_mapa` en `scraper.py`.

Al final deberías ver algo así:

```
=== Resumen ===
2026-09-02 16:15 (IMAX-Subtitulado): 19 disponibles
    B-3
    B-4
    ...
```

Después probá el flujo completo (incluye ranking + estado, pero NO
manda email si no configuraste Gmail):

```bash
python main.py
```

## 2. Configurar el email (Gmail)

1. Google → Seguridad → Verificación en 2 pasos (activala).
2. Contraseñas de aplicación: https://myaccount.google.com/apppasswords
3. Generá una (nombre tipo "bot-imax"), copiá el código de 16
   caracteres (sin espacios). No es tu contraseña normal de Gmail.

## 3. Subir a GitHub y configurar secrets

1. Creá un repositorio nuevo. **Recomendación: dejarlo PÚBLICO**, así
   GitHub Actions es ilimitado. En un repo privado, el plan gratis da
   2000 min/mes y este bot (cada 10 min) se pasa — ahí subí el cron a
   `*/20` o `*/30` en `check-seats.yml`.
2. Subí todos los archivos (incluido `state/notified.json`).
3. **Settings → Secrets and variables → Actions → New repository secret**,
   creá estos cinco:

   | Nombre               | Valor                                           |
   |----------------------|-------------------------------------------------|
   | `SHOWCASE_USER`      | DNI o email de tu cuenta de Showcase            |
   | `SHOWCASE_PASS`      | la contraseña de esa cuenta                     |
   | `GMAIL_USER`         | tu email de Gmail, ej. `tucuenta@gmail.com`     |
   | `GMAIL_APP_PASSWORD` | la contraseña de aplicación de 16 caracteres    |
   | `NOTIFY_TO`          | a qué email(s) avisar (coma para varios)        |

4. **Actions → "Chequear butacas La Odisea IMAX Norcenter" → Run workflow**
   para probarlo a mano. Mirá los logs.
5. El workflow necesita permiso de escritura para guardar
   `state/notified.json` de vuelta (ya está en el YAML como
   `permissions: contents: write`). Si tu organización lo bloquea:
   **Settings → Actions → General → Workflow permissions → Read and write**.

## 3b. Que corra solo cada 10 minutos

El archivo `.github/workflows/check-seats.yml` ya trae:

```yaml
on:
  schedule:
    - cron: "*/10 * * * *"   # cada 10 min (horario UTC)
  workflow_dispatch:          # además, botón manual
```

Para que el cron se active **no hay que tocar nada más**, pero sí que se
cumplan estas condiciones:

1. **El `.yml` tiene que estar en la rama por defecto del repo** (en tu
   caso `master`). GitHub solo dispara `schedule` desde esa rama. Si lo
   editás en otra rama, el cron no corre hasta mergear a `master`.
2. **Actions habilitado**: Settings → Actions → General → "Allow all
   actions and reusable workflows".
3. **El workflow no tiene que estar deshabilitado**: Actions → (panel
   izquierdo) "Chequear butacas…" → si aparece un botón **"Enable
   workflow"**, clickealo.

### Por qué puede parecer que "no corre"

- **GitHub tarda en arrancar el primer cron de un repo nuevo**: puede
  demorar 10–20 min (a veces más) desde el primer push a `master`.
- **`*/10` es "a lo sumo cada 10 min", no exacto.** El scheduler de
  GitHub es una cola compartida; en horas pico **atrasa 10–40 min o
  incluso saltea corridas**. Es una limitación conocida de GitHub, no un
  bug del bot. Si querés cadencia garantizada, GitHub Actions no es la
  herramienta (habría que un server/cron propio).
- **GitHub deshabilita el cron tras 60 días sin actividad en el repo.**
  Como el bot commitea `state/notified.json` cuando avisa, y podés hacer
  un commit cada tanto, no debería pasar. Si pasa, entrá a Actions y
  reactivalo.

### Cómo verificar

Actions → filtro **Event → `schedule`**. Si ves corridas con ese origen,
el cron está andando. Si después de ~30 min del push a `master` no hay
ninguna: hacé un commit cualquiera para "empujar" al scheduler y revisá
los 3 puntos de arriba.

### Costo de minutos (importante)

`*/10` ≈ **144 corridas/día**, ~1–2 min cada una.
- Repo **público** → Actions es gratis e ilimitado. **Recomendado.**
- Repo **privado** → el plan gratis da 2000 min/mes y esto se pasa en
  ~1 semana. Opciones: hacer el repo público, subir el intervalo
  (`*/20`, `*/30`), o limitar las horas del cron. Ej. correr solo de
  05:00 a 24:00 hora Argentina (= 08:00–02:59 UTC):

  ```yaml
  schedule:
    - cron: "*/10 8-23 * * *"
    - cron: "*/10 0-2 * * *"
  ```

  (Ojo: el cron es en **UTC**; Argentina es UTC−3. El rango horario que
  filtra *qué funciones* mirar — `MONITOR_START_HOUR/END_HOUR` — es
  aparte y está en hora local del sitio.)

## 4. Rango horario y otros ajustes

En `.github/workflows/check-seats.yml`, bloque `env:` del paso
"Correr el chequeo":

- `MONITOR_START_HOUR` / `MONITOR_END_HOUR` — rango de horarios a mirar
  (default 16 a 24, fin exclusivo).
- `CANTIDAD_ENTRADAS` — cuántas butacas contiguas buscar (default 2).

Para correrlo localmente valen las mismas variables de entorno.

## 5. "Avisar una sola vez"

Cuando una función tiene butacas buenas, el bot manda el email y anota
su `performanceId` en `state/notified.json`. Esa función no vuelve a
generar avisos, aunque después se liberen más butacas. Para volver a
armar el aviso de una función, borrá su id de ese archivo (o vaciá el
archivo a `[]` para re-armar todo).

## 6. Qué se considera "buena butaca"

Todo en `seat_ranking.py`. Hay dos ejes:

**Vertical (letra de fila):**
- `IDEAL_ROWS = {F, G, H, I}` — el corazón de la sala.
- `OK_ROWS = {E, J, K, L, M}` — aceptables como segunda opción.
- Cualquier otra fila (A–D) no dispara aviso.

**Horizontal (número de butaca dentro de la fila):** la sala está
partida por dos pasillos en 3 bloques. `CENTER_BLOCK[fila] = (primera,
última)` guarda el bloque **central** de cada fila. `OK_MARGIN = 4`
butacas a cada lado del bloque central todavía cuentan como "ok".

- `buena` → butaca dentro del bloque central.
- `ok` → hasta 4 butacas afuera del bloque central (a cada lado).
- `mala` → el resto (butacas contra la pared).

**Clasificación final** (combina los dos ejes; es lo que decide si se
avisa):

- `ideal` → fila F–I **y** butaca `buena`.
- `ok` → fila E–M y butaca `buena` u `ok` (y no llega a `ideal`).
- `else` → butaca `mala`, o fila A–D. **No dispara aviso.**

El bot elige, entre los pares contiguos disponibles, el de mejor clase
(`ideal` < `ok` < `else`) y, dentro de la misma clase, el más centrado
(`score` = 0.6 × distancia al centro + 0.4 × distancia a la fila G).

### Grilla completa (correr `python seat_ranking.py`)

```
fila  ancho  IDEAL (butacas)     OK (butacas)            else (butacas)
A       19   -                   -                       1-19
B       21   -                   -                       1-21
C       23   -                   -                       1-23
D       27   -                   -                       1-27
E       29   -                   4-26                    1-3, 27-29
F       31   9-23                5-8, 24-27              1-4, 28-31
G       33   10-24               6-9, 25-28              1-5, 29-33
H       35   11-25               7-10, 26-29             1-6, 30-35
I       37   12-26               8-11, 27-30             1-7, 31-37
J       37   -                   8-30                    1-7, 31-37
K       37   -                   8-30                    1-7, 31-37
L       29   -                   4-26                    1-3, 27-29
M       33   -                   6-28                    1-5, 29-33
```

⚠️ **Calibración**: `CENTER_BLOCK` está verificado a mano **solo para
I/J/K = (12, 26)**. Para el resto asume un bloque central de ~15 butacas
centrado en la fila. `ROW_WIDTHS` sí está confirmado contra dumps reales
(salvo L, que nunca mostró butacas > 22; quedó en 29 por estimación).
Si verificás los pasillos de otra fila, editá su tupla en
`CENTER_BLOCK` en `seat_ranking.py`.

## Notas técnicas

- El sitio (`entradas.todoshowcase.com`, "Voy al Cine") es ASP.NET Web
  Forms viejo. El estado de la compra vive en la sesión del servidor;
  cada corrida usa un navegador nuevo y aislado, así que hace login y
  repite la navegación desde cero.
- Toda la grilla de horarios está en el objeto JS `op_data` de
  `pelicula.aspx`, indexado por fecha. No hace falta clickear tabs de
  día ni acordeones para leerla.
- Cada butaca del mapa es un `<input type="image">` con `title="FILA-NUMERO"`
  y una imagen que indica el estado (`AvSeat.jpg` = disponible,
  `SoldSeat.jpg` = ocupado, etc. — documentadas en `scraper.py`).
- Loguearse de forma automática cada 10 minutos es intensivo; si notás
  bloqueos o el sitio te pide verificación, subí el intervalo del cron.

## Pendiente / ideas

- WhatsApp en vez de (o además de) email: lo más simple sin pagar la
  WhatsApp Business API es un servicio tipo CallMeBot (webhook gratis a
  tu propio WhatsApp). Se agrega en `notifier.py` una vez que el email
  esté andando.
