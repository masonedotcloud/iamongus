"""
Utility geometriche e di sistema condivise tra editor, manager e renderer.

Funzioni "pure" (no side-effects): point-in-polygon, sampling random,
# Ottiene il rect (x, y, w, h) dell'area client del gioco
conversione colori. Piu' `get_client_rect()` che usa l'API Windows ma e'
qui per comodita' di import.
"""

import random as _random

from .win_deps import WIN_OK, win32gui


def hex_to_rgba(hex_str, alpha=255):
    """Converte una stringa esadecimale '#RRGGBB' in tupla (R, G, B, A)."""
    h = hex_str.lstrip('#')
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), alpha)


# Ottiene il rect (x, y, w, h) dell'area client del gioco
def get_client_rect(hwnd):
    """
    Ritorna (x, y, w, h) dell'area client della finestra bersaglio.
    None se win32 non disponibile o errore.
    """
    if not WIN_OK:
        return None
    try:
        rect = win32gui.GetWindowRect(hwnd)
        client_rect = win32gui.GetClientRect(hwnd)
        border_width = int((rect[2] - rect[0] - client_rect[2]) / 2)
        title_bar_height = int(rect[3] - rect[1] - client_rect[3] - border_width)
        return (rect[0] + border_width,
                rect[1] + title_bar_height,
                client_rect[2],
                client_rect[3])
    except Exception:
        return None


# Test point-in-polygon (Ray casting)
def point_in_polygon(px, py, poly):
    """Ray casting. `poly = [(x, y), ...]` in coordinate qualunque."""
    n = len(poly)
    if n < 3:
        return False
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > py) != (yj > py)) and \
           (px < (xj - xi) * (py - yi) / (yj - yi + 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def random_point_in_rect(rx1, ry1, rx2, ry2):
    """Punto random uniforme in un rettangolo definito dai due angoli."""
    x1, x2 = min(rx1, rx2), max(rx1, rx2)
    y1, y2 = min(ry1, ry2), max(ry1, ry2)
    return _random.uniform(x1, x2), _random.uniform(y1, y2)


def random_point_in_poly(poly, max_tries=40):
    """
    Bounding-box rejection sampling.
    Se non trova un punto valido entro `max_tries` tentativi torna il
    centroide della polilinea.
    """
    if not poly:
        return 0.5, 0.5
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    x1, x2 = min(xs), max(xs)
    y1, y2 = min(ys), max(ys)
    for _ in range(max_tries):
        rx = _random.uniform(x1, x2)
        ry = _random.uniform(y1, y2)
        # Test point-in-polygon (Ray casting)
        if point_in_polygon(rx, ry, poly):
            return rx, ry
    return sum(xs) / len(xs), sum(ys) / len(ys)
