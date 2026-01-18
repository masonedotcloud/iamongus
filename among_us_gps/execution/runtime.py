"""
Motore di esecuzione delle azioni registrate (runtime).

Eseguito quando l'utente clicca "Test" nell'editor — preme/trascina il mouse
sulla finestra di Among Us, eseguendo la sequenza di azioni di una task in
modo umano (movimenti Bezier con jitter, durate randomizzate).

Lo stesso motore in versione INLINE è anche embedded nel template caricato
da `task_template.py` per i file `.py` generati nei `tasks_exec/`. Le due
implementazioni convivono apposta: questo modulo dipende dalla dashboard
(usa import diretti), il template è autonomo (re-importa al bisogno).

Tutte le funzioni assumono che l'ambiente Windows (mss, win32gui, pyautogui,
cv2, numpy) sia inizializzato — vedi `core.win_deps`.
"""

import math
import random
import time

import numpy as np
import pyautogui
import win32gui

from ..core.geometry import (
    get_client_rect,
    point_in_polygon,
    random_point_in_rect,
    random_point_in_poly,
)
from ..core.win_deps import WIN_OK as _OK
from ..core import stop_flag

# Alias storici usati internamente.
_client_rect = get_client_rect
_WIN_OK      = _OK         # alcuni rami di esegui_azioni controllano _WIN_OK
_time        = time        # alias usato in alcuni rami YOLO/OCR del codice originale


def trascinamento_umano(sx, sy, ex, ey, durata):
    pyautogui.moveTo(sx, sy, duration=random.uniform(0.15, 0.25),
                     tween=pyautogui.easeOutQuad)
    pyautogui.mouseDown(button='left')
    time.sleep(random.uniform(0.05, 0.1))

    if durata > 0:
        steps = max(10, int(durata * 60))
        sleep_time = durata / steps
        offset_dist = random.randint(-40, 40)
        mid_x = (sx + ex) / 2 + offset_dist
        mid_y = (sy + ey) / 2 + offset_dist
        for i in range(1, steps + 1):
            t = i / steps
            t_eased = -(math.cos(math.pi * t) - 1) / 2
            cur_x = int((1 - t_eased) ** 2 * sx
                        + 2 * (1 - t_eased) * t_eased * mid_x
                        + t_eased ** 2 * ex)
            cur_y = int((1 - t_eased) ** 2 * sy
                        + 2 * (1 - t_eased) * t_eased * mid_y
                        + t_eased ** 2 * ey)
            pyautogui.moveTo(cur_x, cur_y)
            time.sleep(sleep_time)
        pyautogui.moveTo(ex, ey)
    else:
        pyautogui.moveTo(ex, ey)

    time.sleep(random.uniform(0.05, 0.15))
    pyautogui.mouseUp(button='left')


def trascinamento_multi(punti_abs, durata_totale):
    if len(punti_abs) < 2:
        return
    sx, sy = punti_abs[0]
    pyautogui.moveTo(sx, sy, duration=random.uniform(0.15, 0.25),
                     tween=pyautogui.easeOutQuad)
    pyautogui.mouseDown(button='left')
    time.sleep(random.uniform(0.05, 0.1))

    total_dist = 0.0
    for i in range(len(punti_abs) - 1):
        dx = punti_abs[i+1][0] - punti_abs[i][0]
        dy = punti_abs[i+1][1] - punti_abs[i][1]
        total_dist += math.hypot(dx, dy)

    if total_dist <= 0:
        pyautogui.mouseUp(button='left'); return

    for i in range(len(punti_abs) - 1):
        ax, ay = punti_abs[i]
        bx, by = punti_abs[i+1]
        seg_dist = math.hypot(bx - ax, by - ay)
        dur_seg = max(0.05, durata_totale * (seg_dist / total_dist))
        steps = max(6, int(dur_seg * 60))
        sleep_time = dur_seg / steps
        offset_dist = random.randint(-3, 3)
        mid_x = (ax + bx) / 2 + offset_dist
        mid_y = (ay + by) / 2 + offset_dist
        for k in range(1, steps + 1):
            t = k / steps
            t_eased = -(math.cos(math.pi * t) - 1) / 2
            cur_x = int((1 - t_eased) ** 2 * ax
                        + 2 * (1 - t_eased) * t_eased * mid_x
                        + t_eased ** 2 * bx)
            cur_y = int((1 - t_eased) ** 2 * ay
                        + 2 * (1 - t_eased) * t_eased * mid_y
                        + t_eased ** 2 * by)
            pyautogui.moveTo(cur_x, cur_y)
            time.sleep(sleep_time)
        pyautogui.moveTo(bx, by)

    time.sleep(random.uniform(0.05, 0.15))
    pyautogui.mouseUp(button='left')


def esegui_click_hold(x, y, durata):
    pyautogui.moveTo(x, y, duration=0.1)
    if durata > 0:
        pyautogui.mouseDown()
        time.sleep(durata)
        pyautogui.mouseUp()
    else:
        pyautogui.click()


# Alias storico: alcuni rami di esegui_azioni usano _click_hold (eredita
# dal template inline che ha il prefisso underscore per convenzione).
_click_hold = esegui_click_hold


def trascinamento_e_tieni(sx, sy, ex, ey, durata_drag, hold_time):
    """
    Drag Bezier umano da (sx,sy) a (ex,ey), poi mantiene il tasto sinistro
    premuto su (ex,ey) per hold_time secondi, poi rilascia.
    Equivale a: pressione @A → trascina → attendi @B → rilascio.
    """
    pyautogui.moveTo(sx, sy, duration=random.uniform(0.15, 0.25),
                     tween=pyautogui.easeOutQuad)
    pyautogui.mouseDown(button='left')
    time.sleep(random.uniform(0.05, 0.1))
    if durata_drag > 0:
        steps = max(10, int(durata_drag * 60))
        sleep_t = durata_drag / steps
        off = random.randint(-40, 40)
        mx = (sx + ex) / 2 + off
        my = (sy + ey) / 2 + off
        for i in range(1, steps + 1):
            _t = i / steps
            te = -(math.cos(math.pi * _t) - 1) / 2
            pyautogui.moveTo(
                int((1 - te)**2 * sx + 2*(1-te)*te * mx + te**2 * ex),
                int((1 - te)**2 * sy + 2*(1-te)*te * my + te**2 * ey))
            time.sleep(sleep_t)
        pyautogui.moveTo(ex, ey)
    else:
        pyautogui.moveTo(ex, ey)
    if hold_time > 0:
        time.sleep(hold_time)
    pyautogui.mouseUp(button='left')


def trascinamento_seq_tappe(punti_abs, durata_segmento):
    if len(punti_abs) < 2:
        return
    sx, sy = punti_abs[0]
    pyautogui.moveTo(sx, sy, duration=random.uniform(0.15, 0.25), tween=pyautogui.easeOutQuad)
    pyautogui.mouseDown(button='left')
    time.sleep(random.uniform(0.05, 0.1))

    dur_seg = max(0.25, durata_segmento)
    for i in range(1, len(punti_abs)):
        bx, by = punti_abs[i]
        pyautogui.moveTo(bx, by, duration=dur_seg, tween=pyautogui.easeInOutQuad)
        time.sleep(0.15)

    time.sleep(random.uniform(0.05, 0.15))
    pyautogui.mouseUp(button='left')


def _extract_pure_shape(roi_image):
    """Estrae la forma in B/N ridimensionata a 40x40 per il confronto."""
    import cv2
    import numpy as np
    gray = cv2.cvtColor(roi_image, cv2.COLOR_BGRA2GRAY) if roi_image.shape[2] == 4 else cv2.cvtColor(roi_image, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 120, 255, cv2.THRESH_BINARY_INV)
    points = cv2.findNonZero(thresh)
    if points is not None:
        tx, ty, tw, th = cv2.boundingRect(points)
        cropped = thresh[ty:ty+th, tx:tx+tw]
        size = max(tw, th)
        top = (size - th) // 2
        bottom = size - th - top
        left = (size - tw) // 2
        right = size - tw - left
        square = cv2.copyMakeBorder(cropped, top, bottom, left, right, cv2.BORDER_CONSTANT, value=0)
        res = cv2.resize(square, (40, 40), interpolation=cv2.INTER_AREA)
    else:
        res = cv2.resize(thresh, (40, 40))
    return cv2.GaussianBlur(res, (3, 3), 0)


def esegui_azioni(azioni, hwnd, current_step=0, is_test=False):
    if not _WIN_OK:
        return False

    chunks = []
    current_chunk = []
    cooldowns = []
    for az in azioni:
        if az.get('tipo') == 'cooldown':
            chunks.append(current_chunk)
            cooldowns.append(az.get('durata', 0.0))
            current_chunk = []
        else:
            current_chunk.append(az)
    chunks.append(current_chunk)

    if current_step >= len(chunks):
        current_step = max(0, len(chunks) - 1)

    azioni_da_eseguire = chunks[current_step] if not is_test else azioni

    for az in azioni_da_eseguire:
        if is_test and stop_flag.requested:
            print("[Test] Sequenza interrotta dall'utente.")
            break

        if _WIN_OK and win32gui.GetForegroundWindow() != hwnd:
            print("[Esecuzione] Gioco non in primo piano, in pausa...")
            while win32gui.GetForegroundWindow() != hwnd:
                if is_test and stop_flag.requested:
                    break
                time.sleep(0.5)
            time.sleep(0.3)

        rect = get_client_rect(hwnd)
        if not rect:
            return False
        cx, cy, cw, ch = rect
        tipo = az.get("tipo")
        durata = az.get("durata", 0.0)
        attesa = az.get("attesa", 0.0)

        if tipo == "cooldown":
            if is_test:
                print(f"[Test] Attesa cooldown di {durata}s...")
                time.sleep(durata)
            continue

        if tipo == "click":
            x = cx + int(az["rx"] * cw)
            y = cy + int(az["ry"] * ch)
            esegui_click_hold(x, y, durata)

        elif tipo == "click_rect":
            r = az["rect"]
            rx, ry = random_point_in_rect(r[0], r[1], r[2], r[3])
            x = cx + int(rx * cw); y = cy + int(ry * ch)
            esegui_click_hold(x, y, durata)

        elif tipo == "click_poly":
            rx, ry = random_point_in_poly(az["poly"])
            x = cx + int(rx * cw); y = cy + int(ry * ch)
            esegui_click_hold(x, y, durata)

        elif tipo == "drag":
            sx = cx + int(az["start_rx"] * cw); sy = cy + int(az["start_ry"] * ch)
            ex = cx + int(az["end_rx"]   * cw); ey = cy + int(az["end_ry"]   * ch)
            dist_rel = math.hypot(az["end_rx"] - az["start_rx"],
                                  az["end_ry"] - az["start_ry"])
            dur_fin = max(0.05, dist_rel * durata)
            trascinamento_umano(sx, sy, ex, ey, dur_fin)

        elif tipo == "drag_multi":
            punti_abs = [(cx + int(px * cw), cy + int(py * ch))
                         for px, py in az["punti"]]
            total_rel = 0.0
            pts_rel = az["punti"]
            for i in range(len(pts_rel) - 1):
                total_rel += math.hypot(pts_rel[i+1][0] - pts_rel[i][0],
                                        pts_rel[i+1][1] - pts_rel[i][1])
            dur_fin = max(0.1, total_rel * durata)
            trascinamento_multi(punti_abs, dur_fin)
        elif tipo == 'drag_zone':
            sx_r, sy_r = random_point_in_poly(az["zone_a"])
            ex_r, ey_r = random_point_in_poly(az["zone_b"])
            sx = cx + int(sx_r * cw); sy = cy + int(sy_r * ch)
            ex = cx + int(ex_r * cw); ey = cy + int(ey_r * ch)
            dist_rel = math.hypot(ex_r - sx_r, ey_r - sy_r)
            dur_fin = max(0.05, dist_rel * durata)
            trascinamento_umano(sx, sy, ex, ey, dur_fin)

        elif tipo == "drag_hold":
            sx = cx + int(az["start_rx"] * cw); sy = cy + int(az["start_ry"] * ch)
            ex = cx + int(az["end_rx"]   * cw); ey = cy + int(az["end_ry"]   * ch)
            dist_rel  = math.hypot(az["end_rx"] - az["start_rx"],
                                   az["end_ry"] - az["start_ry"])
            dur_drag  = max(0.05, dist_rel * durata)
            hold_time = max(0.0, az.get("hold", 0.0))
            trascinamento_e_tieni(sx, sy, ex, ey, dur_drag, hold_time)
            
        elif tipo == "wiring":
            left_pts = az.get('left', [])
            right_pts = az.get('right', [])
            light_pts = az.get('lights', [])
            disp_dx = list(range(len(right_pts)))
            
            for i in range(len(left_pts)):
                start_rx, start_ry = left_pts[i]
                sx = cx + int(start_rx * cw); sy = cy + int(start_ry * ch)
                
                try:
                    col_sx = pyautogui.pixel(sx, sy)
                except Exception:
                    col_sx = (0, 0, 0)
                    
                target_scelti = []
                for r_idx in disp_dx:
                    end_rx, end_ry = right_pts[r_idx]
                    ex = cx + int(end_rx * cw); ey = cy + int(end_ry * ch)
                    try:
                        col_dx = pyautogui.pixel(ex, ey)
                        diff = abs(col_sx[0]-col_dx[0]) + abs(col_sx[1]-col_dx[1]) + abs(col_sx[2]-col_dx[2])
                    except Exception:
                        col_dx = (0, 0, 0)
                        diff = 999
                    target_scelti.append((diff, r_idx))
                    print(f"[Wiring] Cavo sx {i} {col_sx} vs Target dx {r_idx} {col_dx} -> diff: {diff}")
                target_scelti.sort(key=lambda item: item[0])
                ordine_tentativi = [t[1] for t in target_scelti]
                
                pyautogui.moveTo(sx, sy, duration=0.15)
                pyautogui.mouseDown(button='left')
                time.sleep(0.1)
                for r_idx in ordine_tentativi:
                    end_rx, end_ry = right_pts[r_idx]
                    ex = cx + int(end_rx * cw); ey = cy + int(end_ry * ch)
                    light_rx, light_ry = light_pts[r_idx]
                    lx = cx + int(light_rx * cw); ly = cy + int(light_ry * ch)
                    pyautogui.moveTo(ex, ey, duration=0.25)
                    time.sleep(0.1)
                    try:
                        r, g, b = pyautogui.pixel(lx, ly)
                        if r > 160 and g > 150 and b < 100:
                            disp_dx.remove(r_idx)
                            break
                    except Exception:
                        pass
                pyautogui.mouseUp(button='left')
                time.sleep(attesa)

        elif tipo == 'sync_click':
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
                            pyautogui.click()
                            clicked = True
                            break
                    except Exception:
                        pass
                    time.sleep(0.005)
                
                if not clicked:
                    print(f"[sync_click] Timeout al punto {i_sync+1}. Riavvio sequenza.")
                    i_sync = 0
                    retry_count += 1
                    time.sleep(1.0)
                    continue
                
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
                    time.sleep(0.75)
                    continue
                    
                i_sync += 1
            time.sleep(attesa)

        elif tipo == 'click_anomaly':
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
            time.sleep(attesa)
            
        elif tipo == 'number_match':
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
                            time.sleep(attesa)
                            
        elif tipo == 'ocr_keypad':
            try:
                import easyocr
                import mss
                import numpy as np
                import re
            except ImportError:
                print("[OCR] Dipendenze mancanti (easyocr non installato).")
                continue
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
                            time.sleep(0.15)
                    except Exception as e:
                        print(f"[OCR] Errore lettura OCR: {e}")
            time.sleep(attesa)

        elif tipo == 'yolo_drag':
            import os
            try:
                from ultralytics import YOLO
                import numpy as np
                import mss
                _YOLO_OK = True
            except ImportError:
                _YOLO_OK = False

            model_name = az.get('yolo_model', '')
            model_path = os.path.join(os.getcwd(), model_name) if not os.path.isabs(model_name) else model_name
                
            ex = cx + int(az.get('end_rx', 0) * cw)
            ey = cy + int(az.get('end_ry', 0) * ch)
            roi_poly = az.get('roi_poly', [])
            start_t = time.time()
            found = False
            print(f"[yolo_drag] Cerco oggetto con YOLO: {model_path}")
            
            if _YOLO_OK and os.path.exists(model_path):
                model = YOLO(model_path)
                with mss.mss() as sct:
                    if len(roi_poly) >= 3:
                        xs = [p[0] for p in roi_poly]
                        ys = [p[1] for p in roi_poly]
                        m_left = cx + int(min(xs) * cw)
                        m_top = cy + int(min(ys) * ch)
                        m_width = int((max(xs) - min(xs)) * cw)
                        m_height = int((max(ys) - min(ys)) * ch)
                    else:
                        m_left, m_top, m_width, m_height = cx, cy, cw, ch
                        
                    monitor = {"top": m_top, "left": m_left, "width": m_width, "height": m_height}
                    
                    while time.time() - start_t < 3.0:
                        try:
                            sct_img = np.array(sct.grab(monitor))
                            img_bgr = sct_img[:, :, :3]
                            results = model(img_bgr, conf=0.7, verbose=False)
                            boxes = results[0].boxes
                            if len(boxes) > 0:
                                best_box = max(boxes, key=lambda b: float(b.conf[0]))
                                x1, y1, x2, y2 = best_box.xyxy[0].tolist()
                                sx = m_left + int((x1 + x2) / 2)
                                sy = m_top + int((y1 + y2) / 2)
                                
                                inside = True
                                if len(roi_poly) >= 3:
                                    rx_rel = (sx - cx) / cw
                                    ry_rel = (sy - cy) / ch
                                    inside = False
                                    n_v = len(roi_poly)
                                    j_v = n_v - 1
                                    for i_v in range(n_v):
                                        xi, yi = roi_poly[i_v]
                                        xj, yj = roi_poly[j_v]
                                        if ((yi > ry_rel) != (yj > ry_rel)) and \
                                           (rx_rel < (xj - xi) * (ry_rel - yi) / (yj - yi + 1e-12) + xi):
                                            inside = not inside
                                        j_v = i_v
                                
                                if inside:
                                    trascinamento_umano(sx, sy, ex, ey, durata)
                                    found = True
                                    break
                        except Exception:
                            pass
                        time.sleep(0.1)
            
            if not found:
                print(f"[yolo_drag] Oggetto non trovato (cercato in: {model_path})")
            time.sleep(attesa)

        elif tipo == 'yolo_drag_all':
            import os
            try:
                from ultralytics import YOLO
                import numpy as np
                import mss
                _YOLO_OK = True
            except ImportError:
                _YOLO_OK = False

            model_name = az.get('yolo_model', '')
            model_path = os.path.join(os.getcwd(), model_name) if not os.path.isabs(model_name) else model_name

            ex = cx + int(az.get('end_rx', 0) * cw)
            ey = cy + int(az.get('end_ry', 0) * ch)
            roi_poly = az.get('roi_poly', [])
            
            if _YOLO_OK and os.path.exists(model_path):
                model = YOLO(model_path)
                with mss.mss() as sct:
                    if len(roi_poly) >= 3:
                        xs = [p[0] for p in roi_poly]
                        ys = [p[1] for p in roi_poly]
                        m_left = cx + int(min(xs) * cw)
                        m_top = cy + int(min(ys) * ch)
                        m_width = int((max(xs) - min(xs)) * cw)
                        m_height = int((max(ys) - min(ys)) * ch)
                    else:
                        m_left, m_top, m_width, m_height = cx, cy, cw, ch

                    monitor = {"top": m_top, "left": m_left, "width": m_width, "height": m_height}
                    max_time = 20.0
                    start_t = time.time()
                    empty_frames = 0
                    
                    while time.time() - start_t < max_time:
                        try:
                            sct_img = np.array(sct.grab(monitor))
                            img_bgr = sct_img[:, :, :3]
                            results = model(img_bgr, conf=0.7, verbose=False)
                            boxes = results[0].boxes
                            
                            valid_boxes = []
                            for box in boxes:
                                x1, y1, x2, y2 = box.xyxy[0].tolist()
                                sx = m_left + int((x1 + x2) / 2)
                                sy = m_top + int((y1 + y2) / 2)
                                
                                inside = True
                                if len(roi_poly) >= 3:
                                    rx_rel = (sx - cx) / cw
                                    ry_rel = (sy - cy) / ch
                                    inside = False
                                    n_v = len(roi_poly)
                                    j_v = n_v - 1
                                    for i_v in range(n_v):
                                        xi, yi = roi_poly[i_v]
                                        xj, yj = roi_poly[j_v]
                                        if ((yi > ry_rel) != (yj > ry_rel)) and \
                                           (rx_rel < (xj - xi) * (ry_rel - yi) / (yj - yi + 1e-12) + xi):
                                            inside = not inside
                                        j_v = i_v
                                if inside and math.hypot(sx - ex, sy - ey) > 60:
                                    valid_boxes.append((sx, sy, float(box.conf[0])))
                                    
                            if not valid_boxes:
                                empty_frames += 1
                                if empty_frames >= 3:
                                    break 
                                time.sleep(0.1)
                                continue

                            empty_frames = 0
                            best_box = max(valid_boxes, key=lambda b: b[2])
                            sx, sy = best_box[0], best_box[1]
                            
                            trascinamento_umano(sx, sy, ex, ey, durata)
                            time.sleep(0.15) 
                            
                        except Exception as e:
                            print(f"[yolo_drag_all] Errore iterazione: {e}")
                            break
            else:
                print(f"[yolo_drag_all] YOLO o modello non trovato: {model_path}")
            
            _time.sleep(attesa)

        elif tipo == 'yolo_click':
            import os as _os
            try:
                from ultralytics import YOLO as _YOLO
                import mss as _mss
                import numpy as _np
                _YOLO_OK = True
            except ImportError:
                _YOLO_OK = False

            model_name = az.get('yolo_model', '')
            _base_dir = _os.getcwd()  # cwd del processo Python = radice progetto
            _model_path = _os.path.join(_base_dir, model_name) if not _os.path.isabs(model_name) else model_name
            if not _os.path.exists(_model_path):
                _model_path = model_name
                
            roi_poly = az.get('roi_poly', [])
            start_t = _time.time()
            found = False
            
            if _YOLO_OK and _os.path.exists(_model_path):
                model = _YOLO(_model_path)
                with _mss.mss() as sct:
                    if len(roi_poly) >= 3:
                        xs = [p[0] for p in roi_poly]
                        ys = [p[1] for p in roi_poly]
                        m_left = cx + int(min(xs) * cw)
                        m_top = cy + int(min(ys) * ch)
                        m_width = int((max(xs) - min(xs)) * cw)
                        m_height = int((max(ys) - min(ys)) * ch)
                    else:
                        m_left, m_top, m_width, m_height = cx, cy, cw, ch
                        
                    monitor = {"top": m_top, "left": m_left, "width": m_width, "height": m_height}
                    
                    while _time.time() - start_t < 3.0:
                        try:
                            sct_img = _np.array(sct.grab(monitor))
                            img_bgr = sct_img[:, :, :3]
                            results = model(img_bgr, conf=0.5, verbose=False)
                            boxes = results[0].boxes
                            if len(boxes) > 0:
                                best_box = max(boxes, key=lambda b: float(b.conf[0]))
                                x1, y1, x2, y2 = best_box.xyxy[0].tolist()
                                sx = m_left + int((x1 + x2) / 2)
                                sy = m_top + int((y1 + y2) / 2)
                                
                                inside = True
                                if len(roi_poly) >= 3:
                                    rx_rel = (sx - cx) / cw
                                    ry_rel = (sy - cy) / ch
                                    inside = False
                                    n_v = len(roi_poly)
                                    j_v = n_v - 1
                                    for i_v in range(n_v):
                                        xi, yi = roi_poly[i_v]
                                        xj, yj = roi_poly[j_v]
                                        if ((yi > ry_rel) != (yj > ry_rel)) and \
                                           (rx_rel < (xj - xi) * (ry_rel - yi) / (yj - yi + 1e-12) + xi):
                                            inside = not inside
                                        j_v = i_v
                                        
                                if inside:
                                    _click_hold(sx, sy, durata)
                                    found = True
                                    break
                        except Exception:
                            pass
                        _time.sleep(0.1)
            
            if not found:
                print(f"[yolo_click] Oggetto non trovato (modello: {_model_path})")
            _time.sleep(attesa)

        elif tipo == 'yolo_click_all':
            import os as _os
            try:
                from ultralytics import YOLO as _YOLO
                import mss as _mss
                import numpy as _np
                _YOLO_OK = True
            except ImportError:
                _YOLO_OK = False

            model_name = az.get('yolo_model', '')
            _base_dir = _os.getcwd()  # cwd del processo Python = radice progetto
            _model_path = _os.path.join(_base_dir, model_name) if not _os.path.isabs(model_name) else model_name
            if not _os.path.exists(_model_path):
                _model_path = model_name

            roi_poly = az.get('roi_poly', [])

            if _YOLO_OK and _os.path.exists(_model_path):
                model = _YOLO(_model_path)
                with _mss.mss() as sct:
                    if len(roi_poly) >= 3:
                        xs = [p[0] for p in roi_poly]
                        ys = [p[1] for p in roi_poly]
                        m_left = cx + int(min(xs) * cw)
                        m_top = cy + int(min(ys) * ch)
                        m_width = int((max(xs) - min(xs)) * cw)
                        m_height = int((max(ys) - min(ys)) * ch)
                    else:
                        m_left, m_top, m_width, m_height = cx, cy, cw, ch

                    monitor = {"top": m_top, "left": m_left, "width": m_width, "height": m_height}
                    max_time = 20.0
                    start_t = _time.time()
                    empty_frames = 0
                    
                    while _time.time() - start_t < max_time:
                        try:
                            sct_img = _np.array(sct.grab(monitor))
                            img_bgr = sct_img[:, :, :3]
                            results = model(img_bgr, conf=0.5, verbose=False)
                            boxes = results[0].boxes
                            
                            valid_boxes = []
                            for box in boxes:
                                x1, y1, x2, y2 = box.xyxy[0].tolist()
                                sx = m_left + int((x1 + x2) / 2)
                                sy = m_top + int((y1 + y2) / 2)
                                
                                inside = True
                                if len(roi_poly) >= 3:
                                    rx_rel = (sx - cx) / cw
                                    ry_rel = (sy - cy) / ch
                                    inside = False
                                    n_v = len(roi_poly)
                                    j_v = n_v - 1
                                    for i_v in range(n_v):
                                        xi, yi = roi_poly[i_v]
                                        xj, yj = roi_poly[j_v]
                                        if ((yi > ry_rel) != (yj > ry_rel)) and \
                                           (rx_rel < (xj - xi) * (ry_rel - yi) / (yj - yi + 1e-12) + xi):
                                            inside = not inside
                                        j_v = i_v
                                if inside:
                                    valid_boxes.append((sx, sy, float(box.conf[0])))
                                    
                            if not valid_boxes:
                                empty_frames += 1
                                if empty_frames >= 3:
                                    break 
                                _time.sleep(0.1)
                                continue

                            empty_frames = 0
                            
                            for box_info in valid_boxes:
                                sx, sy = box_info[0], box_info[1]
                                _click_hold(sx, sy, durata)
                                _time.sleep(0.05) 
                            
                            _time.sleep(0.15) 
                            
                        except Exception as e:
                            print(f"[yolo_click_all] Errore iterazione: {e}")
                            break
            else:
                print(f"[yolo_click_all] YOLO o modello non trovato: {_model_path}")
            
            time.sleep(attesa)
            
        elif tipo == 'click_until':
            for cx_rel, cy_rel, bx_rel, by_rel in az.get('punti', []):
                chk_x = cx + int(cx_rel * cw)
                chk_y = cy + int(cy_rel * ch)
                btn_x = cx + int(bx_rel * cw)
                btn_y = cy + int(by_rel * ch)
                
                pyautogui.moveTo(btn_x, btn_y, duration=0.1)
                
                start_t = time.time()
                while time.time() - start_t < 8.0:
                    try:
                        r, g, b = pyautogui.pixel(chk_x, chk_y)
                        if r > 200 and g > 200 and b > 200:
                            break
                        pyautogui.click()
                        pyautogui.mouseDown(button='left')
                        time.sleep(0.03)
                        pyautogui.mouseUp(button='left')
                    except Exception:
                        pass
                    time.sleep(0.05)
            time.sleep(attesa)

        else:
            print(f"[esegui_azioni] Tipo sconosciuto: {tipo}")

        time.sleep(attesa)

    if not is_test and current_step < len(cooldowns):
        print(f"__COOLDOWN__:{cooldowns[current_step]}")

    return True
