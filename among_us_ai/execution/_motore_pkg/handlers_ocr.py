"""
Handler per i minigiochi che richiedono OCR / matching numerico.

- number_match  cerca un numero target su un display (Stabilize Steering)
- ocr_keypad    legge le cifre di un keypad e clicca quelle richieste
"""
import time as _time
try:
    import pyautogui as _pag
except Exception:
    _pag = None
from .input_mouse import _click_hold, _extract_pure_shape

def _h_number_match(az, cx, cy, cw, ch, hwnd, durata, attesa):
    """
    Handler ``number_match``: minigioco "Stabilize Steering" / scelta numero.

    Per ogni bottone target (con template salvato in fase di registrazione),
    confronta il template con la "forma pura" di tutti i bottoni candidati
    a schermo e clicca quello con la match score piu' alta (template matching
    via OpenCV ``cv2.matchTemplate`` con ``TM_CCOEFF_NORMED``).
    """
    import cv2
    import numpy as np
    import mss as _mss
    buttons = az.get('buttons', [])
    if buttons:
        with _mss.mss() as sct:
            for target_btn in buttons:
                # Template 40x40 della cifra da cercare (salvato durante la
                # registrazione, passa per _extract_pure_shape).
                target_template = np.array(target_btn['template'],
                                            dtype=np.uint8).reshape((40, 40))
                best_score = -1
                best_click_x, best_click_y = (-1, -1)
                # Cattura unica della finestra (piu' rapido di N pixel lookup).
                screen = np.array(sct.grab({'left': cx, 'top': cy,
                                            'width': cw, 'height': ch}))
                for candidate_btn in buttons:
                    r = candidate_btn['rect']
                    x1, y1 = (int(min(r[0], r[2]) * cw),
                              int(min(r[1], r[3]) * ch))
                    x2, y2 = (int(max(r[0], r[2]) * cw),
                              int(max(r[1], r[3]) * ch))
                    roi = screen[y1:y2, x1:x2]
                    if roi.size == 0:
                        continue
                    current_shape = _extract_pure_shape(roi)
                    res = cv2.matchTemplate(current_shape, target_template,
                                            cv2.TM_CCOEFF_NORMED)
                    _, max_val, _, _ = cv2.minMaxLoc(res)
                    if max_val > best_score:
                        best_score = max_val
                        best_click_x = cx + x1 + (x2 - x1) // 2
                        best_click_y = cy + y1 + (y2 - y1) // 2
                if best_click_x != -1:
                    _click_hold(best_click_x, best_click_y, durata)
                    _time.sleep(attesa)


def _h_ocr_keypad(az, cx, cy, cw, ch, hwnd, durata, attesa):
    """
    Handler ``ocr_keypad``: legge una sequenza di cifre da un display e
    le digita sul keypad sottostante (es. login code).

    Usa ``easyocr`` (lazy import: se non installato, no-op con messaggio).
    Schema:
      - ``az['roi_poly']``: poligono del display da OCR-are
      - ``az['keypad']``: lista 10 elementi con le posizioni dei tasti 0-9
    """
    try:
        import easyocr
        import mss as _mss
        import numpy as _np
        import re as _re
    except ImportError:
        print('[OCR] Dipendenze mancanti (easyocr non installato).')
        return
    roi = az.get('roi_poly', [])
    keypad = az.get('keypad', [])
    if len(roi) >= 3 and len(keypad) == 10:
        with _mss.mss() as sct:
            # Bounding box del poligono ROI = rettangolo da catturare.
            xs = [p[0] for p in roi]
            ys = [p[1] for p in roi]
            ml = cx + int(min(xs) * cw)
            mt = cy + int(min(ys) * ch)
            mw = int((max(xs) - min(xs)) * cw)
            mh = int((max(ys) - min(ys)) * ch)
            img = _np.array(sct.grab({'top': mt, 'left': ml,
                                       'width': mw, 'height': mh}))[:, :, :3]
            try:
                # NB: easyocr e' lento al primo init (~3-5s). Per cio'
                # alcuni utenti preferiscono "warmare" il reader in
                # background prima del lancio della task.
                print('[OCR] Inizializzazione EasyOCR in corso...')
                reader = easyocr.Reader(['en'], gpu=False)
                res = reader.readtext(img, detail=0)
                # Estraggo solo le cifre (regex \D = non-cifra).
                nums = _re.sub('\\D', '', ''.join(res))
                print(f"[OCR] Numeri rilevati: '{nums}'")
                # Digito la sequenza sul keypad.
                for ch_num in nums:
                    idx = int(ch_num)
                    kx = cx + int(keypad[idx][0] * cw)
                    ky = cy + int(keypad[idx][1] * ch)
                    _click_hold(kx, ky, durata)
                    _time.sleep(0.15)
            except Exception as e:
                print(f'[OCR] Errore lettura: {e}')
    _time.sleep(attesa)


