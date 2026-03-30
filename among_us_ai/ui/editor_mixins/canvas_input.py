"""
Input mouse/tastiera sul canvas: piazza punti, segue il mouse, hit-test, sposta vertici.

Mixin di TaskActionEditor.
"""

from ._imports import *


class EditorCanvasInputMixin:
    """Mixin con i metodi di editor canvas input di GPSVisualizerPro."""
    def _canvas_mouse_down(self, *_):
        """Callback del click sul canvas dell'editor."""
        pos = dpg.get_drawing_mouse_pos()
        rx = max(0.0, min(1.0, pos[0] / max(1, self.preview_w)))
        ry = max(0.0, min(1.0, pos[1] / max(1, self.preview_h)))

        if self.stato in ("WAIT_RECT_ON_CANVAS", self.WAIT_NUM_MATCH_RECT):
            self.rect_start = (rx, ry)
            self.rect_end   = (rx, ry)
            self.rect_drag_active = True
            # Avvia un thread separato
            threading.Thread(target=self._segui_mouse_rect, daemon=True).start()
            return

        inserimento_attivo = self.stato in (
            self.WAIT_CLICK, self.WAIT_DRAG_START, self.WAIT_DRAG_END,
            self.WAIT_MULTI, self.WAIT_POLY,
            self.WAIT_POLY_ZONE_A, self.WAIT_POLY_ZONE_B,
            self.WAIT_DRAG_HOLD_START, self.WAIT_DRAG_HOLD_END,
            self.WAIT_WIRING_L, self.WAIT_WIRING_R, self.WAIT_WIRING_C,
            self.WAIT_SYNC_CHECK, self.WAIT_SYNC_BTN,
            self.WAIT_YOLO_POLY, self.WAIT_YOLO_DEST,
            self.WAIT_YOLO_ALL_POLY, self.WAIT_YOLO_ALL_DEST,
            self.WAIT_CUC_CHK, self.WAIT_CUC_BTN,
            self.WAIT_YOLO_CLICK_POLY, self.WAIT_YOLO_CLICK_ALL_POLY,
            self.WAIT_YOLO_SEQ_POLY,
            self.WAIT_SIMON_DISPLAY, self.WAIT_SIMON_KEYPAD,
            self.WAIT_ANOMALY_CHK, self.WAIT_ANOMALY_BTN,
            self.WAIT_OCR_POLY, self.WAIT_OCR_KEYPAD
        )
        
        # Se c'e' un inserimento attivo, il click sulla preview registra il punto
        if inserimento_attivo:
            self._piazza_punto_rel(rx, ry)
            return

        # Altrimenti, gestiamo la selezione o il drag dei vertici
        v_idx, v_key = self._hit_test_vertex(rx, ry)
        if v_idx >= 0:
            self._dragging_vertex = True
            self._drag_vx_idx     = v_idx
            self._drag_vx_key     = v_key
            self.sel_idx          = v_idx
            self._aggiorna_pannello_selezione()
            # Avvia un thread separato
            threading.Thread(target=self._segui_mouse_vertex, daemon=True).start()
            return

        idx = self._hit_test(rx, ry)
        self.sel_idx = idx
        self._aggiorna_pannello_selezione()
        self.aggiorna_preview()
        self.aggiorna_lista()

    def _piazza_punto_rel(self, rx, ry):
        """Piazza un punto rel."""
        durata = dpg.get_value(self.TAG_IN_DUR)
        attesa = dpg.get_value(self.TAG_IN_PAUSE)

        if self.stato == self.WAIT_CLICK:
            self.azioni.append({
                "tipo": "click", "rx": rx, "ry": ry,
                "durata": durata, "attesa": attesa,
            })
            self._reset_stato()
            self._imposta_istruzioni("Click aggiunto.")

        elif self.stato == self.WAIT_DRAG_START:
            self.buffer_punti = [(rx, ry)]
            self.stato = self.WAIT_DRAG_END
            self._imposta_istruzioni("Ora CLICK sulla preview per ARRIVO drag.", (255, 100, 100))

        elif self.stato == self.WAIT_DRAG_END:
            sx, sy = self.buffer_punti[0]
            self.azioni.append({
                "tipo": "drag",
                "start_rx": sx, "start_ry": sy,
                "end_rx":   rx, "end_ry":   ry,
                "durata": durata, "attesa": attesa,
            })
            self._reset_stato()
            self._imposta_istruzioni("Drag aggiunto.")

        elif self.stato == self.WAIT_DRAG_HOLD_START:
            self.buffer_punti = [(rx, ry)]
            self.stato = self.WAIT_DRAG_HOLD_END
            self._imposta_istruzioni(
                "Ora CLICK sulla preview per ARRIVO (verra' tenuto premuto).",
                (255, 140, 180))

        elif self.stato == self.WAIT_DRAG_HOLD_END:
            sx, sy = self.buffer_punti[0]
            hold = max(0.0, float(dpg.get_value(self.TAG_IN_HOLD)))
            self.azioni.append({
                "tipo":     "drag_hold",
                "start_rx": sx,     "start_ry": sy,
                "end_rx":   rx,     "end_ry":   ry,
                "durata":   durata, "hold":     hold, "attesa": attesa,
            })
            self._reset_stato()
            self._imposta_istruzioni(f"Drag+Tieni aggiunto (hold={hold:.2f}s).")

        elif self.stato == self.WAIT_WIRING_L:
            self.buffer_w_l.append((rx, ry))
            if len(self.buffer_w_l) >= 4:
                self.stato = self.WAIT_WIRING_R
                self._imposta_istruzioni("Ora clicca sui 4 CONNETTORI A DESTRA (1/4)", (255, 160, 50))
            else:
                self._imposta_istruzioni(f"Cavo {len(self.buffer_w_l)+1}/4...", (200, 255, 100))

        elif self.stato == self.WAIT_WIRING_R:
            self.buffer_w_r.append((rx, ry))
            if len(self.buffer_w_r) >= 4:
                self.stato = self.WAIT_WIRING_C
                self._imposta_istruzioni("Ora clicca sulle 4 LUCI INDICATRICI (1/4)", (255, 255, 100))
            else:
                self._imposta_istruzioni(f"Connettore {len(self.buffer_w_r)+1}/4...", (255, 160, 50))

        elif self.stato == self.WAIT_WIRING_C:
            self.buffer_w_c.append((rx, ry))
            if len(self.buffer_w_c) >= 4:
                self.azioni.append({
                    "tipo": "wiring", "left": self.buffer_w_l,
                    "right": self.buffer_w_r, "lights": self.buffer_w_c,
                    "durata": durata, "attesa": attesa,
                })
                self._reset_stato()
                self._imposta_istruzioni("Fix Wiring registrato correttamente!", (100, 255, 100))
            else:
                self._imposta_istruzioni(f"Luce {len(self.buffer_w_c)+1}/4...", (255, 255, 100))

        elif self.stato == self.WAIT_SYNC_CHECK:
            self.buffer_punti = [(rx, ry)]
            self.stato = self.WAIT_SYNC_BTN
            self._imposta_istruzioni("Ora clicca il BOTTONE DA PREMERE associato.", (255, 100, 100))

        elif self.stato == self.WAIT_SYNC_BTN:
            cx_rel, cy_rel = self.buffer_punti[0]
            self.buffer_sync.append((cx_rel, cy_rel, rx, ry))
            self.stato = self.WAIT_SYNC_CHECK
            self._imposta_istruzioni(f"Coppia {len(self.buffer_sync)} aggiunta. Clicca nuovo PUNTO CHECK o 'CHIUDI PUNTI'.", (255, 255, 100))

        elif self.stato == self.WAIT_YOLO_DEST:
            self.azioni.append({
                "tipo": "yolo_drag",
                "yolo_model": getattr(self, '_tmp_yolo_model', 'best.pt'),
                "roi_poly": [list(p) for p in self.buffer_zone_a],
                "end_rx": rx, "end_ry": ry,
                "durata": durata, "attesa": attesa
            })
            self._reset_stato()
            self._imposta_istruzioni(f"Drag YOLO aggiunto.", (100, 255, 100))

        elif self.stato == self.WAIT_YOLO_ALL_DEST:
            self.azioni.append({
                "tipo": "yolo_drag_all",
                "yolo_model": getattr(self, '_tmp_yolo_model', 'best.pt'),
                "roi_poly": [list(p) for p in self.buffer_zone_a],
                "end_rx": rx, "end_ry": ry,
                "durata": durata, "attesa": attesa
            })
            self._reset_stato()
            self._imposta_istruzioni(f"Drag ALL YOLO aggiunto.", (100, 255, 100))

        elif self.stato == self.WAIT_CUC_CHK:
            self.buffer_punti = [(rx, ry)]
            self.stato = self.WAIT_CUC_BTN
            self._imposta_istruzioni("Ora clicca il BOTTONE DA PREMERE associato.", (100, 255, 255))

        elif self.stato == self.WAIT_CUC_BTN:
            cx_rel, cy_rel = self.buffer_punti[0]
            self.buffer_cuc.append((cx_rel, cy_rel, rx, ry))
            self.stato = self.WAIT_CUC_CHK
            self._imposta_istruzioni(f"Coppia {len(self.buffer_cuc)} aggiunta. Clicca nuovo PUNTO CHECK o 'CHIUDI PUNTI'.", (255, 255, 255))

        elif self.stato == self.WAIT_SIMON_DISPLAY:
            self.buffer_simon_d.append((rx, ry))
            self._imposta_istruzioni(f"Luce display {len(self.buffer_simon_d)} mappata.", (100, 200, 255))
            
        elif self.stato == self.WAIT_SIMON_KEYPAD:
            self.buffer_simon_k.append((rx, ry))
            self._imposta_istruzioni(f"Bottone tastierino {len(self.buffer_simon_k)} mappato.", (255, 100, 255))

        elif self.stato == self.WAIT_ANOMALY_CHK:
            self.buffer_punti = [(rx, ry)]
            self.stato = self.WAIT_ANOMALY_BTN
            self._imposta_istruzioni("Ora clicca il BOTTONE DA PREMERE associato all'anomalia.", (255, 50, 100))

        elif self.stato == self.WAIT_ANOMALY_BTN:
            cx_rel, cy_rel = self.buffer_punti[0]
            self.buffer_anomaly.append((cx_rel, cy_rel, rx, ry))
            self.stato = self.WAIT_ANOMALY_CHK
            self._imposta_istruzioni(f"Coppia {len(self.buffer_anomaly)} aggiunta. Clicca nuovo CHECK o 'CHIUDI PUNTI'.", (255, 100, 200))
            
        elif self.stato == self.WAIT_OCR_KEYPAD:
            self.buffer_keypad.append((rx, ry))
            if len(self.buffer_keypad) == 10:
                self.azioni.append({
                    "tipo": "ocr_keypad",
                    "roi_poly": [list(p) for p in self.buffer_zone_a],
                    "keypad": [list(p) for p in self.buffer_keypad],
                    "durata": durata, "attesa": attesa
                })
                self._reset_stato()
                self._imposta_istruzioni("OCR Keypad salvato!", (100, 255, 100))
            else:
                self._imposta_istruzioni(f"Tasto {len(self.buffer_keypad)}/10 mappato.", (255, 100, 255))

        elif self.stato in (self.WAIT_MULTI, self.WAIT_POLY,
                            self.WAIT_POLY_ZONE_A, self.WAIT_POLY_ZONE_B,
                            self.WAIT_YOLO_POLY,
                            self.WAIT_YOLO_ALL_POLY,
                            self.WAIT_YOLO_CLICK_POLY,
                            self.WAIT_YOLO_CLICK_ALL_POLY,
                          self.WAIT_YOLO_SEQ_POLY,
                          self.WAIT_OCR_POLY):
            self.buffer_punti.append((rx, ry))
            self._imposta_istruzioni(
                f"Punto {len(self.buffer_punti)} aggiunto.", (200, 200, 200))

        self.aggiorna_lista()
        self.aggiorna_preview()

    def _segui_mouse_vertex(self):
        """Segue il mouse vertex."""
        # Senza ambiente Windows non possiamo procedere
        if not _WIN_OK:
            self._dragging_vertex = False
            return
        # Pausa il thread per il tempo specificato (secondi)
        time.sleep(0.02)
        while self._dragging_vertex:
            lmb = (win32api.GetAsyncKeyState(win32con.VK_LBUTTON) & 0x8000) != 0
            if not lmb:
                break
            try:
                pos = dpg.get_drawing_mouse_pos()
                rx = max(0.0, min(1.0, pos[0] / max(1, self.preview_w)))
                ry = max(0.0, min(1.0, pos[1] / max(1, self.preview_h)))
                self._muovi_vertice(self._drag_vx_idx, self._drag_vx_key, rx, ry)
                self.aggiorna_preview()
            except Exception:
                pass
            # Pausa il thread per il tempo specificato (secondi)
            time.sleep(0.015)

        self._dragging_vertex = False
        self._drag_vx_idx     = -1
        self._drag_vx_key     = None
        try:
            self.aggiorna_lista()
            self.aggiorna_preview()
            self._imposta_istruzioni("Vertice spostato.")
        except Exception:
            pass

    def _segui_mouse_rect(self):
        """Segue il mouse rect."""
        # Senza ambiente Windows non possiamo procedere
        if not _WIN_OK:
            return
        # Pausa il thread per il tempo specificato (secondi)
        time.sleep(0.02)
        while self.rect_drag_active:
            lmb = (win32api.GetAsyncKeyState(win32con.VK_LBUTTON) & 0x8000) != 0
            if not lmb:
                break
            try:
                pos = dpg.get_drawing_mouse_pos()
                rx = max(0.0, min(1.0, pos[0] / max(1, self.preview_w)))
                ry = max(0.0, min(1.0, pos[1] / max(1, self.preview_h)))
                self.rect_end = (rx, ry)
            except Exception:
                pass
            # Pausa il thread per il tempo specificato (secondi)
            time.sleep(0.015)

        if self.rect_start and self.rect_end:
            x1, y1 = self.rect_start
            x2, y2 = self.rect_end
            if abs(x2 - x1) > 0.005 and abs(y2 - y1) > 0.005:
                if self.stato == "WAIT_RECT_ON_CANVAS":
                    durata = dpg.get_value(self.TAG_IN_DUR)
                    attesa = dpg.get_value(self.TAG_IN_PAUSE)
                    self.azioni.append({
                        "tipo":   "click_rect",
                        "rect":   [x1, y1, x2, y2],
                        "durata": durata,
                        "attesa": attesa,
                    })
                    self._imposta_istruzioni("Click-rect aggiunto.")
                elif self.stato == self.WAIT_NUM_MATCH_RECT:
                    # Cerca la finestra del gioco per nome
                    hwnd = win32gui.FindWindow(None, dpg.get_value(self.TAG_IN_WIN_NAME))
                    # Ottiene il rect (x, y, w, h) dell'area client del gioco
                    rect = get_client_rect(hwnd)
                    if rect:
                        cx, cy, cw, ch = rect
                        px1, py1 = int(min(x1, x2)*cw), int(min(y1, y2)*ch)
                        px2, py2 = int(max(x1, x2)*cw), int(max(y1, y2)*ch)
                        ax1, ay1 = cx + px1, cy + py1
                        ax2, ay2 = cx + px2, cy + py2
                        try:
                            import mss
                            import cv2
                            import numpy as np
                            # Cattura uno screenshot della regione del gioco
                            with mss.mss() as sct:
                                img = np.array(sct.grab({"left": ax1, "top": ay1, "width": ax2-ax1, "height": ay2-ay1}))
                                shape_blurred = _extract_pure_shape(img)
                                self.buffer_num_match.append({
                                    "rect": [x1, y1, x2, y2],
                                    "template": shape_blurred.flatten().tolist()
                                })
                                self._imposta_istruzioni(f"Numero {len(self.buffer_num_match)} salvato. Trascina prossimo o CHIUDI PUNTI.", (100, 255, 255))
                        except Exception as e:
                            print("[NumberMatch] Errore salvataggio template:", e)
            else:
                if self.stato == "WAIT_RECT_ON_CANVAS":
                    self._imposta_istruzioni("Rettangolo troppo piccolo, annullato.", (255, 150, 100))
        self.rect_drag_active = False
        if self.stato == "WAIT_RECT_ON_CANVAS":
            self._reset_stato()
        else:
            self.rect_start = None
            self.rect_end = None
        try:
            self.aggiorna_lista()
            self.aggiorna_preview()
        except Exception:
            pass

    def _hit_test(self, rx, ry, tol_click=0.015, tol_line=0.012):
        """Test di collisione con."""
        for i in range(len(self.azioni) - 1, -1, -1):
            a = self.azioni[i]
            t = a.get("tipo")
            if t == "click":
                if math.hypot(rx - a["rx"], ry - a["ry"]) <= tol_click:
                    return i
            elif t == "click_rect":
                r = a["rect"]
                if min(r[0], r[2]) <= rx <= max(r[0], r[2]) and \
                   min(r[1], r[3]) <= ry <= max(r[1], r[3]):
                    return i
            elif t == "click_poly":
                # Test point-in-polygon (Ray casting)
                if point_in_polygon(rx, ry, a["poly"]):
                    return i
            elif t in ("drag", "drag_hold"):
                if math.hypot(rx - a["start_rx"], ry - a["start_ry"]) <= tol_click:
                    return i
                if math.hypot(rx - a["end_rx"], ry - a["end_ry"]) <= tol_click:
                    return i
                if self._point_near_segment(rx, ry,
                        a["start_rx"], a["start_ry"],
                        a["end_rx"],   a["end_ry"], tol_line):
                    return i
            elif t == "drag_multi":
                pts = a.get("punti", [])
                for p in pts:
                    if math.hypot(rx - p[0], ry - p[1]) <= tol_click:
                        return i
                for k in range(len(pts) - 1):
                    if self._point_near_segment(rx, ry,
                            pts[k][0], pts[k][1],
                            pts[k+1][0], pts[k+1][1], tol_line):
                        return i
            elif t == "drag_zone":
                # Test point-in-polygon (Ray casting)
                if point_in_polygon(rx, ry, a.get("zone_a", [])):
                    return i
                # Test point-in-polygon (Ray casting)
                if point_in_polygon(rx, ry, a.get("zone_b", [])):
                    return i
            elif t == "wiring":
                for grp in ["left", "right", "lights"]:
                    for p in a.get(grp, []):
                        if math.hypot(rx - p[0], ry - p[1]) <= tol_click:
                            return i
            elif t == "sync_click":
                for cx, cy, bx, by in a.get("punti", []):
                    if math.hypot(rx - cx, ry - cy) <= tol_click: return i
                    if math.hypot(rx - bx, ry - by) <= tol_click: return i
            elif t in ("yolo_drag", "yolo_drag_all"):
                if math.hypot(rx - a["end_rx"], ry - a["end_ry"]) <= tol_click:
                    return i
                # Test point-in-polygon (Ray casting)
                if point_in_polygon(rx, ry, a.get("roi_poly", [])):
                    return i
            elif t in ("yolo_click", "yolo_click_all", "yolo_drag_seq"):
                # Test point-in-polygon (Ray casting)
                if point_in_polygon(rx, ry, a.get("roi_poly", [])):
                    return i
            elif t == "click_until":
                for cx, cy, bx, by in a.get("punti", []):
                    if math.hypot(rx - cx, ry - cy) <= tol_click: return i
                    if math.hypot(rx - bx, ry - by) <= tol_click: return i
            elif t == "simon_says":
                for cx, cy in a.get("display", []):
                    if math.hypot(rx - cx, ry - cy) <= tol_click: return i
                for bx, by in a.get("keypad", []):
                    if math.hypot(rx - bx, ry - by) <= tol_click: return i
            elif t == "click_anomaly":
                for p_list in a.get("punti", []):
                    if len(p_list) == 4:
                        cx, cy, bx, by = p_list
                        if math.hypot(rx - cx, ry - cy) <= tol_click: return i
                        if math.hypot(rx - bx, ry - by) <= tol_click: return i
                    elif len(p_list) == 2:
                        cx, cy = p_list
                        if math.hypot(rx - cx, ry - cy) <= tol_click: return i
            elif t == "number_match":
                for btn in a.get("buttons", []):
                    r = btn["rect"]
                    if min(r[0], r[2]) <= rx <= max(r[0], r[2]) and min(r[1], r[3]) <= ry <= max(r[1], r[3]):
                        return i
            elif t == "ocr_keypad":
                # Test point-in-polygon (Ray casting)
                if point_in_polygon(rx, ry, a.get("roi_poly", [])): return i
                for px, py in a.get("keypad", []):
                    if math.hypot(rx - px, ry - py) <= tol_click: return i

        return -1

    def _point_near_segment(px, py, ax, ay, bx, by, tol):
        """Verifica se il punto e' vicino al segment."""
        dx, dy = bx - ax, by - ay
        lung2 = dx * dx + dy * dy
        if lung2 < 1e-12:
            return math.hypot(px - ax, py - ay) <= tol
        t = ((px - ax) * dx + (py - ay) * dy) / lung2
        t = max(0.0, min(1.0, t))
        proj_x = ax + t * dx
        proj_y = ay + t * dy
        return math.hypot(px - proj_x, py - proj_y) <= tol

    def _hit_test_vertex(self, rx, ry, tol=0.018):
        """Test di collisione con vertex."""
        best = (-1, None, float('inf'))
        for i in range(len(self.azioni) - 1, -1, -1):
            a = self.azioni[i]
            t = a.get("tipo")

            def check(px, py, key):
                """Verifica una condizione."""
                nonlocal best
                d = math.hypot(rx - px, ry - py)
                if d <= tol and d < best[2]:
                    best = (i, key, d)

            if t == "click":
                check(a["rx"], a["ry"], 'c')
            elif t == "click_rect":
                r = a["rect"]
                check(r[0], r[1], 'r1')
                check(r[2], r[3], 'r2')
            elif t == "click_poly":
                for k, (vx, vy) in enumerate(a.get("poly", [])):
                    check(vx, vy, f'p{k}')
            elif t in ("drag", "drag_hold"):
                check(a["start_rx"], a["start_ry"], 's')
                check(a["end_rx"],   a["end_ry"],   'e')
            elif t == "drag_multi":
                for k, (vx, vy) in enumerate(a.get("punti", [])):
                    check(vx, vy, f'm{k}')
            elif t == "drag_zone":
                for k, (vx, vy) in enumerate(a.get("zone_a", [])):
                    check(vx, vy, f'a{k}')
                for k, (vx, vy) in enumerate(a.get("zone_b", [])):
                    check(vx, vy, f'b{k}')
            elif t == "wiring":
                for k, (vx, vy) in enumerate(a.get("left", [])):
                    check(vx, vy, f'wl{k}')
                for k, (vx, vy) in enumerate(a.get("right", [])):
                    check(vx, vy, f'wr{k}')
                for k, (vx, vy) in enumerate(a.get("lights", [])):
                    check(vx, vy, f'wc{k}')
            elif t == "sync_click":
                for k, (cx, cy, bx, by) in enumerate(a.get("punti", [])):
                    check(cx, cy, f'sc{k}')
                    check(bx, by, f'sb{k}')
            elif t in ("yolo_drag", "yolo_drag_all"):
                check(a["end_rx"], a["end_ry"], 'e')
                for k, (vx, vy) in enumerate(a.get("roi_poly", [])):
                    check(vx, vy, f'yr{k}')
            elif t in ("yolo_click", "yolo_click_all", "yolo_drag_seq"):
                for k, (vx, vy) in enumerate(a.get("roi_poly", [])):
                    check(vx, vy, f'yr{k}')
            elif t == "click_until":
                for k, (cx, cy, bx, by) in enumerate(a.get("punti", [])):
                    check(cx, cy, f'uc{k}')
                    check(bx, by, f'ub{k}')
            elif t == "simon_says":
                for k, (cx, cy) in enumerate(a.get("display", [])):
                    check(cx, cy, f'sd{k}')
                for k, (bx, by) in enumerate(a.get("keypad", [])):
                    check(bx, by, f'sk{k}')
            elif t == "click_anomaly":
                for k, p_list in enumerate(a.get("punti", [])):
                    if len(p_list) == 4:
                        cx, cy, bx, by = p_list
                        check(cx, cy, f'ac{k}')
                        check(bx, by, f'ab{k}')
                    elif len(p_list) == 2:
                        cx, cy = p_list
                        check(cx, cy, f'ac{k}')
            elif t == "number_match":
                for k, btn in enumerate(a.get("buttons", [])):
                    r = btn["rect"]
                    check(r[0], r[1], f'nm{k}_1')
                    check(r[2], r[3], f'nm{k}_2')
            elif t == "ocr_keypad":
                for k, (vx, vy) in enumerate(a.get("roi_poly", [])):
                    check(vx, vy, f'okp{k}')
                for k, (vx, vy) in enumerate(a.get("keypad", [])):
                    check(vx, vy, f'okk{k}')

        return best[0], best[1]

    def _muovi_vertice(self, idx, key, rx, ry):
        """Muove vertice."""
        if idx < 0 or idx >= len(self.azioni):
            return
        a = self.azioni[idx]
        t = a.get("tipo")
        if t == "click" and key == 'c':
            a["rx"] = rx; a["ry"] = ry
        elif t == "click_rect":
            r = a["rect"]
            if key == 'r1':
                r[0] = rx; r[1] = ry
            elif key == 'r2':
                r[2] = rx; r[3] = ry
        elif t == "click_poly" and key and key.startswith('p'):
            try:
                k = int(key[1:])
                a["poly"][k] = [rx, ry]
            except (ValueError, IndexError):
                pass
        elif t in ("drag", "drag_hold"):
            if key == 's':
                a["start_rx"] = rx; a["start_ry"] = ry
            elif key == 'e':
                a["end_rx"]   = rx; a["end_ry"]   = ry
        elif t == "drag_multi" and key and key.startswith('m'):
            try:
                k = int(key[1:])
                a["punti"][k] = [rx, ry]
            except (ValueError, IndexError):
                pass
        elif t == "drag_zone" and key:
            try:
                if key.startswith('a'):
                    k = int(key[1:])
                    a["zone_a"][k] = [rx, ry]
                elif key.startswith('b'):
                    k = int(key[1:])
                    a["zone_b"][k] = [rx, ry]
            except (ValueError, IndexError):
                pass
        elif t == "wiring" and key:
            try:
                if key.startswith('wl'):
                    k = int(key[2:])
                    a["left"][k] = [rx, ry]
                elif key.startswith('wr'):
                    k = int(key[2:])
                    a["right"][k] = [rx, ry]
                elif key.startswith('wc'):
                    k = int(key[2:])
                    a["lights"][k] = [rx, ry]
            except (ValueError, IndexError):
                pass
        elif t == "sync_click" and key:
            try:
                if key.startswith('sc'):
                    k = int(key[2:])
                    a["punti"][k] = [rx, ry, a["punti"][k][2], a["punti"][k][3]]
                elif key.startswith('sb'):
                    k = int(key[2:])
                    a["punti"][k] = [a["punti"][k][0], a["punti"][k][1], rx, ry]
            except (ValueError, IndexError):
                pass
        elif t in ("yolo_drag", "yolo_drag_all", "yolo_click", "yolo_click_all", "yolo_drag_seq"):
            if key == 'e' and t in ("yolo_drag", "yolo_drag_all"):
                a["end_rx"] = rx; a["end_ry"] = ry
            elif key and key.startswith('yr'):
                try:
                    k = int(key[2:])
                    a["roi_poly"][k] = [rx, ry]
                except (ValueError, IndexError):
                    pass
        elif t == "click_until" and key:
            try:
                if key.startswith('uc'):
                    k = int(key[2:])
                    a["punti"][k] = [rx, ry, a["punti"][k][2], a["punti"][k][3]]
                elif key.startswith('ub'):
                    k = int(key[2:])
                    a["punti"][k] = [a["punti"][k][0], a["punti"][k][1], rx, ry]
            except (ValueError, IndexError):
                pass
        elif t == "simon_says" and key:
            try:
                if key.startswith('sd'):
                    k = int(key[2:])
                    a["display"][k] = [rx, ry]
                elif key.startswith('sk'):
                    k = int(key[2:])
                    a["keypad"][k] = [rx, ry]
            except (ValueError, IndexError):
                pass
        elif t == "click_anomaly" and key:
            try:
                if key.startswith('ac'):
                    k = int(key[2:])
                    a["punti"][k] = [rx, ry, a["punti"][k][2], a["punti"][k][3]]
                elif key.startswith('ab'):
                    k = int(key[2:])
                    a["punti"][k] = [a["punti"][k][0], a["punti"][k][1], rx, ry]
            except (ValueError, IndexError):
                pass
        elif t == "number_match" and key and key.startswith('nm'):
            try:
                parts = key[2:].split('_')
                k = int(parts[0])
                corner = int(parts[1])
                r = a["buttons"][k]["rect"]
                if corner == 1:
                    r[0] = rx; r[1] = ry
                else:
                    r[2] = rx; r[3] = ry
            except Exception:
                pass
        elif t == "ocr_keypad" and key:
            try:
                if key.startswith('okp'):
                    k = int(key[3:])
                    a["roi_poly"][k] = [rx, ry]
                elif key.startswith('okk'):
                    k = int(key[3:])
                    a["keypad"][k] = [rx, ry]
            except Exception:
                pass

    # Callback per l'evento
    def _on_key_delete(self, *_):
        """Callback per l'evento key delete."""
        if not self.e_aperto():
            return
        if self.sel_idx < 0:
            return
        self._elimina_selezione()
