"""
Handler per i tipi di azione di tipo "drag":
- drag         drag rettilineo punto-punto
- drag_multi   drag in sequenza fra N punti
- drag_zone    drag fra 2 zone (poligoni) con punti random
- drag_hold    drag rettilineo + hold finale
"""
import math as _math
from .geometria import _random_in_poly
from .input_mouse import _drag_umano, _drag_multi, _drag_e_tieni

def _h_drag(az, cx, cy, cw, ch, hwnd, durata, attesa):
    sx = cx + int(az['start_rx'] * cw)
    sy = cy + int(az['start_ry'] * ch)
    ex = cx + int(az['end_rx'] * cw)
    ey = cy + int(az['end_ry'] * ch)
    d = _math.hypot(az['end_rx'] - az['start_rx'], az['end_ry'] - az['start_ry'])
    _drag_umano(sx, sy, ex, ey, max(0.05, d * durata))


def _h_drag_multi(az, cx, cy, cw, ch, hwnd, durata, attesa):
    pts = [(cx + int(p[0] * cw), cy + int(p[1] * ch)) for p in az['punti']]
    rel = az['punti']
    tot = sum((_math.hypot(rel[i + 1][0] - rel[i][0], rel[i + 1][1] - rel[i][1]) for i in range(len(rel) - 1)))
    _drag_multi(pts, max(0.1, tot * durata))


def _h_drag_zone(az, cx, cy, cw, ch, hwnd, durata, attesa):
    sxr, syr = _random_in_poly(az['zone_a'])
    exr, eyr = _random_in_poly(az['zone_b'])
    d = _math.hypot(exr - sxr, eyr - syr)
    _drag_umano(cx + int(sxr * cw), cy + int(syr * ch), cx + int(exr * cw), cy + int(eyr * ch), max(0.05, d * durata))


def _h_drag_hold(az, cx, cy, cw, ch, hwnd, durata, attesa):
    sx = cx + int(az['start_rx'] * cw)
    sy = cy + int(az['start_ry'] * ch)
    ex = cx + int(az['end_rx'] * cw)
    ey = cy + int(az['end_ry'] * ch)
    d = _math.hypot(az['end_rx'] - az['start_rx'], az['end_ry'] - az['start_ry'])
    _drag_e_tieni(sx, sy, ex, ey, max(0.05, d * durata), az.get('hold', 0.0))


