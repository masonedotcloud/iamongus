"""
Matching numerico (per Stabilize Steering).

Handler per le azioni di tipo: number_match.

Ogni funzione ha la firma standard:
    handle_<tipo>(az, ctx) -> None

dove ``az`` e' il dict dell'azione e ``ctx`` e' un namespace con i
parametri condivisi (cx, cy, cw, ch del rect del gioco; hwnd; flag
is_test). Le funzioni delegano i movimenti del mouse ai helper di
``_drag_utils.py``.
"""

import time

from .._drag_utils import esegui_click_hold
# _extract_pure_shape estrae la forma binarizzata 40x40 da una ROI:
# serve a confrontare il template del numero target con i candidati.
from .._motore_pkg.input_mouse import _extract_pure_shape


def handle_number_match(az, cx, cy, cw, ch, hwnd, is_test):
    """
    Matching numerico: legge un numero target, trova il pulsante corrispondente e clicca.

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
    import cv2
    import numpy as np
    import mss
    buttons = az.get("buttons", [])
    if buttons:
        with mss.mss() as sct:
            for target_btn in buttons:
                target_template = np.array(target_btn['template'], dtype=np.uint8).reshape((40, 40))
                best_score = -1
                best_click_x, best_click_y = -1, -1
                
                screen = np.array(sct.grab({"left": cx, "top": cy, "width": cw, "height": ch}))
                
                for candidate_btn in buttons:
                    r = candidate_btn['rect']
                    x1, y1 = int(min(r[0], r[2])*cw), int(min(r[1], r[3])*ch)
                    x2, y2 = int(max(r[0], r[2])*cw), int(max(r[1], r[3])*ch)
                    roi = screen[y1:y2, x1:x2]
                    if roi.size == 0: continue
                    
                    current_shape = _extract_pure_shape(roi)
                    res = cv2.matchTemplate(current_shape, target_template, cv2.TM_CCOEFF_NORMED)
                    _, max_val, _, _ = cv2.minMaxLoc(res)
                    if max_val > best_score:
                        best_score = max_val
                        best_click_x = cx + x1 + (x2 - x1)//2
                        best_click_y = cy + y1 + (y2 - y1)//2
                if best_click_x != -1:
                    esegui_click_hold(best_click_x, best_click_y, durata)
                    # Pausa il thread per il tempo specificato (secondi)
                    time.sleep(attesa)
                    


