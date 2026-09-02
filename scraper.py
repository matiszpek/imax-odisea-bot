"""
scraper.py

Navega el sitio de Showcase (entradas.todoshowcase.com) con Playwright y
devuelve, para cada función IMAX de "La Odisea" en IMAX Theatre
(Norcenter) que caiga dentro del rango horario configurado, la lista de
butacas disponibles con su fila/número.

Cosas que aprendimos inspeccionando el sitio en vivo (02/09/2026):

1. "La Odisea" es el filmid 5875. La página de la película
   (`pelicula.aspx?filmid=5875`) trae TODA la grilla de horarios ya
   embebida en un objeto JavaScript global llamado `op_data`. No hace
   falta clickear tabs de día ni expandir acordeones para leer los
   horarios: se leen directo de `op_data`.

       op_data.name                -> "La Odisea"
       op_data.days["2026-09-02"]  -> lista de cines de ese día
         cada cine: { id, name, ewaveId, formats: [ ... ] }
         cada format: { formatDescription, showId, performances: [ ... ] }
         cada performance: { performanceId, showTime }

   IMAX Theatre (Norcenter) es el cine con `id == 18`, y el formato es
   "IMAX-Subtitulado" (`showId == "86868A"`, pero lo leemos dinámico).

2. Elegir un horario NO abre una pantalla intermedia: arma una URL
   directa de la forma

       pelicula.aspx?filmid=5875&perf=<performanceId>&cinema=18&date=<YYYY-MM-DD>&show=<showId>

   y redirige ahí. O sea que podemos saltar directo a esa URL.

3. IMPORTANTE: esa URL, si NO estás logueado, te patea a
   `ingresar.aspx` (login). No hay checkout como invitado. Por eso el
   bot ahora inicia sesión con una cuenta de Showcase (credenciales en
   variables de entorno SHOWCASE_USER / SHOWCASE_PASS) antes de
   consultar cada función.

4. Después del login, la URL de la función lleva a la selección de
   cantidad de entradas y luego al mapa de butacas. Esa parte
   (`_navegar_hasta_mapa`) es la más frágil porque no la pudimos
   inspeccionar sin una cuenta real. Si algo falla, corré este archivo
   con `HEADLESS=0 python scraper.py` y mirá en qué paso se traba.

Cada butaca en el mapa es un <input type="image"> con:
  - title = "FILA-NUMERO"  (ej. "B-14")
  - src   = nombre de imagen que indica el estado:
        AvSeat.jpg    -> disponible
        SoldSeat.jpg  -> ocupado/vendido
        NotAvSeat.jpg -> no es un asiento real (hueco en la sala)
        HandSeat.jpg  -> asiento adaptado (discapacidad)
        SelSeat.jpg   -> seleccionado en esta sesión
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from playwright.sync_api import (
    sync_playwright,
    Page,
    TimeoutError as PWTimeout,
)

BASE_URL = "https://entradas.todoshowcase.com/showcase/"

# Identificadores fijos del sitio (ver docstring). FILM_ID puede cambiar
# si Showcase recarga la ficha de la película; si el bot deja de
# encontrar funciones, revisá el filmid en la URL de "La Odisea".
FILM_ID = int(os.environ.get("SHOWCASE_FILM_ID", "5875"))
CINEMA_ID_IMAX_NORCENTER = int(os.environ.get("SHOWCASE_CINEMA_ID", "18"))

STATE_MAP = {
    "AvSeat.jpg": "disponible",
    "SoldSeat.jpg": "ocupado",
    "NotAvSeat.jpg": "no_disponible",
    "HandSeat.jpg": "discapacidad",
    "SelSeat.jpg": "seleccionado",
}


@dataclass
class Seat:
    row: str
    num: int
    state: str


@dataclass
class Performance:
    """Una función concreta (fecha + hora) de La Odisea en IMAX Norcenter."""

    performance_id: int
    date: str          # "YYYY-MM-DD"
    show_time: str      # "HH:MM"
    show_code: str      # showId, ej. "86868A"
    format_desc: str    # ej. "IMAX-Subtitulado"

    @property
    def hour(self) -> int:
        return int(self.show_time.split(":")[0])

    @property
    def label(self) -> str:
        return f"{self.date} {self.show_time} ({self.format_desc})"

    def url(self) -> str:
        return (
            f"{BASE_URL}pelicula.aspx?filmid={FILM_ID}"
            f"&perf={self.performance_id}"
            f"&cinema={CINEMA_ID_IMAX_NORCENTER}"
            f"&date={self.date}"
            f"&show={self.show_code}"
        )


@dataclass
class FunctionResult:
    performance: Performance
    seats: list[Seat] = field(default_factory=list)
    error: str | None = None

    @property
    def disponibles(self) -> list[Seat]:
        return [s for s in self.seats if s.state == "disponible"]


class LoginError(RuntimeError):
    pass


# --------------------------------------------------------------------------- #
# Login
# --------------------------------------------------------------------------- #

def _login(page: Page, user: str, password: str) -> None:
    """
    Inicia sesión en Showcase. Lanza LoginError si no lo logra.

    El form es ASP.NET WebForms clásico: el botón "INGRESAR" dispara un
    __doPostBack. Después del login exitoso el sitio deja de mostrar el
    campo de contraseña.
    """
    page.goto(f"{BASE_URL}ingresar.aspx", wait_until="domcontentloaded")

    page.fill("#ctl00_Contenido_txtIdOrMail", user)
    page.fill("#ctl00_Contenido_txtpass", password)
    page.click("#ctl00_Contenido_btnGet")

    try:
        page.wait_for_load_state("networkidle", timeout=15_000)
    except PWTimeout:
        pass

    # ¿Sigue el campo de contraseña visible? -> no entró.
    still_on_login = page.locator("#ctl00_Contenido_txtpass").count() > 0
    if still_on_login:
        status = ""
        try:
            status = page.locator("#ctl00_Contenido_lblStatus").inner_text(timeout=2000)
        except PWTimeout:
            pass
        status = status.strip() or "sin mensaje"
        raise LoginError(
            f"No se pudo iniciar sesión en Showcase. "
            f"Mensaje del sitio: {status!r}. "
            f"Revisá SHOWCASE_USER / SHOWCASE_PASS."
        )


# --------------------------------------------------------------------------- #
# Grilla de horarios (op_data)
# --------------------------------------------------------------------------- #

def _leer_performances_imax(page: Page) -> list[Performance]:
    """
    Abre la ficha de La Odisea y lee de `op_data` todas las funciones
    IMAX de IMAX Theatre (Norcenter), de todos los días disponibles.
    """
    page.goto(
        f"{BASE_URL}pelicula.aspx?filmid={FILM_ID}",
        wait_until="domcontentloaded",
    )

    try:
        page.wait_for_function("typeof op_data !== 'undefined' && !!op_data.days", timeout=15_000)
    except PWTimeout:
        raise RuntimeError(
            "No apareció `op_data` en la ficha de la película. "
            "¿Cambió el filmid o el layout del sitio?"
        )

    raw = page.evaluate(
        """(cinemaId) => {
            const out = [];
            const days = op_data.days || {};
            for (const date of Object.keys(days)) {
                const cine = (days[date] || []).find(c => c.id === cinemaId);
                if (!cine) continue;
                for (const fmt of (cine.formats || [])) {
                    for (const perf of (fmt.performances || [])) {
                        out.push({
                            performance_id: perf.performanceId,
                            date: date,
                            show_time: perf.showTime,
                            show_code: fmt.showId,
                            format_desc: fmt.formatDescription,
                        });
                    }
                }
            }
            return out;
        }""",
        CINEMA_ID_IMAX_NORCENTER,
    )

    perfs = [
        Performance(
            performance_id=int(item["performance_id"]),
            date=item["date"],
            # a veces las trasnoche vienen como "N 00:30"; normalizamos.
            show_time=item["show_time"].replace("N ", "").strip(),
            show_code=item["show_code"],
            format_desc=item["format_desc"],
        )
        for item in raw
    ]
    perfs.sort(key=lambda p: (p.date, p.show_time))
    return perfs


# --------------------------------------------------------------------------- #
# Mapa de butacas
# --------------------------------------------------------------------------- #

def _navegar_hasta_mapa(page: Page, perf: Performance, cantidad: int) -> None:
    """
    Desde la URL directa de la función, avanza (si hace falta) por la
    pantalla de cantidad de entradas hasta que aparece el mapa de
    butacas (inputs type=image).

    OJO: no pudimos inspeccionar esta parte con una cuenta real. Está
    escrita a la defensiva y puede necesitar ajuste. Si el mapa nunca
    aparece, este método tira TimeoutError con un dump de contexto.
    """
    page.goto(perf.url(), wait_until="domcontentloaded")

    # Si nos devolvió al login, la sesión se cayó.
    if "ingresar.aspx" in page.url:
        raise LoginError("La función pide login: la sesión no está activa.")

    # ¿Ya estamos en el mapa?
    if page.locator("input[type='image']").count() > 0:
        _sweep_seatmap(page)
        return

    # Pantalla de cantidad de entradas. Probamos las variantes conocidas
    # de sitios ASP.NET viejos, en orden.
    _intentar_setear_cantidad(page, cantidad)

    # Botón de avanzar ("Continuar" / "Siguiente" / "Seleccionar butacas").
    for patron in (r"continuar", r"siguiente", r"butaca", r"asiento", r"confirmar"):
        btn = page.get_by_role("button", name=re.compile(patron, re.IGNORECASE))
        if btn.count() == 0:
            btn = page.get_by_role("link", name=re.compile(patron, re.IGNORECASE))
        if btn.count() > 0:
            try:
                btn.first.click(timeout=3000)
                page.wait_for_load_state("domcontentloaded")
                break
            except PWTimeout:
                continue

    try:
        page.wait_for_selector("input[type='image']", timeout=15_000)
    except PWTimeout:
        dump = page.content()[:1500]
        raise PWTimeout(
            f"No apareció el mapa de butacas para {perf.label}. "
            f"URL actual: {page.url}\n--- HTML (recortado) ---\n{dump}"
        )

    _sweep_seatmap(page)


def _sweep_seatmap(page: Page) -> None:
    """
    El mapa avisa "Puede desplazarse horizontalmente para ver más
    lugares": si el contenedor de butacas hace scroll horizontal, algunas
    butacas podrían no estar renderizadas hasta que se scrollea. Por las
    dudas, recorremos el contenedor de izquierda a derecha antes de leer.

    Es best-effort: si no encuentra un contenedor scrolleable, no hace
    nada (y `_extract_seats` igual lee lo que haya en el DOM).
    """
    try:
        page.evaluate(
            """async () => {
                const sleep = (ms) => new Promise(r => setTimeout(r, ms));
                const img = document.querySelector("input[type='image']");
                if (!img) return;
                // buscar el ancestro que scrollea horizontalmente
                let el = img.parentElement;
                let cont = null;
                while (el && el !== document.body) {
                    if (el.scrollWidth > el.clientWidth + 20) { cont = el; break; }
                    el = el.parentElement;
                }
                const target = cont || document.scrollingElement || document.body;
                const max = target.scrollWidth;
                for (let x = 0; x <= max; x += Math.max(200, target.clientWidth - 100)) {
                    target.scrollLeft = x;
                    await sleep(120);
                }
                target.scrollLeft = 0;
                await sleep(120);
            }"""
        )
    except Exception:
        pass


def _intentar_setear_cantidad(page: Page, cantidad: int) -> None:
    """Intenta poner `cantidad` entradas, tolerando varios tipos de control."""
    # 1) <select>
    selects = page.locator("select")
    if selects.count() > 0:
        try:
            selects.first.select_option(str(cantidad))
            page.wait_for_timeout(400)
            return
        except Exception:
            pass

    # 2) <input type="number">
    num = page.locator("input[type='number']")
    if num.count() > 0:
        try:
            num.first.fill(str(cantidad))
            page.wait_for_timeout(400)
            return
        except Exception:
            pass

    # 3) botones +/- : clickeamos "+" (cantidad-1) veces
    mas = page.get_by_role("button", name=re.compile(r"^\s*\+\s*$"))
    if mas.count() > 0:
        for _ in range(max(0, cantidad - 1)):
            try:
                mas.first.click(timeout=2000)
                page.wait_for_timeout(200)
            except PWTimeout:
                break


def _extract_seats(page: Page) -> list[Seat]:
    raw = page.eval_on_selector_all(
        "input[type='image']",
        """els => els.map(e => ({
            title: e.title || e.getAttribute('title') || '',
            src: e.src ? e.src.split('/').pop() : ''
        }))""",
    )
    por_butaca: dict[tuple[str, int], Seat] = {}
    for item in raw:
        title = item.get("title", "")
        if "-" not in title:
            continue
        row, num_str = title.rsplit("-", 1)
        if not num_str.isdigit():
            continue
        row = row.strip()
        num = int(num_str)
        state = STATE_MAP.get(item.get("src", ""), "desconocido")
        # Si aparece repetida (p. ej. tras scrollear), nos quedamos con
        # la lectura que tenga un estado conocido.
        prev = por_butaca.get((row, num))
        if prev is None or (prev.state == "desconocido" and state != "desconocido"):
            por_butaca[(row, num)] = Seat(row=row, num=num, state=state)

    return sorted(por_butaca.values(), key=lambda s: (s.row, s.num))


# --------------------------------------------------------------------------- #
# API pública
# --------------------------------------------------------------------------- #

def check_functions(
    start_hour: int = 16,
    end_hour: int = 24,
    cantidad: int = 2,
    headless: bool = True,
    only_performance_ids: set[int] | None = None,
    skip_performance_ids: set[int] | None = None,
) -> list[FunctionResult]:
    """
    Devuelve un FunctionResult por cada función IMAX de La Odisea en
    IMAX Norcenter cuyo horario esté en [start_hour, end_hour).

    - only_performance_ids: si se pasa, sólo consulta esas funciones.
    - skip_performance_ids: funciones a saltear (ej. ya avisadas).

    Cada FunctionResult trae .disponibles (butacas libres) o .error si
    esa función puntual falló (el resto se sigue consultando igual).
    """
    user = os.environ.get("SHOWCASE_USER")
    password = os.environ.get("SHOWCASE_PASS")
    if not user or not password:
        raise RuntimeError(
            "Faltan las credenciales de Showcase. Definí las variables de "
            "entorno SHOWCASE_USER (DNI o email) y SHOWCASE_PASS."
        )

    skip_performance_ids = skip_performance_ids or set()
    results: list[FunctionResult] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            locale="es-AR",
            viewport={"width": 1920, "height": 1080},
        )
        page = context.new_page()

        try:
            _login(page, user, password)

            perfs = _leer_performances_imax(page)
            print(f"Funciones IMAX encontradas en la grilla: {len(perfs)}")

            for perf in perfs:
                if only_performance_ids is not None and perf.performance_id not in only_performance_ids:
                    continue
                if perf.performance_id in skip_performance_ids:
                    print(f"  - {perf.label}: ya avisada, se saltea.")
                    continue
                if not (start_hour <= perf.hour < end_hour):
                    continue

                fr = FunctionResult(performance=perf)
                try:
                    _navegar_hasta_mapa(page, perf, cantidad)
                    fr.seats = _extract_seats(page)
                    print(
                        f"  - {perf.label}: {len(fr.disponibles)} "
                        f"butacas disponibles (de {len(fr.seats)})."
                    )
                except Exception as e:  # noqa: BLE001 - queremos seguir con las demás
                    fr.error = str(e)
                    print(f"  - {perf.label}: ERROR -> {e}")
                results.append(fr)
        finally:
            browser.close()

    return results


if __name__ == "__main__":
    _headless = os.environ.get("HEADLESS", "1") not in ("0", "false", "no")
    _start = int(os.environ.get("MONITOR_START_HOUR", "16"))
    _end = int(os.environ.get("MONITOR_END_HOUR", "24"))

    res = check_functions(start_hour=_start, end_hour=_end, headless=_headless)
    print("\n=== Resumen ===")
    for fr in res:
        if fr.error:
            print(f"{fr.performance.label}: ERROR {fr.error}")
            continue
        print(f"{fr.performance.label}: {len(fr.disponibles)} disponibles")
        for s in fr.disponibles:
            print(f"    {s.row}-{s.num}")
