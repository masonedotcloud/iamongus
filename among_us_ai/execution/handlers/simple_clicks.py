"""
Click semplici e poligonali.

Handler per le azioni di tipo: click, click_rect, click_poly.

Ogni funzione ha la firma standard:
    handle_<tipo>(az, ctx) -> None

dove ``az`` e' il dict dell'azione e ``ctx`` e' un namespace con i
parametri condivisi (cx, cy, cw, ch del rect del gioco; hwnd; flag
is_test). Le funzioni delegano i movimenti del mouse ai helper di
``_drag_utils.py``.
"""

import math
import os
import random
import time

import pyautogui

from .._drag_utils import (
    trascinamento_umano,
    trascinamento_multi,
    esegui_click_hold,
    trascinamento_e_tieni,
    trascinamento_seq_tappe,
)
from ...core.geometry import (
    random_point_in_rect,
    random_point_in_poly,
    point_in_polygon,
)


def handle_click(az, cx, cy, cw, ch, hwnd, is_test):
    """
    Click semplice in un punto del minigioco. Coordinate relative al rect del client (rx, ry in [0,1]).

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
    x = cx + int(az["rx"] * cw)
    y = cy + int(az["ry"] * ch)
    esegui_click_hold(x, y, durata)



def handle_click_rect(az, cx, cy, cw, ch, hwnd, is_test):
    """
    Click random in un rettangolo. Utile quando l'esatto pixel non conta.

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
    r = az["rect"]
    rx, ry = random_point_in_rect(r[0], r[1], r[2], r[3])
    x = cx + int(rx * cw); y = cy + int(ry * ch)
    esegui_click_hold(x, y, durata)



def handle_click_poly(az, cx, cy, cw, ch, hwnd, is_test):
    """
    Click random in un poligono. Stessa logica di click_rect ma con shape libera.

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
    rx, ry = random_point_in_poly(az["poly"])
    x = cx + int(rx * cw); y = cy + int(ry * ch)
    esegui_click_hold(x, y, durata)



