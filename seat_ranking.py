"""
seat_ranking.py

Define qué se considera un asiento "centrado" en la sala IMAX de
Showcase Norcenter, y ordena los asientos disponibles de mejor a peor
según esa definición.

Geometría real relevada el 02/09/2026 (puede no ser exactamente igual
en otra sesión, pero la sala física no cambia, así que sirve como
referencia fija):

  Fila A: butacas 1-19   (19 asientos)
  Fila B: butacas 1-21   (21 asientos)
  Fila C: butacas 1-23   (23 asientos)
  Fila D: butacas 1-27   (27 asientos)
  Fila E: butacas 1-29   (29 asientos)
  Fila F: butacas 1-31   (31 asientos)
  Fila G: butacas 1-33   (33 asientos)
  Fila H: butacas 1-35   (35 asientos)
  Fila I: butacas 1-37   (37 asientos)
  Fila J: butacas 1-37   (37 asientos)
  Fila K: butacas 1-37   (37 asientos)
  Fila L: butacas 1-29   (29 asientos)
  Fila M: butacas 1-33   (33 asientos)

La sala se ensancha de A a K/J y after vuelve a angostarse en L/M
(probablemente L/M están detrás de un pasillo o son una zona distinta,
como balcón). Para "el mejor asiento posible" el criterio clásico de
sala de cine es:
  1. Ni en las primerísimas filas (muy cerca de la pantalla, IMAX es
     grande y se sufre el cuello) ni en las últimas.
  2. Centrado horizontalmente dentro de su fila (no en los extremos).
"""

from dataclasses import dataclass

# Ancho real de cada fila (cantidad de butacas), según lo relevado.
ROW_WIDTHS = {
    "A": 19, "B": 21, "C": 23, "D": 27, "E": 29, "F": 31,
    "G": 33, "H": 35, "I": 37, "J": 37, "K": 37, "L": 29, "M": 33,
}

# Orden de filas de adelante (cerca de pantalla) hacia atrás.
ROW_ORDER = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M"]

# Filas que consideramos "zona ideal" verticalmente: ni muy adelante ni
# muy atrás. F, G, H, I son el corazón de la sala (posiciones 6-9 de 13).
IDEAL_ROWS = {"F", "G", "H", "I"}

# Filas aceptables como segunda opción si no hay nada en la zona ideal.
OK_ROWS = {"E", "J", "K"}


@dataclass
class RankedSeat:
    row: str
    num: int
    score: float  # menor = mejor
    zona: str  # "ideal", "ok", "otra"


def _horizontal_centering(row: str, num: int) -> float:
    """
    Devuelve qué tan lejos del centro horizontal está la butaca `num`
    dentro de su fila, normalizado 0 (centro exacto) a 1 (extremo).
    """
    width = ROW_WIDTHS.get(row)
    if not width:
        return 1.0  # fila desconocida, la tratamos como mala
    center = (width + 1) / 2
    max_dist = width / 2
    return abs(num - center) / max_dist if max_dist else 0.0


def _row_zone(row: str) -> str:
    if row in IDEAL_ROWS:
        return "ideal"
    if row in OK_ROWS:
        return "ok"
    return "otra"


def rank_seats(available_seats: list) -> list[RankedSeat]:
    """
    Recibe una lista de objetos con .row y .num (por ejemplo, los Seat
    de scraper.py ya filtrados a solo disponibles) y devuelve una lista
    de RankedSeat ordenada de mejor a peor.

    El score combina:
      - distancia horizontal al centro de la fila (peso principal)
      - qué tan lejos está la fila de la zona ideal (F-I)
    """
    ranked = []
    for seat in available_seats:
        h_dist = _horizontal_centering(seat.row, seat.num)
        zona = _row_zone(seat.row)

        if seat.row in ROW_ORDER:
            row_idx = ROW_ORDER.index(seat.row)
            ideal_idx = ROW_ORDER.index("G")  # G como centro vertical ideal
            v_dist = abs(row_idx - ideal_idx) / len(ROW_ORDER)
        else:
            v_dist = 1.0

        # Peso: horizontal pesa un poco más que vertical, porque quedar
        # en el extremo lateral molesta más que estar una fila más
        # adelante/atrás de la ideal.
        score = (h_dist * 0.6) + (v_dist * 0.4)

        ranked.append(RankedSeat(row=seat.row, num=seat.num, score=score, zona=zona))

    ranked.sort(key=lambda r: r.score)
    return ranked


def find_best_pair(available_seats: list, cantidad: int = 2) -> list[RankedSeat] | None:
    """
    Busca `cantidad` butacas CONTIGUAS (misma fila, números consecutivos)
    lo más centradas posible. Devuelve None si no hay ningún grupo
    contiguo de ese tamaño disponible.

    Esto es importante porque el sitio exige "seleccionar todas las
    butacas contiguas" (vimos ese mensaje de error en el sitio), así que
    dos asientos sueltos en la misma fila pero no adyacentes no sirven
    para ir juntos.
    """
    by_row: dict[str, list[int]] = {}
    for s in available_seats:
        by_row.setdefault(s.row, []).append(s.num)

    candidates = []
    for row, nums in by_row.items():
        nums_sorted = sorted(nums)
        # buscar corridas consecutivas de largo >= cantidad
        run = [nums_sorted[0]]
        for n in nums_sorted[1:]:
            if n == run[-1] + 1:
                run.append(n)
            else:
                run = [n]
            if len(run) >= cantidad:
                # tomar los `cantidad` números más centrados dentro de
                # esta corrida
                start = run[-cantidad]
                group_nums = list(range(start, start + cantidad))
                candidates.append((row, group_nums))

    if not candidates:
        return None

    # Rankear cada grupo por el score promedio de sus butacas
    best_group = None
    best_avg_score = None
    for row, nums in candidates:
        fake_seats = [type("S", (), {"row": row, "num": n})() for n in nums]
        ranked = rank_seats(fake_seats)
        avg = sum(r.score for r in ranked) / len(ranked)
        if best_avg_score is None or avg < best_avg_score:
            best_avg_score = avg
            best_group = ranked

    return best_group
