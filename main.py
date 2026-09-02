"""
main.py

Punto de entrada del bot. Corre UNA vez por invocación (GitHub Actions
lo dispara con un cron; no queda en loop).

Flujo:
  1. Inicia sesión en Showcase y lee todas las funciones IMAX de
     "La Odisea" en IMAX Theatre (Norcenter) que caen en el rango
     horario configurado (por defecto 16:00 a 24:00).
  2. Para cada función NO avisada todavía, saca el mapa de butacas y
     busca el mejor par contiguo y centrado.
  3. Si hay funciones nuevas con butacas buenas, manda UN email con
     todas juntas y las marca como avisadas (state/notified.json).
  4. "Avisar una vez y frenar": una función ya avisada no vuelve a
     generar email aunque siga habiendo lugar. Para re-armar el aviso
     de una función, borrá su id de state/notified.json.

Config por variables de entorno (todas opcionales salvo credenciales):
  SHOWCASE_USER        (requerida)  DNI o email de la cuenta Showcase
  SHOWCASE_PASS        (requerida)  contraseña de esa cuenta
  GMAIL_USER / GMAIL_APP_PASSWORD / NOTIFY_TO  -> ver notifier.py
  MONITOR_START_HOUR   (default 16)  hora desde la cual mirar funciones
  MONITOR_END_HOUR     (default 24)  hora hasta la cual mirar (exclusiva)
  CANTIDAD_ENTRADAS    (default 2)
  HEADLESS             (default 1)   0 para ver el navegador
"""

import json
import os
import sys
from pathlib import Path

from scraper import check_functions, LoginError
from seat_ranking import find_best_pair, pair_class
from notifier import send_email, build_email_body

STATE_FILE = Path(__file__).parent / "state" / "notified.json"

CANTIDAD_ENTRADAS = int(os.environ.get("CANTIDAD_ENTRADAS", "2"))
MONITOR_START_HOUR = int(os.environ.get("MONITOR_START_HOUR", "16"))
MONITOR_END_HOUR = int(os.environ.get("MONITOR_END_HOUR", "24"))
HEADLESS = os.environ.get("HEADLESS", "1") not in ("0", "false", "no")

# Solo avisamos si el mejor par contiguo clasifica como "ideal" u "ok"
# (ver seat_ranking.classify_seat). Si lo único contiguo es "else"
# (butacas contra la pared o filas muy adelante), no molestamos.


def _load_notified() -> set[int]:
    try:
        return set(json.loads(STATE_FILE.read_text(encoding="utf-8")))
    except FileNotFoundError:
        return set()
    except (json.JSONDecodeError, ValueError):
        print(f"AVISO: {STATE_FILE} ilegible, se arranca de cero.", file=sys.stderr)
        return set()


def _save_notified(ids: set[int]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(
        json.dumps(sorted(ids), indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    print(
        f"Chequeando funciones IMAX de La Odisea entre las "
        f"{MONITOR_START_HOUR}:00 y las {MONITOR_END_HOUR}:00..."
    )

    notified = _load_notified()
    print(f"Funciones ya avisadas hasta ahora: {len(notified)}")

    try:
        resultados = check_functions(
            start_hour=MONITOR_START_HOUR,
            end_hour=MONITOR_END_HOUR,
            cantidad=CANTIDAD_ENTRADAS,
            headless=HEADLESS,
            skip_performance_ids=notified,
        )
    except LoginError as e:
        print(f"ERROR de login: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR durante el chequeo: {e}", file=sys.stderr)
        sys.exit(1)

    nuevos_avisos = []  # list[(FunctionResult, best_pair)]

    for fr in resultados:
        perf = fr.performance
        if fr.error:
            # ya se logueó en el scraper; no cortamos el resto.
            continue

        disponibles = fr.disponibles
        if not disponibles:
            print(f"{perf.label}: sin butacas. Nada que hacer.")
            continue

        best_pair = find_best_pair(disponibles, cantidad=CANTIDAD_ENTRADAS)
        if not best_pair:
            print(
                f"{perf.label}: {len(disponibles)} butacas sueltas, ninguna "
                f"corrida contigua de {CANTIDAD_ENTRADAS}. No se avisa."
            )
            continue

        clase = pair_class(best_pair)
        if clase == "else":
            print(
                f"{perf.label}: el mejor par contiguo es 'else' "
                f"(fila {best_pair[0].row}, asientos {[s.num for s in best_pair]}). "
                f"No se avisa."
            )
            continue

        print(
            f"{perf.label}: ¡par {clase}! fila {best_pair[0].row}, "
            f"asientos {[s.num for s in best_pair]}."
        )
        nuevos_avisos.append((fr, best_pair))

    if not nuevos_avisos:
        print("Nada nuevo para avisar. Fin.")
        return

    body = build_email_body(nuevos_avisos)
    cantidad_funciones = len(nuevos_avisos)
    subject = (
        f"La Odisea IMAX Norcenter: butacas en "
        f"{cantidad_funciones} funcion{'es' if cantidad_funciones > 1 else ''}"
    )
    send_email(subject=subject, body=body)
    print(f"Email enviado con {cantidad_funciones} función(es).")

    for fr, _ in nuevos_avisos:
        notified.add(fr.performance.performance_id)
    _save_notified(notified)
    print(f"Estado actualizado: {len(notified)} funciones avisadas.")


if __name__ == "__main__":
    main()
