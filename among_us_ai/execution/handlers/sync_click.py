"""
Click sincronizzato a un evento visivo (cambio colore pixel).

Handler per le azioni di tipo: sync_click.

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


def handle_sync_click(az, cx, cy, cw, ch, hwnd, is_test):
    """
    Click sincronizzato: aspetta che un pixel di check cambi colore prima di cliccare il pulsante.

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
    punti_sync = az.get('punti', [])
    i_sync = 0
    max_retries = 3
    retry_count = 0

    check_coords_abs = []
    for cx_rel, cy_rel, _, _ in punti_sync:
        check_coords_abs.append((cx + int(cx_rel * cw), cy + int(cy_rel * ch)))

    while i_sync < len(punti_sync):
        if retry_count >= max_retries:
            print(f"[sync_click] Tentativi massimi ({max_retries}) raggiunti. Annullamento.")
            break

        _, _, bx_rel, by_rel = punti_sync[i_sync]
        chk_x, chk_y = check_coords_abs[i_sync]
        btn_x = cx + int(bx_rel * cw)
        btn_y = cy + int(by_rel * ch)
        
        # Sposta il mouse alla posizione
        pyautogui.moveTo(btn_x, btn_y, duration=0.1)
        
        try:
            base_col = pyautogui.pixel(chk_x, chk_y)
        except Exception:
            base_col = (0, 0, 0)
        
        start_t = time.time()
        clicked = False
        while time.time() - start_t < 8.0:
            try:
                r, g, b = pyautogui.pixel(chk_x, chk_y)
                if (r + g + b) > 60 and (abs(r - base_col[0]) + abs(g - base_col[1]) + abs(b - base_col[2])) > 40:
                    # Click del mouse simulato via pyautogui
                    pyautogui.click()
                    clicked = True
                    break
            except Exception:
                pass
            # Pausa il thread per il tempo specificato (secondi)
            time.sleep(0.005)
        
        if not clicked:
            print(f"[sync_click] Timeout al punto {i_sync+1}. Riavvio sequenza.")
            i_sync = 0
            retry_count += 1
            # Pausa il thread per il tempo specificato (secondi)
            time.sleep(1.0)
            continue
        
        # Pausa il thread per il tempo specificato (secondi)
        time.sleep(0.2)

        sequence_failed = False
        failed_at_step = -1
        for k in range(i_sync + 1):
            prev_chk_x, prev_chk_y = check_coords_abs[k]
            try:
                r, g, b = pyautogui.pixel(prev_chk_x, prev_chk_y)
                if (r + g + b) < 75:
                    sequence_failed = True
                    failed_at_step = k + 1
                    break
            except Exception:
                sequence_failed = True
                failed_at_step = k + 1
                break
        
        if sequence_failed:
            print(f"[sync_click] Fallimento rilevato al passo {failed_at_step}. Riavvio (tentativo {retry_count + 1}/{max_retries}).")
            i_sync = 0
            retry_count += 1
            # Pausa il thread per il tempo specificato (secondi)
            time.sleep(0.75)
            continue
            
        i_sync += 1
    # Pausa il thread per il tempo specificato (secondi)
    time.sleep(attesa)



