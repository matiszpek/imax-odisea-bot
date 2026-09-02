"""
notifier.py

Envía un email cuando el bot encuentra butacas buenas disponibles.

Usa Gmail con una "contraseña de aplicación" (App Password), no tu
contraseña normal de Gmail. Instrucciones para generarla están en el
README.md del proyecto.

Todas las credenciales se leen de variables de entorno, NUNCA se
escriben en este archivo. En GitHub Actions esas variables vienen de
"Secrets" (ver .github/workflows/check-seats.yml).
"""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

COMPRA_URL = "https://entradas.todoshowcase.com/showcase/pelicula.aspx?filmid=5875"


def send_email(subject: str, body: str) -> None:
    """
    Envía un email usando SMTP de Gmail.

    Variables de entorno requeridas:
      GMAIL_USER          -> la cuenta de Gmail que envía (ej. tuusuario@gmail.com)
      GMAIL_APP_PASSWORD  -> la contraseña de aplicación de 16 caracteres
      NOTIFY_TO           -> a qué email(s) mandar el aviso, separados por coma
    """
    gmail_user = os.environ["GMAIL_USER"]
    gmail_app_password = os.environ["GMAIL_APP_PASSWORD"]
    notify_to = [x.strip() for x in os.environ["NOTIFY_TO"].split(",") if x.strip()]

    msg = MIMEMultipart()
    msg["From"] = gmail_user
    msg["To"] = ", ".join(notify_to)
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_user, gmail_app_password)
        server.sendmail(gmail_user, notify_to, msg.as_string())


def build_email_body(avisos) -> str:
    """
    `avisos` es una lista de tuplas (FunctionResult, best_pair), donde
    best_pair es la lista de RankedSeat del mejor par contiguo.
    """
    lines = [
        "¡Hay butacas para La Odisea en IMAX Theatre (Norcenter)!",
        "",
    ]

    for fr, best_pair in avisos:
        perf = fr.performance
        lines.append(f"▶ {perf.date}  {perf.show_time}  ·  {perf.format_desc}")
        lines.append(f"  Butacas libres en la sala ahora: {len(fr.disponibles)}")
        lines.append("  Mejor par contiguo y centrado:")
        for seat in best_pair:
            lines.append(
                f"    - Fila {seat.row}, asiento {seat.num} (zona: {seat.zona})"
            )
        lines.append("")

    lines += [
        "Andá rápido a comprarlas, la demanda es alta:",
        COMPRA_URL,
        "",
        "(Este es un aviso único por función: si más adelante se liberan",
        " más butacas de la misma función, el bot no vuelve a avisar.)",
    ]
    return "\n".join(lines)
