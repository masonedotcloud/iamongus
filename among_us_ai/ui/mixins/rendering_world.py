"""
Rendering del mondo statico: griglia, zone, porte, trail, path, target di navigazione, POI.

Mixin di GPSVisualizerPro.
"""

from ._imports import *


class RenderingWorldMixin:
    """Mixin con i metodi di rendering world di GPSVisualizerPro."""
    def _render_grid(self, cam_x, cam_y, half_w, half_h, scale):
        """Disegna la griglia di sfondo (ortogonale, centrata sull'origine del gioco)."""
        dpg.delete_item("grid_node", children_only=True)
        if not self.show_grid: return
        dpg.push_container_stack("grid_node")

        grid_size = GPSConfig.GRID_SIZE
        while grid_size * scale < 28: grid_size *= 2
        while grid_size * scale > 140: grid_size /= 2

        step_px = grid_size * scale
        off_x = (cam_x % grid_size) * scale
        off_y = (cam_y % grid_size) * scale

        n = int(self.canvas_w / step_px) + 2
        x = half_w - off_x - step_px * (n // 2 + 1)
        end_x = self.canvas_w + step_px
        while x < end_x:
            game_x = cam_x + (x - half_w) / scale
            col = Colors.AXIS if abs(game_x) < grid_size / 2 else Colors.GRID
            dpg.draw_line((x, 0), (x, self.canvas_h), color=col, thickness=1)
            x += step_px

        n = int(self.canvas_h / step_px) + 2
        y = half_h + off_y - step_px * (n // 2 + 1)
        end_y = self.canvas_h + step_px
        while y < end_y:
            game_y = cam_y - (y - half_h) / scale
            col = Colors.AXIS if abs(game_y) < grid_size / 2 else Colors.GRID
            dpg.draw_line((0, y), (self.canvas_w, y), color=col, thickness=1)
            y += step_px

        dpg.pop_container_stack()

    def _render_zones(self, cam_x, cam_y, half_w, half_h, scale):
        """Disegna i poligoni delle zone disegnate dall'utente, con riempimento semi-trasparente."""
        dpg.delete_item("zone_node", children_only=True)
        dpg.push_container_stack("zone_node")

        # Zone salvate
        for z in self.zone_mgr.zone:
            pts = z.get('punti', [])
            if len(pts) < 3:
                continue

            pts_schermo = []
            for gx, gy in pts:
                sx = half_w + scale * (gx - cam_x)
                sy = half_h - scale * (gy - cam_y)
                pts_schermo.append((sx, sy))

            # Culling bounding-box
            xs = [p[0] for p in pts_schermo]
            ys = [p[1] for p in pts_schermo]
            if max(xs) < 0 or min(xs) > self.canvas_w: continue
            if max(ys) < 0 or min(ys) > self.canvas_h: continue

            col_full = _hex_to_rgba(z['colore'], 230)
            col_fill = _hex_to_rgba(z['colore'], 45)

            # Evidenzia la zona che stiamo modificando (bordo bianco piu' spesso)
            if z['id'] == self.zona_in_modifica:
                outline = (255, 255, 255, 255)
                thickness = 3
            else:
                outline = col_full
                thickness = 2

            dpg.draw_polygon(points=pts_schermo,
                             color=outline, fill=col_fill,
                             thickness=thickness)

            # Etichetta al centroide
            cx_lbl = sum(xs) / len(xs)
            cy_lbl = sum(ys) / len(ys)
            nome = z['nome']
            txt_w = max(20, len(nome) * 7.5)
            dpg.draw_rectangle(
                (cx_lbl - txt_w / 2 - 5, cy_lbl - 11),
                (cx_lbl + txt_w / 2 + 5, cy_lbl + 11),
                color=col_full, fill=col_full)
            dpg.draw_text((cx_lbl - txt_w / 2, cy_lbl - 8),
                          nome, color=(255, 255, 255, 255), size=14)

        # Render Zone Porte (YOLO)
        if getattr(self, 'show_door_zones', True):
            for z in self.door_zone_mgr.zone:
                pts = z.get('punti', [])
                if len(pts) < 3: continue
                pts_schermo = []
                for gx, gy in pts:
                    sx = half_w + scale * (gx - cam_x)
                    sy = half_h - scale * (gy - cam_y)
                    pts_schermo.append((sx, sy))

                xs = [p[0] for p in pts_schermo]
                ys = [p[1] for p in pts_schermo]
                if max(xs) < 0 or min(xs) > self.canvas_w: continue
                if max(ys) < 0 or min(ys) > self.canvas_h: continue

                col_full = _hex_to_rgba(z.get('colore', '#FF3333'), 200)
                col_fill = _hex_to_rgba(z.get('colore', '#FF3333'), 30)
                dpg.draw_polygon(points=pts_schermo, color=col_full, fill=col_fill, thickness=2)
                cx_lbl = sum(xs) / len(xs)
                cy_lbl = sum(ys) / len(ys)
                dpg.draw_text((cx_lbl - len(z['nome'])*3, cy_lbl - 8), z['nome'], color=(255, 100, 100, 255), size=13)

        # Preview del poligono in corso di disegno
        if self.zone_draw_mode:
            if getattr(self, 'zone_draw_type', 'normal') == "door" and getattr(self, 'door_rect_start', None) and getattr(self, 'door_rect_end', None):
                x1, y1 = self.door_rect_start
                x2, y2 = self.door_rect_end
                sx1 = half_w + scale * (x1 - cam_x)
                sy1 = half_h - scale * (y1 - cam_y)
                sx2 = half_w + scale * (x2 - cam_x)
                sy2 = half_h - scale * (y2 - cam_y)
                dpg.draw_rectangle((sx1, sy1), (sx2, sy2), color=(255, 50, 50, 255), fill=(255, 50, 50, 40), parent="zone_node")
            elif getattr(self, 'zone_draw_type', 'normal') == "normal" and len(self.zone_draw_points) >= 1:
                pts_schermo = []
                for gx, gy in self.zone_draw_points:
                    sx = half_w + scale * (gx - cam_x)
                    sy = half_h - scale * (gy - cam_y)
                    pts_schermo.append((sx, sy))

                # "Rubber band": aggiungi la posizione corrente del mouse
                if dpg.is_item_hovered("canvas"):
                    mpos = dpg.get_drawing_mouse_pos()
                    pts_schermo.append((mpos[0], mpos[1]))

                preview_color = Colors.ZONE_PREVIEW

                # Linea continua tra i punti
                for i in range(len(pts_schermo) - 1):
                    dpg.draw_line(pts_schermo[i], pts_schermo[i + 1],
                                  color=preview_color, thickness=2)
                # Linea di chiusura sottile verso il primo punto
                if len(pts_schermo) >= 3:
                    dpg.draw_line(pts_schermo[-1], pts_schermo[0],
                                  color=(180, 180, 180, 150), thickness=1)
                # Pallini sui vertici
                for sx, sy in pts_schermo:
                    dpg.draw_circle((sx, sy), 2,
                                    color=preview_color,
                                    fill=preview_color)

        dpg.pop_container_stack()

    def _render_doors(self, cam_x, cam_y, half_w, half_h, scale):
        """Disegna gli ostacoli dinamici (porte chiuse) come piccoli quadrati rossi."""
        dpg.delete_item("doors_node", children_only=True)
        if not getattr(self, 'show_detected_doors', True) or not hasattr(self, 'detected_doors') or not self.detected_doors:
            return
        dpg.push_container_stack("doors_node")
        
        current_time = time.time()
        for d in self.detected_doors:
            if current_time - d['time'] < 1.0:
                sx = half_w + scale * (d['x'] - cam_x)
                sy = half_h - scale * (d['y'] - cam_y)
                
                door_w = 20
                door_h = 30
                dpg.draw_rectangle((sx - door_w/2, sy - door_h/2), (sx + door_w/2, sy + door_h/2), 
                                   color=(255, 50, 50, 200), fill=(255, 50, 50, 100), thickness=2)
                dpg.draw_text((sx - 18, sy - door_h/2 - 18), "PORTA CHIUSA", color=(255, 50, 50, 255), size=14)
                
        dpg.pop_container_stack()

    def _render_trail(self, cam_x, cam_y, half_w, half_h, scale):
        """Disegna il trail (storico delle posizioni) come polilinea giallo-fading."""
        dpg.delete_item("trail_node", children_only=True)
        if not self.show_trail or len(self.trail) < 2: return
        dpg.push_container_stack("trail_node")
        pts = []
        for tx, ty in self.trail:
            sx = half_w + scale * (tx - cam_x)
            sy = half_h - scale * (ty - cam_y)
            pts.append((sx, sy))
        n = len(pts)
        for i in range(n - 1):
            alpha = int(30 + 180 * (i / max(1, n - 1)))
            col = (Colors.TRAIL[0], Colors.TRAIL[1], Colors.TRAIL[2], alpha)
            dpg.draw_line(pts[i], pts[i + 1], color=col, thickness=2)
        dpg.pop_container_stack()

    def _render_path(self, cam_x, cam_y, half_w, half_h, scale):
        """Disegna il path A* corrente: linea piena per il tratto da percorrere, tratteggiata per quello gia' fatto."""
        dpg.delete_item("path_node", children_only=True)
        if not self.show_path or not self.auto_path: return
        dpg.push_container_stack("path_node")

        # Converto waypoint in pixel
        pts = []
        for wx, wy in self.auto_path:
            sx = half_w + scale * (wx - cam_x)
            sy = half_h - scale * (wy - cam_y)
            pts.append((sx, sy))

        # Segmenti "fatti" piu' spenti, segmenti "da fare" accesi
        current_i = self.auto_path_index
        # Connessione dal player al waypoint corrente
        px = half_w + scale * (self.pos_visuale[0] - cam_x)
        py = half_h - scale * (self.pos_visuale[1] - cam_y)
        if current_i < len(pts):
            dpg.draw_line((px, py), pts[current_i],
                          color=Colors.PATH, thickness=3)

        # Segmenti fra waypoint
        for i in range(len(pts) - 1):
            col = Colors.PATH if i >= current_i else Colors.PATH_DONE
            th = 3 if i >= current_i else 1
            dpg.draw_line(pts[i], pts[i + 1], color=col, thickness=th)

        # Marker waypoint
        for i, (sx, sy) in enumerate(pts):
            if i < current_i:
                dpg.draw_circle((sx, sy), 3, color=Colors.PATH_DONE,
                                fill=Colors.PATH_DONE)
            elif i == current_i:
                dpg.draw_circle((sx, sy), 6, color=Colors.WAYPOINT,
                                fill=Colors.WAYPOINT)
            else:
                dpg.draw_circle((sx, sy), 4, color=Colors.PATH,
                                fill=Colors.PATH)

        dpg.pop_container_stack()

    def _render_target(self, cam_x, cam_y, half_w, half_h, scale):
        """Disegna il marker del target (pos_target) come crocino rosa con alone."""
        dpg.delete_item("target_node", children_only=True)
        if self.auto_final_target is None: return
        dpg.push_container_stack("target_node")

        tx, ty = self.auto_final_target
        sx = half_w + scale * (tx - cam_x)
        sy = half_h - scale * (ty - cam_y)

        pulse = 0.5 + 0.5 * math.sin(time.time() * 5)
        r_outer = 14 + pulse * 8
        dpg.draw_circle((sx, sy), r_outer, color=Colors.TARGET_DIM,
                        fill=Colors.TARGET_DIM)
        dpg.draw_circle((sx, sy), 6, color=Colors.TARGET, fill=Colors.TARGET)
        dpg.draw_line((sx - 10, sy), (sx + 10, sy),
                      color=Colors.TARGET, thickness=1)
        dpg.draw_line((sx, sy - 10), (sx, sy + 10),
                      color=Colors.TARGET, thickness=1)
        dpg.pop_container_stack()

    def _render_poi(self, cam_x, cam_y, half_w, half_h, scale):
        """Disegna i Punti di Interesse (POI) come stelle blu con etichetta."""
        dpg.delete_item("poi_node", children_only=True)
        if not self.show_poi or not self.poi_mgr.poi_list:
            return
        dpg.push_container_stack("poi_node")

        import math as _m, time as _t
        pulse   = 0.5 + 0.5 * _m.sin(_t.time() * 3)
        COL     = (80, 200, 255)   # ciano fisso per tutti i POI
        COL_LBL = (15, 15, 20, 210)
        R = 10

        # Itera tutti i POI
        for p in self.poi_mgr.poi_list:
            sx = half_w + scale * (p['x'] - cam_x)
            sy = half_h - scale * (p['y'] - cam_y)

            if sx < -60 or sx > self.canvas_w + 60 or sy < -60 or sy > self.canvas_h + 60:
                continue

            # Alone pulsante
            glow_a = int(40 + pulse * 60)
            dpg.draw_circle((sx, sy), int(R + 7 + pulse * 4),
                            color=(*COL, glow_a), fill=(*COL, glow_a // 3), thickness=1)

            # Cerchio esterno
            dpg.draw_circle((sx, sy), R + 4,
                            color=(*COL, 220), fill=(*COL, 40), thickness=2)

            # Cerchio interno
            dpg.draw_circle((sx, sy), R,
                            color=(*COL, 255), fill=(*COL, 200), thickness=1)

            # Rombo centrale (* -> segnalino POI)
            dpg.draw_text((sx - 4, sy - 7), "*", color=(15, 15, 15, 255), size=14)

            # Etichetta: nome  [zona]
            zona_sfx = f"  [{p['nome_zona']}]" if p.get('nome_zona') else ""
            label    = f"{p['nome']}{zona_sfx}"
            txt_w    = max(20, len(label) * 7)
            dpg.draw_rectangle(
                (sx - txt_w / 2 - 4, sy - R - 22),
                (sx + txt_w / 2 + 4, sy - R - 4),
                color=(*COL, 180), fill=COL_LBL)
            dpg.draw_text((sx - txt_w / 2, sy - R - 20),
                          label, color=(*COL, 255), size=13)

        dpg.pop_container_stack()
