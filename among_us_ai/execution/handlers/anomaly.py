"""
Rilevamento "anomalia": click sull'unico elemento diverso.

Handler per le azioni di tipo: click_anomaly.

Ogni funzione ha la firma standard:
    handle_<tipo>(az, ctx) -> None

dove ``az`` e' il dict dell'azione e ``ctx`` e' un namespace con i
parametri condivisi (cx, cy, cw, ch del rect del gioco; hwnd; flag
is_test). Le funzioni delegano i movimenti del mouse ai helper di
``_drag_utils.py``.
"""

import time

import pyautogui

from .._drag_utils import esegui_click_hold

def handle_click_anomaly(az, cx, cy, cw, ch, hwnd, is_test):
    """
    Identifica l'unico elemento "diverso" tra una serie di pulsanti e ci clicca sopra.

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
    # Pausa il thread per il tempo specificato (secondi)
    time.sleep(1.0)
    chk_pts = [(cx + int(p[0]*cw), cy + int(p[1]*ch)) for p in az.get('punti', [])]
    btn_pts = []
    for p in az.get('punti', []):
        if len(p) >= 4:
            btn_pts.append((cx + int(p[2]*cw), cy + int(p[3]*ch)))
        else:
            btn_pts.append((cx + int(p[0]*cw), cy + int(p[1]*ch)))
    if len(chk_pts) >= 3:
        colori = []
        try:
            import mss
            import numpy as np
            # Cattura uno screenshot della regione del gioco
            with mss.mss() as sct:
                monitor = {"top": cy, "left": cx, "width": cw, "height": ch}
                sct_img = np.array(sct.grab(monitor))
                for px, py in chk_pts:
                    y_idx = max(0, min(ch - 1, py - cy))
                    x_idx = max(0, min(cw - 1, px - cx))
                    b, g, r, _ = sct_img[y_idx, x_idx]
                    colori.append((int(r), int(g), int(b)))
        except Exception:
            for px, py in chk_pts:
                try:
                    colori.append(pyautogui.pixel(px, py))
                except Exception:
                    colori.append((0, 0, 0))
        
        max_dist = -1
        anomalo_idx = 0
        for i in range(len(colori)):
            dist_sum = 0
            for j in range(len(colori)):
                if i != j:
                    dist_sum += abs(colori[i][0]-colori[j][0]) + abs(colori[i][1]-colori[j][1]) + abs(colori[i][2]-colori[j][2])
            if dist_sum > max_dist:
                max_dist = dist_sum
                anomalo_idx = i
        print(f"[Anomalia] Colori: {colori} -> Scelto bottone {anomalo_idx}")
        esegui_click_hold(btn_pts[anomalo_idx][0], btn_pts[anomalo_idx][1], durata)
    # Pausa il thread per il tempo specificato (secondi)
    time.sleep(attesa)
    


