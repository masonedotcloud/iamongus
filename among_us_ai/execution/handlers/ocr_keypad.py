"""
Lettura OCR di un keypad poi click.

Handler per le azioni di tipo: ocr_keypad.

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


def handle_ocr_keypad(az, cx, cy, cw, ch, hwnd, is_test):
    """
    Lettura OCR di un display di numeri, poi click sui tasti corrispondenti.

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
    try:
        import easyocr
        import mss
        import numpy as np
        import re
    except ImportError:
        print("[OCR] Dipendenze mancanti (easyocr non installato).")
        return
    roi_poly = az.get('roi_poly', [])
    keypad = az.get('keypad', [])
    if len(roi_poly) >= 3 and len(keypad) == 10:
        with mss.mss() as sct:
            xs = [p[0] for p in roi_poly]; ys = [p[1] for p in roi_poly]
            ml = cx + int(min(xs)*cw); mt = cy + int(min(ys)*ch)
            mw = int((max(xs)-min(xs))*cw); mh = int((max(ys)-min(ys))*ch)
            monitor = {"top": mt, "left": ml, "width": mw, "height": mh}
            sct_img = np.array(sct.grab(monitor))
            img_rgb = sct_img[:, :, :3]
            try:
                print("[OCR] Lettura immagine in corso...")
                reader = easyocr.Reader(['en'], gpu=False)
                res = reader.readtext(img_rgb, detail=0)
                nums = re.sub(r'\D', '', "".join(res))
                print(f"[OCR] Numeri letti: '{nums}'")
                for ch_num in nums:
                    idx = int(ch_num)
                    kx = cx + int(keypad[idx][0]*cw)
                    ky = cy + int(keypad[idx][1]*ch)
                    esegui_click_hold(kx, ky, durata)
                    # Pausa il thread per il tempo specificato (secondi)
                    time.sleep(0.15)
            except Exception as e:
                print(f"[OCR] Errore lettura OCR: {e}")
    # Pausa il thread per il tempo specificato (secondi)
    time.sleep(attesa)



