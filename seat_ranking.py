"""
seat_ranking.py

Define qué se considera un asiento "centrado" en la sala IMAX de
Showcase Norcenter y ordena los asientos disponibles de mejor a peor.

Hay DOS ejes:

  1. Vertical  (letra de fila)   -> IDEAL_ROWS / OK_ROWS / resto
  2. Horizontal (número dentro de la fila) -> "buena" / "ok" / "mala",
     en base a en qué bloque de la sala cae la butaca.

La sala está partida por dos pasillos en TRES bloques: uno central
grande y dos laterales. `CENTER_BLOCK` guarda, por fila, el primer y
último número del bloque central. El único dato verificado a mano es
I/J/K -> (12, 26); el resto asume un bloque central de ~15 butacas
centrado en la fila. Si verificás otra fila y no coincide, editá su
tupla en `CENTER_BLOCK`.

Anchos de fila (butaca máxima), confirmados contra dumps reales del
mapa el 07/09/2026:

  A:19  B:21  C:23  D:27  E:29  F:31  G:33  H:35  I:37  J:37  K:37
  L:29  M:33            (L nunca mostró butacas > 22; 29 es estimado)

Correr `python seat_ranking.py` imprime la grilla completa
fila x butaca clasificada en ideal / ok / else.
"""

from dataclasses import dataclass

# Ancho real de cada fila (cantidad de butacas).
ROW_WIDTHS = {
    "A": 19, "B": 21, "C": 23, "D": 27, "E": 29, "F": 31,
    "G": 33, "H": 35, "I": 37, "J": 37, "K": 37, "L": 29, "M": 33,
}

# Orden de filas de adelante (cerca de pantalla) hacia atrás.
ROW_ORDER = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M"]

# --- Eje vertical -----------------------------------------------------------
# Filas "corazón de la sala": ni muy adelante ni muy atrás.
IDEAL_ROWS = {"F", "G", "H", "I"}
# Filas aceptables como segunda opción (E justo antes del corazón; J/K
# apenas atrás; L/M son las últimas, lejos de la pantalla pero válidas).
OK_ROWS = {"E", "J", "K", "L", "M"}

# --- Eje horizontal -------------------------------------------------------- #
# Bloque central (entre los dos pasillos) de cada fila: (primera, última)
# butaca. VERIFICADO a mano solo para I/J/K = (12, 26). El resto es un
# bloque de ~15 butacas centrado en la fila -> editá la fila puntual acá
# si la chequeás y no da.
CENTER_BLOCK = {
    "A": (3, 17), "B": (4, 18), "C": (5, 19), "D": (7, 21),
    "E": (8, 22), "F": (9, 23), "G": (10, 24), "H": (11, 25),
    "I": (12, 26), "J": (12, 26), "K": (12, 26),
    "L": (8, 22), "M": (10, 24),
}
# Cuántas butacas a cada lado del bloque central siguen contando "ok".
OK_MARGIN = 4


@dataclass
class RankedSeat:
    row: str
    num: int
    score: float   # menor = mejor (para ordenar entre butacas parecidas)
    zona: str      # eje vertical: "ideal" | "ok" | "otra"
    h_zona: str    # eje horizontal: "buena" | "ok" | "mala"
    clase: str     # combinación de ambos: "ideal" | "ok" | "else"


# --------------------------------------------------------------------------- #
# Clasificación
# --------------------------------------------------------------------------- #

def _row_zone(row: str) -> str:
    if row in IDEAL_ROWS:
        return "ideal"
    if row in OK_ROWS:
        return "ok"
    return "otra"


def _horizontal_zone(row: str, num: int) -> str:
    """buena = bloque central; ok = hasta OK_MARGIN butacas a los costados;
    mala = el resto (butacas contra la pared)."""
    block = CENTER_BLOCK.get(row)
    if block is None:
        width = ROW_WIDTHS.get(row)
        if not width:
            return "mala"
        half = max(1, (15 - 1) // 2)
        center = (width + 1) / 2
        block = (round(center - half), round(center + half))
    lo, hi = block
    if lo <= num <= hi:
        return "buena"
    if lo - OK_MARGIN <= num <= hi + OK_MARGIN:
        return "ok"
    return "mala"


def classify_seat(row: str, num: int) -> str:
    """
    Clasificación final de una butaca, combinando fila + número:

      "ideal" -> fila del corazón (F-I) Y butaca en el bloque central
      "ok"    -> el resto de las combinaciones "mirables":
                 fila en IDEAL_ROWS∪OK_ROWS y butaca no "mala"
      "else"  -> butaca contra la pared, o fila muy adelante (A-D)
    """
    rz = _row_zone(row)
    hz = _horizontal_zone(row, num)
    if rz == "otra" or hz == "mala":
        return "else"
    if rz == "ideal" and hz == "buena":
        return "ideal"
    return "ok"


_CLASS_ORDER = {"ideal": 0, "ok": 1, "else": 2}


def _horizontal_centering(row: str, num: int) -> float:
    """Distancia normalizada de la butaca al centro de su fila (0..1).
    Solo se usa para desempatar en el `score`."""
    width = ROW_WIDTHS.get(row)
    if not width:
        return 1.0
    center = (width + 1) / 2
    max_dist = width / 2
    return abs(num - center) / max_dist if max_dist else 0.0


# --------------------------------------------------------------------------- #
# Ranking
# --------------------------------------------------------------------------- #

def rank_seats(available_seats: list) -> list[RankedSeat]:
    """
    Recibe objetos con .row y .num y devuelve RankedSeat ordenados de
    mejor a peor: primero por clase (ideal < ok < else), después por
    `score` (distancia al centro horizontal 0.6 + distancia a la fila
    ideal G 0.4).
    """
    ranked = []
    for seat in available_seats:
        h_dist = _horizontal_centering(seat.row, seat.num)
        zona = _row_zone(seat.row)
        h_zona = _horizontal_zone(seat.row, seat.num)
        clase = classify_seat(seat.row, seat.num)

        if seat.row in ROW_ORDER:
            row_idx = ROW_ORDER.index(seat.row)
            ideal_idx = ROW_ORDER.index("G")
            v_dist = abs(row_idx - ideal_idx) / len(ROW_ORDER)
        else:
            v_dist = 1.0

        score = (h_dist * 0.6) + (v_dist * 0.4)

        ranked.append(
            RankedSeat(
                row=seat.row, num=seat.num, score=score,
                zona=zona, h_zona=h_zona, clase=clase,
            )
        )

    ranked.sort(key=lambda r: (_CLASS_ORDER[r.clase], r.score))
    return ranked


def pair_class(pair: list) -> str:
    """Clase de un par/grupo = la peor de sus butacas."""
    return max((s.clase for s in pair), key=lambda c: _CLASS_ORDER[c])


def find_best_pair(available_seats: list, cantidad: int = 2) -> list[RankedSeat] | None:
    """
    Busca `cantidad` butacas CONTIGUAS (misma fila, números consecutivos)
    lo mejor clasificadas y más centradas posible. Devuelve None si no
    hay ningún grupo contiguo de ese tamaño.

    (El sitio exige seleccionar butacas contiguas, por eso dos asientos
    sueltos de la misma fila no sirven.)

    OJO: puede devolver un grupo de clase "else" si es lo único contiguo
    que hay. El filtro de "vale la pena avisar" lo hace main.py.
    """
    by_row: dict[str, list[int]] = {}
    for s in available_seats:
        by_row.setdefault(s.row, []).append(s.num)

    candidates: list[list] = []
    for row, nums in by_row.items():
        nums_sorted = sorted(set(nums))
        # cortar en corridas maximales de números consecutivos
        run: list[int] = []
        for n in nums_sorted + [None]:
            if run and n == run[-1] + 1:
                run.append(n)
                continue
            if len(run) >= cantidad:
                # todas las ventanas contiguas de tamaño `cantidad`
                for i in range(len(run) - cantidad + 1):
                    grupo = run[i:i + cantidad]
                    fake = [type("S", (), {"row": row, "num": x})() for x in grupo]
                    candidates.append(rank_seats(fake))
            run = [] if n is None else [n]

    if not candidates:
        return None

    def key(grupo: list):
        avg = sum(r.score for r in grupo) / len(grupo)
        return (_CLASS_ORDER[pair_class(grupo)], avg)

    return min(candidates, key=key)


# --------------------------------------------------------------------------- #
# Utilidad: imprimir la grilla completa
# --------------------------------------------------------------------------- #

def _ranges(nums: list[int]) -> str:
    if not nums:
        return "-"
    nums = sorted(nums)
    out, start, prev = [], nums[0], nums[0]
    for n in nums[1:]:
        if n == prev + 1:
            prev = n
            continue
        out.append(f"{start}" if start == prev else f"{start}-{prev}")
        start = prev = n
    out.append(f"{start}" if start == prev else f"{start}-{prev}")
    return ", ".join(out)


def print_grid() -> None:
    print(f"{'fila':4}  {'ancho':5}  {'IDEAL (butacas)':18}  "
          f"{'OK (butacas)':22}  else (butacas)")
    for row in ROW_ORDER:
        w = ROW_WIDTHS[row]
        buckets = {"ideal": [], "ok": [], "else": []}
        for n in range(1, w + 1):
            buckets[classify_seat(row, n)].append(n)
        print(f"{row:4}  {w:5}  {_ranges(buckets['ideal']):18}  "
              f"{_ranges(buckets['ok']):22}  {_ranges(buckets['else'])}")


if __name__ == "__main__":
    print_grid()
