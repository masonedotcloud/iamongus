"""
Disegno DPG: preview screenshot, azioni, handle, buffer corrente.

Mixin di TaskActionEditor.
"""

from ._imports import *


class EditorDrawingMixin:
    """Mixin con i metodi di editor drawing di GPSVisualizerPro."""
    def aggiorna_preview(self):
        """Aggiorna la preview screenshot nell'editor."""
        # Verifica se l'elemento DPG e' gia' stato creato
        if not dpg.does_item_exist(self.TAG_CANVAS):
            return
        # Rimuove l'elemento DPG (cleanup)
        dpg.delete_item(self.TAG_CANVAS, children_only=True)

        # Verifica se l'elemento DPG e' gia' stato creato
        if self.texture_width > 0 and dpg.does_item_exist(self.TAG_BG_TEX):
            dpg.draw_image(self.TAG_BG_TEX, (0, 0),
                           (self.preview_w, self.preview_h),
                           parent=self.TAG_CANVAS)
        else:
            dpg.draw_rectangle((0, 0), (self.preview_w, self.preview_h),
                               color=(100, 100, 100, 255),
                               fill=(40, 40, 40, 255),
                               parent=self.TAG_CANVAS)

        for i, a in enumerate(self.azioni):
            self._disegna_azione(i, a, selezionato=(i == self.sel_idx))

        self._disegna_buffer_corrente()

        if self.frozen:
            dpg.draw_rectangle((8, 8), (135, 34),
                               color=(0, 0, 0, 200),
                               fill=(0, 0, 0, 180),
                               parent=self.TAG_CANVAS)
            dpg.draw_text((14, 12), "FROZEN [F]",
                          color=(100, 220, 255, 255), size=18,
                          parent=self.TAG_CANVAS)

    def _px(self, rx, ry):
        """Converte coordinate gioco in pixel del canvas."""
        return rx * self.preview_w, ry * self.preview_h

    def _disegna_azione(self, idx, a, selezionato=False):
        """Disegna su DPG azione."""
        num = str(idx + 1)
        t = a.get("tipo")
        p = self.TAG_CANVAS
        SEL_COL = (255, 255, 0, 255)
        SEL_TH  = 3 

        if t == "click":
            x, y = self._px(a["rx"], a["ry"])
            dpg.draw_circle((x, y), 8, color=(0, 255, 0), fill=(0, 200, 0), parent=p)
            dpg.draw_text((x + 12, y - 12), num, color=(255, 255, 255), size=18, parent=p)
            if selezionato:
                dpg.draw_circle((x, y), 14, color=SEL_COL, thickness=SEL_TH, parent=p)

        elif t == "click_rect":
            r = a["rect"]
            x1, y1 = self._px(r[0], r[1])
            x2, y2 = self._px(r[2], r[3])
            dpg.draw_rectangle((x1, y1), (x2, y2),
                               color=(180, 255, 180, 255),
                               fill=(180, 255, 180, 40), parent=p)
            dpg.draw_text((x1 + 4, y1 + 4), num, color=(180, 255, 180), size=18, parent=p)
            if selezionato:
                dpg.draw_rectangle((x1 - 3, y1 - 3), (x2 + 3, y2 + 3),
                                   color=SEL_COL, thickness=SEL_TH, parent=p)

        elif t == "click_poly":
            pts = [self._px(px, py) for px, py in a["poly"]]
            if len(pts) >= 3:
                dpg.draw_polygon(pts, color=(200, 180, 255, 255),
                                 fill=(200, 180, 255, 40), parent=p)
                dpg.draw_text(pts[0], num, color=(200, 180, 255), size=18, parent=p)
                if selezionato:
                    dpg.draw_polygon(pts, color=SEL_COL,
                                     thickness=SEL_TH, parent=p)

        elif t == "drag":
            sx, sy = self._px(a["start_rx"], a["start_ry"])
            ex, ey = self._px(a["end_rx"],   a["end_ry"])
            dpg.draw_circle((sx, sy), 6, color=(255, 200, 0), fill=(255, 200, 0), parent=p)
            dpg.draw_arrow((ex, ey), (sx, sy), color=(255, 50, 50),
                           thickness=3, size=18, parent=p)
            dpg.draw_text((sx + 12, sy - 12), num, color=(255, 255, 255), size=18, parent=p)
            if selezionato:
                dpg.draw_circle((sx, sy), 12, color=SEL_COL, thickness=SEL_TH, parent=p)
                dpg.draw_circle((ex, ey), 12, color=SEL_COL, thickness=SEL_TH, parent=p)

        elif t == "drag_multi":
            pts = [self._px(px, py) for px, py in a["punti"]]
            for i in range(len(pts) - 1):
                dpg.draw_arrow(pts[i+1], pts[i], color=(255, 120, 50),
                               thickness=2, size=14, parent=p)
            if pts:
                dpg.draw_circle(pts[0], 6, color=(255, 200, 0),
                                fill=(255, 200, 0), parent=p)
                dpg.draw_text((pts[0][0] + 12, pts[0][1] - 12), num,
                              color=(255, 255, 255), size=18, parent=p)
                if selezionato:
                    for pt in pts:
                        dpg.draw_circle(pt, 11, color=SEL_COL,
                                        thickness=SEL_TH, parent=p)

        elif t == "drag_hold":
            sx, sy = self._px(a["start_rx"], a["start_ry"])
            ex, ey = self._px(a["end_rx"],   a["end_ry"])
            hold   = a.get("hold", 0)
            dpg.draw_circle((sx, sy), 6, color=(255, 140, 180),
                            fill=(255, 140, 180), parent=p)
            dpg.draw_arrow((ex, ey), (sx, sy), color=(255, 80, 160),
                           thickness=3, size=18, parent=p)
            hold_r = min(30, max(10, int(hold * 8 + 10)))
            dpg.draw_circle((ex, ey), hold_r,
                            color=(255, 80, 160, 140), fill=(255, 80, 160, 60), parent=p)
            dpg.draw_text((ex + hold_r + 4, ey - 8),
                          f"H:{hold:.1f}s", color=(255, 140, 180), size=16, parent=p)
            dpg.draw_text((sx + 12, sy - 12), num,
                          color=(255, 255, 255), size=18, parent=p)
            if selezionato:
                dpg.draw_circle((sx, sy), 12,
                                color=SEL_COL, thickness=SEL_TH, parent=p)
                dpg.draw_circle((ex, ey), hold_r + 4,
                                color=SEL_COL, thickness=SEL_TH, parent=p)

        elif t == "drag_zone":
            poly_a = [self._px(px, py) for px, py in a["zone_a"]]
            poly_b = [self._px(px, py) for px, py in a["zone_b"]]
            if len(poly_a) >= 3:
                dpg.draw_polygon(poly_a, color=(255, 200, 0, 255),
                                 fill=(255, 200, 0, 40), parent=p)
            if len(poly_b) >= 3:
                dpg.draw_polygon(poly_b, color=(255, 50, 50, 255),
                                 fill=(255, 50, 50, 40), parent=p)
            if poly_a and poly_b:
                ca_x = sum(pt[0] for pt in poly_a) / len(poly_a)
                ca_y = sum(pt[1] for pt in poly_a) / len(poly_a)
                cb_x = sum(pt[0] for pt in poly_b) / len(poly_b)
                cb_y = sum(pt[1] for pt in poly_b) / len(poly_b)
                dpg.draw_arrow((cb_x, cb_y), (ca_x, ca_y),
                               color=(255, 255, 255), thickness=2, size=14, parent=p)
                dpg.draw_text((ca_x + 12, ca_y - 12), num,
                              color=(255, 255, 255), size=18, parent=p)
            if selezionato:
                if len(poly_a) >= 3:
                    dpg.draw_polygon(poly_a, color=SEL_COL,
                                     thickness=SEL_TH, parent=p)
                if len(poly_b) >= 3:
                    dpg.draw_polygon(poly_b, color=SEL_COL,
                                     thickness=SEL_TH, parent=p)
                                     
        elif t == "wiring":
            for cx, cy in a.get("left", []):
                pt = self._px(cx, cy)
                dpg.draw_circle(pt, 5, color=(200, 255, 100), fill=(200, 255, 100), parent=p)
            for cx, cy in a.get("right", []):
                pt = self._px(cx, cy)
                dpg.draw_circle(pt, 5, color=(255, 160, 50), fill=(255, 160, 50), parent=p)
            for cx, cy in a.get("lights", []):
                pt = self._px(cx, cy)
                dpg.draw_circle(pt, 6, color=(255, 255, 100), fill=(255, 255, 100), parent=p)
                dpg.draw_circle(pt, 10, color=(255, 255, 100), thickness=1, parent=p)
                
        elif t == "sync_click":
            for i, (cx, cy, bx, by) in enumerate(a.get("punti", [])):
                pc = self._px(cx, cy)
                pb = self._px(bx, by)
                dpg.draw_circle(pc, 5, color=(255, 255, 100), fill=(255, 255, 100), parent=p)
                dpg.draw_circle(pb, 5, color=(255, 100, 100), fill=(255, 100, 100), parent=p)
                dpg.draw_arrow(pb, pc, color=(255, 200, 150), thickness=2, size=10, parent=p)
                if selezionato:
                    dpg.draw_circle(pc, 10, color=SEL_COL, thickness=SEL_TH, parent=p)
                    dpg.draw_circle(pb, 10, color=SEL_COL, thickness=SEL_TH, parent=p)
                    
        elif t == "yolo_drag":
            ex, ey = self._px(a["end_rx"], a["end_ry"])
            dpg.draw_circle((ex, ey), 8, color=(255, 100, 100), fill=(255, 100, 100, 100), parent=p)
            dpg.draw_text((ex + 12, ey - 12), f"{num} (YOLO: {a.get('yolo_model')})", color=(255, 100, 100), size=16, parent=p)
            
            roi_poly = a.get("roi_poly", [])
            if len(roi_poly) >= 3:
                za = [self._px(px, py) for px, py in roi_poly]
                dpg.draw_polygon(za, color=(255, 100, 255, 150), fill=(255, 100, 255, 40), parent=p)
                cx = sum(pt[0] for pt in roi_poly) / len(roi_poly)
                cy = sum(pt[1] for pt in roi_poly) / len(roi_poly)
                c_px, c_py = self._px(cx, cy)
                dpg.draw_arrow((ex, ey), (c_px, c_py), color=(255, 150, 255, 150), thickness=2, size=10, parent=p)

            if selezionato:
                dpg.draw_circle((ex, ey), 14, color=SEL_COL, thickness=SEL_TH, parent=p)
                if len(roi_poly) >= 3:
                    dpg.draw_polygon(za, color=SEL_COL, thickness=SEL_TH, parent=p)
                    
        elif t == "yolo_drag_all":
            ex, ey = self._px(a["end_rx"], a["end_ry"])
            dpg.draw_circle((ex, ey), 8, color=(255, 150, 50), fill=(255, 150, 50, 100), parent=p)
            dpg.draw_text((ex + 12, ey - 12), f"{num} (ALL YOLO: {a.get('yolo_model')})", color=(255, 150, 50), size=16, parent=p)
            
            roi_poly = a.get("roi_poly", [])
            if len(roi_poly) >= 3:
                za = [self._px(px, py) for px, py in roi_poly]
                dpg.draw_polygon(za, color=(255, 150, 50, 150), fill=(255, 150, 50, 40), parent=p)
                cx = sum(pt[0] for pt in roi_poly) / len(roi_poly)
                cy = sum(pt[1] for pt in roi_poly) / len(roi_poly)
                c_px, c_py = self._px(cx, cy)
                dpg.draw_arrow((ex, ey), (c_px, c_py), color=(255, 180, 100, 150), thickness=2, size=10, parent=p)

            if selezionato:
                dpg.draw_circle((ex, ey), 14, color=SEL_COL, thickness=SEL_TH, parent=p)
                if len(roi_poly) >= 3:
                    dpg.draw_polygon(za, color=SEL_COL, thickness=SEL_TH, parent=p)

        elif t == "yolo_click":
            roi_poly = a.get("roi_poly", [])
            if len(roi_poly) >= 3:
                za = [self._px(px, py) for px, py in roi_poly]
                dpg.draw_polygon(za, color=(100, 255, 100, 150), fill=(100, 255, 100, 40), parent=p)
                cx = sum(pt[0] for pt in roi_poly) / len(roi_poly)
                cy = sum(pt[1] for pt in roi_poly) / len(roi_poly)
                c_px, c_py = self._px(cx, cy)
                dpg.draw_circle((c_px, c_py), 8, color=(100, 255, 100), fill=(100, 255, 100, 100), parent=p)
                dpg.draw_text((c_px + 12, c_py - 12), f"{num} (YOLO Click: {a.get('yolo_model')})", color=(100, 255, 100), size=16, parent=p)

            if selezionato:
                if len(roi_poly) >= 3:
                    dpg.draw_polygon(za, color=SEL_COL, thickness=SEL_TH, parent=p)
                    
        elif t == "yolo_click_all":
            roi_poly = a.get("roi_poly", [])
            if len(roi_poly) >= 3:
                za = [self._px(px, py) for px, py in roi_poly]
                dpg.draw_polygon(za, color=(100, 255, 150, 150), fill=(100, 255, 150, 40), parent=p)
                cx = sum(pt[0] for pt in roi_poly) / len(roi_poly)
                cy = sum(pt[1] for pt in roi_poly) / len(roi_poly)
                c_px, c_py = self._px(cx, cy)
                dpg.draw_circle((c_px, c_py), 8, color=(100, 255, 150), fill=(100, 255, 150, 100), parent=p)
                dpg.draw_text((c_px + 12, c_py - 12), f"{num} (ALL YOLO Click: {a.get('yolo_model')})", color=(100, 255, 150), size=16, parent=p)

            if selezionato:
                if len(roi_poly) >= 3:
                    dpg.draw_polygon(za, color=SEL_COL, thickness=SEL_TH, parent=p)

        elif t == "yolo_drag_seq":
            roi_poly = a.get("roi_poly", [])
            if len(roi_poly) >= 3:
                za = [self._px(px, py) for px, py in roi_poly]
                dpg.draw_polygon(za, color=(255, 120, 200, 150), fill=(255, 120, 200, 40), parent=p)
                cx = sum(pt[0] for pt in roi_poly) / len(roi_poly)
                cy = sum(pt[1] for pt in roi_poly) / len(roi_poly)
                c_px, c_py = self._px(cx, cy)
                dpg.draw_circle((c_px, c_py), 8, color=(255, 120, 200), fill=(255, 120, 200, 100), parent=p)
                dpg.draw_text((c_px + 12, c_py - 12), f"{num} (SEQ YOLO: {a.get('yolo_model')})", color=(255, 120, 200), size=16, parent=p)
            if selezionato:
                if len(roi_poly) >= 3:
                    dpg.draw_polygon(za, color=SEL_COL, thickness=SEL_TH, parent=p)

        elif t == "click_until":
            for i, (cx, cy, bx, by) in enumerate(a.get("punti", [])):
                pc = self._px(cx, cy)
                pb = self._px(bx, by)
                dpg.draw_circle(pc, 5, color=(255, 255, 255), fill=(255, 255, 255), parent=p)
                dpg.draw_circle(pb, 5, color=(100, 255, 255), fill=(100, 255, 255), parent=p)
                dpg.draw_arrow(pb, pc, color=(200, 255, 255), thickness=2, size=10, parent=p)
                if selezionato:
                    dpg.draw_circle(pc, 10, color=SEL_COL, thickness=SEL_TH, parent=p)
                    dpg.draw_circle(pb, 10, color=SEL_COL, thickness=SEL_TH, parent=p)
                    
        elif t == "simon_says":
            for i, (dx, dy) in enumerate(a.get("display", [])):
                pd = self._px(dx, dy)
                pk = self._px(a["keypad"][i][0], a["keypad"][i][1])
                dpg.draw_circle(pd, 6, color=(100, 200, 255), fill=(100, 200, 255), parent=p)
                dpg.draw_circle(pk, 6, color=(255, 100, 255), fill=(255, 100, 255), parent=p)
                dpg.draw_arrow(pk, pd, color=(200, 150, 255, 150), thickness=2, size=10, parent=p)
                if selezionato:
                    dpg.draw_circle(pd, 12, color=SEL_COL, thickness=SEL_TH, parent=p)
                    dpg.draw_circle(pk, 12, color=SEL_COL, thickness=SEL_TH, parent=p)

        elif t == "click_anomaly":
            for i, p_list in enumerate(a.get("punti", [])):
                if len(p_list) == 4:
                    cx, cy, bx, by = p_list
                    pc = self._px(cx, cy)
                    pb = self._px(bx, by)
                    dpg.draw_circle(pc, 5, color=(255, 100, 200), fill=(255, 100, 200), parent=p)
                    dpg.draw_circle(pb, 5, color=(255, 50, 100), fill=(255, 50, 100), parent=p)
                    dpg.draw_arrow(pb, pc, color=(255, 150, 200), thickness=2, size=10, parent=p)
                    dpg.draw_text((pc[0] + 10, pc[1] - 10), str(i+1), color=(255, 100, 200), size=14, parent=p)
                    if selezionato:
                        dpg.draw_circle(pc, 10, color=SEL_COL, thickness=SEL_TH, parent=p)
                        dpg.draw_circle(pb, 10, color=SEL_COL, thickness=SEL_TH, parent=p)
                elif len(p_list) == 2:
                    cx, cy = p_list
                    pc = self._px(cx, cy)
                    dpg.draw_circle(pc, 5, color=(255, 100, 200), fill=(255, 100, 200), parent=p)
                    dpg.draw_text((pc[0] + 10, pc[1] - 10), str(i+1) + " (old)", color=(255, 100, 200), size=14, parent=p)
                    if selezionato:
                        dpg.draw_circle(pc, 10, color=SEL_COL, thickness=SEL_TH, parent=p)
                        
        elif t == "number_match":
            for k, btn in enumerate(a.get("buttons", [])):
                r = btn["rect"]
                x1, y1 = self._px(r[0], r[1])
                x2, y2 = self._px(r[2], r[3])
                dpg.draw_rectangle((x1, y1), (x2, y2), color=(100, 255, 255, 255), fill=(100, 255, 255, 40), parent=p)
                dpg.draw_text((x1 + 4, y1 + 4), f"{num}.{k+1}", color=(100, 255, 255), size=14, parent=p)
                if selezionato:
                    dpg.draw_rectangle((x1 - 3, y1 - 3), (x2 + 3, y2 + 3),
                                       color=SEL_COL, thickness=SEL_TH, parent=p)

        elif t == "ocr_keypad":
            roi = a.get("roi_poly", [])
            kp = a.get("keypad", [])
            if len(roi) >= 3:
                za = [self._px(px, py) for px, py in roi]
                dpg.draw_polygon(za, color=(100, 255, 200, 150), fill=(100, 255, 200, 40), parent=p)
                if selezionato: dpg.draw_polygon(za, color=SEL_COL, thickness=SEL_TH, parent=p)
            for i, (kx, ky) in enumerate(kp):
                pk = self._px(kx, ky)
                dpg.draw_circle(pk, 7, color=(255, 100, 255), fill=(255, 100, 255), parent=p)
                dpg.draw_text((pk[0]-4, pk[1]-6), str(i), color=(0, 0, 0, 255), size=12, parent=p)
                if selezionato: dpg.draw_circle(pk, 11, color=SEL_COL, thickness=SEL_TH, parent=p)

        if selezionato:
            self._disegna_handles(a)

    def _disegna_handles(self, a):
        """Disegna su DPG handles."""
        p = self.TAG_CANVAS
        HANDLE_R    = 5
        HANDLE_FILL = (255, 255, 255, 230)
        HANDLE_EDGE = (30, 30, 30, 255)

        def h(vx, vy):
            """Funzione di euristica per l'algoritmo A*."""
            x, y = self._px(vx, vy)
            dpg.draw_circle((x, y), HANDLE_R, color=HANDLE_EDGE,
                            fill=HANDLE_FILL, thickness=1, parent=p)

        t = a.get("tipo")
        if t == "click":
            h(a["rx"], a["ry"])
        elif t == "click_rect":
            r = a["rect"]
            h(r[0], r[1])
            h(r[2], r[3])
        elif t == "click_poly":
            for vx, vy in a.get("poly", []):
                h(vx, vy)
        elif t in ("drag", "drag_hold"):
            h(a["start_rx"], a["start_ry"])
            h(a["end_rx"],   a["end_ry"])
        elif t == "drag_multi":
            for vx, vy in a.get("punti", []):
                h(vx, vy)
        elif t == "drag_zone":
            for vx, vy in a.get("zone_a", []):
                h(vx, vy)
            for vx, vy in a.get("zone_b", []):
                h(vx, vy)
        elif t == "wiring":
            for k, (vx, vy) in enumerate(a.get("left", [])):
                h(vx, vy)
            for k, (vx, vy) in enumerate(a.get("right", [])):
                h(vx, vy)
            for k, (vx, vy) in enumerate(a.get("lights", [])):
                h(vx, vy)
        elif t == "sync_click":
            for k, (cx, cy, bx, by) in enumerate(a.get("punti", [])):
                h(cx, cy)
                h(bx, by)
        elif t in ("yolo_drag", "yolo_drag_all"):
            h(a["end_rx"], a["end_ry"])
            for k, (vx, vy) in enumerate(a.get("roi_poly", [])):
                h(vx, vy)
        elif t in ("yolo_click", "yolo_click_all", "yolo_drag_seq"):
            for k, (vx, vy) in enumerate(a.get("roi_poly", [])):
                h(vx, vy)
        elif t == "click_until":
            for k, (cx, cy, bx, by) in enumerate(a.get("punti", [])):
                h(cx, cy)
                h(bx, by)
        elif t == "simon_says":
            for k, (dx, dy) in enumerate(a.get("display", [])):
                h(dx, dy)
            for k, (kx, ky) in enumerate(a.get("keypad", [])):
                h(kx, ky)
        elif t == "click_anomaly":
            for k, p_list in enumerate(a.get("punti", [])):
                if len(p_list) == 4:
                    cx, cy, bx, by = p_list
                    h(cx, cy)
                    h(bx, by)
                elif len(p_list) == 2:
                    cx, cy = p_list
                    h(cx, cy)
        elif t == "number_match":
            for btn in a.get("buttons", []):
                r = btn["rect"]
                h(r[0], r[1])
                h(r[2], r[3])
        elif t == "ocr_keypad":
            for k, (vx, vy) in enumerate(a.get("roi_poly", [])):
                h(vx, vy)
            for k, (vx, vy) in enumerate(a.get("keypad", [])):
                h(vx, vy)

    def _disegna_buffer_corrente(self):
        """Disegna su DPG buffer corrente."""
        p = self.TAG_CANVAS

        if self.stato in (self.WAIT_POLY,
                          self.WAIT_POLY_ZONE_A,
                          self.WAIT_POLY_ZONE_B,
                          self.WAIT_YOLO_POLY,
                          self.WAIT_YOLO_DEST,
                          self.WAIT_YOLO_ALL_POLY,
                          self.WAIT_YOLO_ALL_DEST,
                          self.WAIT_YOLO_CLICK_POLY,
                          self.WAIT_YOLO_CLICK_ALL_POLY,
                          self.WAIT_YOLO_SEQ_POLY,
                          self.WAIT_OCR_POLY):
            pts = [self._px(rx, ry) for rx, ry in self.buffer_punti]
            for pt in pts:
                dpg.draw_circle(pt, 4, color=(255, 255, 0),
                                fill=(255, 255, 0), parent=p)
            for i in range(len(pts) - 1):
                dpg.draw_line(pts[i], pts[i+1], color=(255, 255, 0), thickness=2, parent=p)

            if self.stato == self.WAIT_POLY_ZONE_B and len(self.buffer_zone_a) >= 3:
                za = [self._px(rx, ry) for rx, ry in self.buffer_zone_a]
                dpg.draw_polygon(za, color=(255, 200, 0, 255),
                                 fill=(255, 200, 0, 40), parent=p)

            if self.stato == self.WAIT_YOLO_DEST and len(self.buffer_zone_a) >= 3:
                za = [self._px(rx, ry) for rx, ry in self.buffer_zone_a]
                dpg.draw_polygon(za, color=(255, 100, 255, 255),
                                 fill=(255, 100, 255, 40), parent=p)

            if self.stato == self.WAIT_YOLO_ALL_DEST and len(self.buffer_zone_a) >= 3:
                za = [self._px(rx, ry) for rx, ry in self.buffer_zone_a]
                dpg.draw_polygon(za, color=(255, 150, 50, 255),
                                 fill=(255, 150, 50, 40), parent=p)
            
            if self.stato == self.WAIT_OCR_KEYPAD and len(self.buffer_zone_a) >= 3:
                za = [self._px(rx, ry) for rx, ry in self.buffer_zone_a]
                dpg.draw_polygon(za, color=(100, 255, 200, 255), fill=(100, 255, 200, 40), parent=p)

        if self.stato == self.WAIT_MULTI:
            pts = [self._px(rx, ry) for rx, ry in self.buffer_punti]
            for pt in pts:
                dpg.draw_circle(pt, 5, color=(255, 180, 100),
                                fill=(255, 180, 100), parent=p)
            for i in range(len(pts) - 1):
                dpg.draw_arrow(pts[i+1], pts[i], color=(255, 180, 100),
                               thickness=2, size=12, parent=p)

        if self.stato == "WAIT_RECT_ON_CANVAS" and self.rect_start and self.rect_end:
            x1, y1 = self._px(*self.rect_start)
            x2, y2 = self._px(*self.rect_end)
            dpg.draw_rectangle((x1, y1), (x2, y2),
                               color=(180, 255, 180, 255),
                               fill=(180, 255, 180, 40), parent=p)

        if self.stato in (self.WAIT_DRAG_END, self.WAIT_DRAG_HOLD_END) and self.buffer_punti:
            rx, ry = self.buffer_punti[0]
            x, y = self._px(rx, ry)
            col = (255, 200, 0) if self.stato == self.WAIT_DRAG_END else (255, 140, 180)
            dpg.draw_circle((x, y), 6, color=col, fill=col, parent=p)
            dpg.draw_text((x + 10, y - 10), "A", color=col, size=16, parent=p)

        if self.stato in (self.WAIT_WIRING_L, self.WAIT_WIRING_R, self.WAIT_WIRING_C):
            for (rx, ry) in self.buffer_w_l:
                dpg.draw_circle(self._px(rx, ry), 5, color=(200, 255, 100), fill=(200, 255, 100), parent=p)
            for (rx, ry) in self.buffer_w_r:
                dpg.draw_circle(self._px(rx, ry), 5, color=(255, 160, 50), fill=(255, 160, 50), parent=p)
            for (rx, ry) in self.buffer_w_c:
                dpg.draw_circle(self._px(rx, ry), 6, color=(255, 255, 100), fill=(255, 255, 100), parent=p)

        if self.stato in (self.WAIT_SYNC_CHECK, self.WAIT_SYNC_BTN):
            for (cx, cy, bx, by) in self.buffer_sync:
                pc = self._px(cx, cy)
                pb = self._px(bx, by)
                dpg.draw_circle(pc, 5, color=(255, 255, 100), fill=(255, 255, 100), parent=p)
                dpg.draw_circle(pb, 5, color=(255, 100, 100), fill=(255, 100, 100), parent=p)
                dpg.draw_arrow(pb, pc, color=(255, 200, 150), thickness=2, size=10, parent=p)
            if self.stato == self.WAIT_SYNC_BTN and self.buffer_punti:
                pc = self._px(self.buffer_punti[0][0], self.buffer_punti[0][1])
                dpg.draw_circle(pc, 5, color=(255, 255, 100), fill=(255, 255, 100), parent=p)
                
        if self.stato in (self.WAIT_CUC_CHK, self.WAIT_CUC_BTN):
            for (cx, cy, bx, by) in self.buffer_cuc:
                pc = self._px(cx, cy)
                pb = self._px(bx, by)
                dpg.draw_circle(pc, 5, color=(255, 255, 255), fill=(255, 255, 255), parent=p)
                dpg.draw_circle(pb, 5, color=(100, 255, 255), fill=(100, 255, 255), parent=p)
                dpg.draw_arrow(pb, pc, color=(200, 255, 255), thickness=2, size=10, parent=p)
            if self.stato == self.WAIT_CUC_BTN and self.buffer_punti:
                pc = self._px(self.buffer_punti[0][0], self.buffer_punti[0][1])
                dpg.draw_circle(pc, 5, color=(255, 255, 255), fill=(255, 255, 255), parent=p)
                
        if self.stato in (self.WAIT_SIMON_DISPLAY, self.WAIT_SIMON_KEYPAD):
            for (rx, ry) in self.buffer_simon_d:
                pd = self._px(rx, ry)
                dpg.draw_circle(pd, 6, color=(100, 200, 255), fill=(100, 200, 255), parent=p)
            for i, (rx, ry) in enumerate(self.buffer_simon_k):
                pk = self._px(rx, ry)
                dpg.draw_circle(pk, 6, color=(255, 100, 255), fill=(255, 100, 255), parent=p)
                if i < len(self.buffer_simon_d):
                    pd = self._px(self.buffer_simon_d[i][0], self.buffer_simon_d[i][1])
                    dpg.draw_arrow(pk, pd, color=(200, 150, 255, 150), thickness=2, size=10, parent=p)
                    
        if self.stato in (self.WAIT_ANOMALY_CHK, self.WAIT_ANOMALY_BTN):
            for (cx, cy, bx, by) in self.buffer_anomaly:
                pc = self._px(cx, cy)
                pb = self._px(bx, by)
                dpg.draw_circle(pc, 5, color=(255, 100, 200), fill=(255, 100, 200), parent=p)
                dpg.draw_circle(pb, 5, color=(255, 50, 100), fill=(255, 50, 100), parent=p)
                dpg.draw_arrow(pb, pc, color=(255, 150, 200), thickness=2, size=10, parent=p)
            if self.stato == self.WAIT_ANOMALY_BTN and self.buffer_punti:
                pc = self._px(self.buffer_punti[0][0], self.buffer_punti[0][1])
                dpg.draw_circle(pc, 5, color=(255, 100, 200), fill=(255, 100, 200), parent=p)
                
        if self.stato == self.WAIT_NUM_MATCH_RECT:
            for i, btn in enumerate(self.buffer_num_match):
                r = btn["rect"]
                x1, y1 = self._px(r[0], r[1])
                x2, y2 = self._px(r[2], r[3])
                dpg.draw_rectangle((x1, y1), (x2, y2), color=(100, 255, 255, 255), fill=(100, 255, 255, 40), parent=p)
                dpg.draw_text((x1 + 4, y1 + 4), f"{i+1}", color=(100, 255, 255), size=16, parent=p)
            if self.rect_start and self.rect_end:
                x1, y1 = self._px(*self.rect_start)
                x2, y2 = self._px(*self.rect_end)
                dpg.draw_rectangle((x1, y1), (x2, y2), color=(100, 255, 255, 255), fill=(100, 255, 255, 40), parent=p)
                
        if self.stato == self.WAIT_OCR_KEYPAD:
            for i, (kx, ky) in enumerate(self.buffer_keypad):
                pk = self._px(kx, ky)
                dpg.draw_circle(pk, 7, color=(255, 100, 255), fill=(255, 100, 255), parent=p)
                dpg.draw_text((pk[0]-4, pk[1]-6), str(i), color=(0, 0, 0, 255), size=12, parent=p)
