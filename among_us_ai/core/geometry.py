"""
Utility geometriche e di sistema condivise fra editor, manager e renderer.

Funzioni "pure" senza side-effects (point-in-polygon, sampling random,
conversione colori) piu' :func:`get_client_rect` che chiama l'API Win32:
viene messa qui per comodita' di import, ma e' gated dal flag ``WIN_OK``.
"""

import random as _random

from .win_deps import WIN_OK, win32gui


def hex_to_rgba(hex_str, alpha=255):
    """Converte una stringa esadecimale ``'#RRGGBB'`` in tupla ``(R, G, B, A)``."""
    h = hex_str.lstrip('#')
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), alpha)


def get_client_rect(hwnd):
    """
    Restituisce ``(x, y, w, h)`` dell'area client (= contenuto interno alla
    finestra, esclusi bordi e barra del titolo) per la finestra Win32 indicata.

    Ritorna ``None`` se le dipendenze Win32 non sono disponibili
    (``WIN_OK=False``) o se l'HWND non e' valido.
    """
    if not WIN_OK:
        return None
    try:
        # GetWindowRect: rettangolo "esterno" (compreso bordo e titolo)
        # GetClientRect: dimensioni "interne" (sempre a partire da 0,0)
        rect = win32gui.GetWindowRect(hwnd)
        client_rect = win32gui.GetClientRect(hwnd)
        # Calcolo border + titolo come differenza fra i due rect.
        border_width = int((rect[2] - rect[0] - client_rect[2]) / 2)
        title_bar_height = int(rect[3] - rect[1] - client_rect[3] - border_width)
        return (rect[0] + border_width,
                rect[1] + title_bar_height,
                client_rect[2],
                client_rect[3])
    except Exception:
        return None


def point_in_polygon(px, py, poly):
    """
    Test point-in-polygon con algoritmo ray casting.

    :param px, py: coordinate del punto da testare
    :param poly:   lista di tuple ``[(x, y), ...]`` (sistema di riferimento
                   qualunque, basta che sia coerente fra punto e poligono)
    :return: ``True`` se il punto e' dentro il poligono.
    """
    n = len(poly)
    if n < 3:
        # Un "poligono" con meno di 3 vertici non racchiude area.
        return False
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        # Test classico di intersezione: il raggio orizzontale che parte
        # da (px,py) verso destra interseca il segmento (i,j)?
        # +1e-12 a denominatore per evitare divisione per zero su lati orizzontali.
        if ((yi > py) != (yj > py)) and \
           (px < (xj - xi) * (py - yi) / (yj - yi + 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def random_point_in_rect(rx1, ry1, rx2, ry2):
    """Punto random uniforme nel rettangolo definito da due angoli opposti."""
    # Normalizzo gli estremi cosi' funziona anche con angoli "invertiti".
    x1, x2 = min(rx1, rx2), max(rx1, rx2)
    y1, y2 = min(ry1, ry2), max(ry1, ry2)
    return _random.uniform(x1, x2), _random.uniform(y1, y2)


def random_point_in_poly(poly, max_tries=40):
    """
    Punto random uniforme dentro un poligono, via rejection sampling
    sulla bounding box.

    :param poly:      lista di tuple ``[(x, y), ...]``
    :param max_tries: dopo N tentativi falliti torna il centroide come
                      fallback (poligoni molto stretti potrebbero non
                      avere mai un hit "random").
    :return: tupla ``(x, y)`` dentro il poligono (o centroide come fallback).
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
        if point_in_polygon(rx, ry, poly):
            return rx, ry
    # Fallback: centroide (media aritmetica dei vertici - non e' il
    # baricentro vero del poligono ma e' "dentro" per poligoni convessi
    # e accettabile per i nostri casi d'uso).
    return sum(xs) / len(xs), sum(ys) / len(ys)
