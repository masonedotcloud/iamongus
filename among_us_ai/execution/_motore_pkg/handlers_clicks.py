"""
Handler per i tipi di azione di tipo "click":
- click          click semplice in un punto
- click_rect     click random in un rettangolo (anti-detection)
- click_poly     click random in un poligono
- click_until    click ripetuto finche' un colore cambia
"""
import time as _time
try:
    import pyautogui as _pag
except Exception:
    _pag = None
from .geometria import _random_in_rect, _random_in_poly
from .input_mouse import _click_hold

def _h_click(az, cx, cy, cw, ch, hwnd, durata, attesa):
    _click_hold(cx + int(az['rx'] * cw), cy + int(az['ry'] * ch), durata)


def _h_click_rect(az, cx, cy, cw, ch, hwnd, durata, attesa):
    rx, ry = _random_in_rect(az['rect'])
    _click_hold(cx + int(rx * cw), cy + int(ry * ch), durata)


def _h_click_poly(az, cx, cy, cw, ch, hwnd, durata, attesa):
    rx, ry = _random_in_poly(az['poly'])
    _click_hold(cx + int(rx * cw), cy + int(ry * ch), durata)


def _h_click_until(az, cx, cy, cw, ch, hwnd, durata, attesa):
    for cx_rel, cy_rel, bx_rel, by_rel in az.get('punti', []):
        chk_x = cx + int(cx_rel * cw)
        chk_y = cy + int(cy_rel * ch)
        btn_x = cx + int(bx_rel * cw)
        btn_y = cy + int(by_rel * ch)
        _pag.moveTo(btn_x, btn_y, duration=0.1)
        start_t = _time.time()
        while _time.time() - start_t < 8.0:
            try:
                r, g, b = _pag.pixel(chk_x, chk_y)
                if r > 200 and g > 200 and (b > 200):
                    break
                _pag.click()
                _pag.mouseDown(button='left')
                _time.sleep(0.03)
                _pag.mouseUp(button='left')
            except Exception:
                pass
            _time.sleep(0.05)
    _time.sleep(attesa)


