# Bot de butacas — La Odisea, IMAX Theatre (Norcenter)

Cada 10 minutos revisa las funciones IMAX de **La Odisea** en el
**IMAX Theatre (Norcenter)** de Showcase, dentro de un rango horario
(por defecto **16:00 a 24:00**), y manda un email cuando encuentra un
par de butacas contiguas y bien centradas. Avisa **una sola vez por
función**.

## Estado actual

- ✅ Lectura de la grilla de horarios: **funciona y está probada en vivo**.
  El sitio trae toda la agenda IMAX embebida en un objeto JS (`op_data`),
  así que sacar fechas/horarios/`performanceId` es directo y confiable.
- ⚠️ Login + mapa de butacas: **escrito pero NO probado en vivo**, porque
  hace falta una cuenta real de Showcase. El sitio cambió respecto de la
  primera versión de este bot: **ahora exige iniciar sesión** (DNI/email
  + contraseña, sin opción de invitado) para llegar al mapa de butacas.
  El primer arranque casi seguro necesita un ajuste fino en
  `_navegar_hasta_mapa` (la pantalla de "cantidad de entradas" previa al
  mapa). **Corré el bot una vez en tu compu con el navegador visible
  antes de confiar en el cron** (ver más abajo).

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
3. **Cada función en rango**: navega a su URL y llega al mapa de butacas.
   **Acá es donde más probable falle la primera vez.** Si ves un
   `TimeoutError` con un dump de HTML, es la pantalla intermedia de
   cantidad de entradas: fijate en ese HTML cómo es el control real
   (¿un `<select>`? ¿botones +/-? ¿un botón "Continuar"?) y ajustá
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
   `state/notified.json` de vuelta (ya está puesto en el YAML como
   `permissions: contents: write`). Si tu organización lo bloquea:
   **Settings → Actions → General → Workflow permissions → Read and write**.

Una vez confirmado, el cron lo corre solo.

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

En `seat_ranking.py`, listas `IDEAL_ROWS` (F, G, H, I) y `OK_ROWS`
(E, J, K), más `ROW_WIDTHS` con el ancho de cada fila. El score combina
distancia al centro horizontal (peso 0.6) y distancia a la fila ideal
(0.4). Ojo: `ROW_WIDTHS` viene de un relevamiento previo y **todavía no
lo pudimos verificar contra el mapa real** (está detrás del login).
Ajustalo cuando veas la sala de verdad.

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
