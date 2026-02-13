"""
Helper geometriche pure: poligono, rettangolo, sampling random, rect del client.

Non dipende da nessun altro modulo del package. Le funzioni qui sono
"matematica pura" + win32gui per il client rect.
"""
import math as _math
import random as _random

# win32gui usato solo da _client_rect; se non disponibile, _client_rect
# ritornera' None (gestito dal chiamante).
try:
    import win32gui as _win32gui
except Exception:
    _win32gui = None

def _client_rect(hwnd):
    # Restituisce (origin_x, origin_y, width, height) del CLIENT AREA del
    # gioco, in pixel schermo. Esclude bordi e barra del titolo della
    # finestra del SO. Restituisce None se la finestra non esiste.
    try:
        # Rect totale della finestra (incluso bordo + titolo)
        rect  = _win32gui.GetWindowRect(hwnd)
        # Rect del client (solo area utile interna)
        crect = _win32gui.GetClientRect(hwnd)
        # bw = larghezza bordo verticale (sinistro/destro identici)
        bw = int((rect[2] - rect[0] - crect[2]) / 2)
        # th = altezza barra titolo + bordo superiore
        th = int(rect[3] - rect[1] - crect[3] - bw)
        return rect[0] + bw, rect[1] + th, crect[2], crect[3]
    except Exception:
        return None


def _point_in_polygon(px, py, poly):
    # Test point-in-polygon classico con algoritmo "ray casting".
    # Ritorna True se il punto (px, py) e' DENTRO il poligono.
    # Funziona con poligoni concavi e auto-intersecanti.
    n = len(poly)
    if n < 3:
        # Meno di 3 vertici = degenere, considerato fuori
        return False
    inside = False
    j = n - 1  # indice del vertice precedente (chiusura del poligono)
    for i in range(n):
        xi, yi = poly[i]; xj, yj = poly[j]
        # Conta intersezioni del raggio orizzontale (verso destra) col lato i-j
        if ((yi > py) != (yj > py)) and \
           (px < (xj - xi) * (py - yi) / (yj - yi + 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def _random_in_rect(rect):
    # Punto random uniforme dentro un rettangolo [(x1,y1)-(x2,y2)].
    # Usa min/max per gestire rect con coordinate "invertite".
    x1, y1, x2, y2 = rect
    xa, xb = min(x1, x2), max(x1, x2)
    ya, yb = min(y1, y2), max(y1, y2)
    return _random.uniform(xa, xb), _random.uniform(ya, yb)


def _random_in_poly(poly):
    # Punto random uniforme dentro un poligono.
    # Strategia: rejection sampling sul bbox per max 40 tentativi,
    # fallback al centroide.
    if not poly:
        return 0.5, 0.5
    # Bounding box del poligono
    xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
    x1, x2 = min(xs), max(xs); y1, y2 = min(ys), max(ys)
    # Tenta 40 volte di trovare un punto dentro
    for _ in range(40):
        rx = _random.uniform(x1, x2); ry = _random.uniform(y1, y2)
        if _point_in_polygon(rx, ry, poly):
            return rx, ry
    # Fallback: centroide (media aritmetica dei vertici).
    # Non e' il vero centroide geometrico ma e' sempre dentro un poligono
    # convesso e quasi sempre dentro uno concavo.
    return sum(xs)/len(xs), sum(ys)/len(ys)


