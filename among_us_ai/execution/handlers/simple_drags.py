"""
Drag semplici e in zona.

Handler per le azioni di tipo: drag, drag_multi, drag_zone, drag_hold.

Ogni funzione ha la firma standard:
    handle_<tipo>(az, ctx) -> None

dove ``az`` e' il dict dell'azione e ``ctx`` e' un namespace con i
parametri condivisi (cx, cy, cw, ch del rect del gioco; hwnd; flag
is_test). Le funzioni delegano i movimenti del mouse ai helper di
``_drag_utils.py``.
"""

import math

from .._drag_utils import (
    trascinamento_umano,
    trascinamento_multi,
    trascinamento_e_tieni,
)
from ...core.geometry import random_point_in_poly

def handle_drag(az, cx, cy, cw, ch, hwnd, is_test):
    """
    Trascinamento da (start_rx, start_ry) a (end_rx, end_ry). La durata e' proporzionale alla distanza.

    Parametri
    ---------
    az : dict
        Dizionario dell'azione (chiavi specifiche del tipo).
    cx, cy : int
        Origine (top-left) del rect del client del gioco.
    cw, ch : int
        Larghezza e altezza del rect del client.
    hwnd : int
        Handle della finestra del gioco (per check foreground).
    is_test : bool
        True se chiamato dal pulsante "Test" dell'editor (modalita' verbosa).
    """
    durata = az.get("durata", 0.0)
    attesa = az.get("attesa", 0.0)
    sx = cx + int(az["start_rx"] * cw); sy = cy + int(az["start_ry"] * ch)
    ex = cx + int(az["end_rx"]   * cw); ey = cy + int(az["end_ry"]   * ch)
    dist_rel = math.hypot(az["end_rx"] - az["start_rx"],
                          az["end_ry"] - az["start_ry"])
    dur_fin = max(0.05, dist_rel * durata)
    trascinamento_umano(sx, sy, ex, ey, dur_fin)


def handle_drag_multi(az, cx, cy, cw, ch, hwnd, is_test):
    """
    Drag in sequenza su piu' punti senza rilasciare il tasto (per asteroidi).

    Parametri
    ---------
    az : dict
        Dizionario dell'azione (chiavi specifiche del tipo).
    cx, cy : int
        Origine (top-left) del rect del client del gioco.
    cw, ch : int
        Larghezza e altezza del rect del client.
    hwnd : int
        Handle della finestra del gioco (per check foreground).
    is_test : bool
        True se chiamato dal pulsante "Test" dell'editor (modalita' verbosa).
    """
    durata = az.get("durata", 0.0)
    attesa = az.get("attesa", 0.0)
    punti_abs = [(cx + int(px * cw), cy + int(py * ch))
                 for px, py in az["punti"]]
    total_rel = 0.0
    pts_rel = az["punti"]
    for i in range(len(pts_rel) - 1):
        total_rel += math.hypot(pts_rel[i+1][0] - pts_rel[i][0],
                                pts_rel[i+1][1] - pts_rel[i][1])
    dur_fin = max(0.1, total_rel * durata)
    trascinamento_multi(punti_abs, dur_fin)


def handle_drag_zone(az, cx, cy, cw, ch, hwnd, is_test):
    """
    Drag che inizia in un punto random di una zona A e finisce in un punto random di una zona B.

    Parametri
    ---------
    az : dict
        Dizionario dell'azione (chiavi specifiche del tipo).
    cx, cy : int
        Origine (top-left) del rect del client del gioco.
    cw, ch : int
        Larghezza e altezza del rect del client.
    hwnd : int
        Handle della finestra del gioco (per check foreground).
    is_test : bool
        True se chiamato dal pulsante "Test" dell'editor (modalita' verbosa).
    """
    durata = az.get("durata", 0.0)
    attesa = az.get("attesa", 0.0)
    sx_r, sy_r = random_point_in_poly(az["zone_a"])
    ex_r, ey_r = random_point_in_poly(az["zone_b"])
    sx = cx + int(sx_r * cw); sy = cy + int(sy_r * ch)
    ex = cx + int(ex_r * cw); ey = cy + int(ey_r * ch)
    dist_rel = math.hypot(ex_r - sx_r, ey_r - sy_r)
    dur_fin = max(0.05, dist_rel * durata)
    trascinamento_umano(sx, sy, ex, ey, dur_fin)


def handle_drag_hold(az, cx, cy, cw, ch, hwnd, is_test):
    """
    Drag che mantiene il tasto premuto alla fine per un tempo aggiuntivo.

    Parametri
    ---------
    az : dict
        Dizionario dell'azione (chiavi specifiche del tipo).
    cx, cy : int
        Origine (top-left) del rect del client del gioco.
    cw, ch : int
        Larghezza e altezza del rect del client.
    hwnd : int
        Handle della finestra del gioco (per check foreground).
    is_test : bool
        True se chiamato dal pulsante "Test" dell'editor (modalita' verbosa).
    """
    durata = az.get("durata", 0.0)
    attesa = az.get("attesa", 0.0)
    sx = cx + int(az["start_rx"] * cw); sy = cy + int(az["start_ry"] * ch)
    ex = cx + int(az["end_rx"]   * cw); ey = cy + int(az["end_ry"]   * ch)
    dist_rel  = math.hypot(az["end_rx"] - az["start_rx"],
                           az["end_ry"] - az["start_ry"])
    dur_drag  = max(0.05, dist_rel * durata)
    hold_time = max(0.0, az.get("hold", 0.0))
    trascinamento_e_tieni(sx, sy, ex, ey, dur_drag, hold_time)
    


