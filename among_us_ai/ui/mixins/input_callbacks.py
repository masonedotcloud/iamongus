"""
Callback DPG di mouse, zoom, camera, viewport.

Mixin di GPSVisualizerPro: metodi separati per organizzazione, ma
condividono lo stato self.* della classe principale.
"""

from ._imports import *



class InputCallbacksMixin:
    """Mixin con i metodi di input callbacks di GPSVisualizerPro."""
    # Callback per l'evento
    def _on_viewport_resize(self, *args):
        """Callback per l'evento viewport resize."""
        vp_w = dpg.get_viewport_client_width()
        vp_h = dpg.get_viewport_client_height()
        self.canvas_w = max(200, vp_w - GPSConfig.SIDE_PANEL_W - 20)
        self.canvas_h = max(200, vp_h - GPSConfig.STATUS_BAR_H - 60)
        # Cambia le configurazioni di un widget gia' creato
        dpg.configure_item("canvas", width=self.canvas_w, height=self.canvas_h)

    # Callback per l'evento
    def _on_mouse_wheel(self, sender, app_data):
        """Callback per l'evento mouse wheel."""
        if not dpg.is_item_hovered("canvas"): return
        factor = 1.15 if app_data > 0 else 1.0 / 1.15
        self._zoom(factor)

    # Callback per l'evento
    def _on_middle_click(self, *args):
        """Callback per l'evento middle click."""
        if not dpg.is_item_hovered("canvas"): return
        if self.camera_mode == "follow":
            self.free_cam = list(self.pos_visuale)
            self.camera_mode = "free"
        self.is_panning = True
        self.pan_start_cam = tuple(self.free_cam)

    # Callback per l'evento
    def _on_middle_drag(self, sender, app_data):
        """Callback per l'evento middle drag."""
        if not self.is_panning: return
        _, dx, dy = app_data
        self.free_cam[0] = self.pan_start_cam[0] - dx / self.scale
        self.free_cam[1] = self.pan_start_cam[1] + dy / self.scale

    # Callback per l'evento
    def _on_middle_release(self, *args):
        """Callback per l'evento middle release."""
        self.is_panning = False

    # Callback per l'evento
    def _on_left_click(self, *args):
        """Callback per l'evento left click."""
        if not dpg.is_item_hovered("canvas"): return

        # Modalita' disegno zona: il click inizializza la lista punti
        if self.zone_draw_mode:
            if self.zone_draw_type == "door":
                gx, gy = self._mouse_to_game()
                self.door_rect_start = (gx, gy)
                self.door_rect_end = (gx, gy)
                return
            gx, gy = self._mouse_to_game()
            self.zone_draw_points = [(gx, gy)]
            mx, my = dpg.get_drawing_mouse_pos()
            self.zone_last_pixel = (mx, my)
            return

        if not self.auto_enabled:
            self.auto_status_msg = "Auto-move disattivato (premi M)"
            return

        mx, my = dpg.get_drawing_mouse_pos()
        cam_x, cam_y = self._camera_center()
        half_w = self.canvas_w / 2
        half_h = self.canvas_h / 2
        game_x = cam_x + (mx - half_w) / self.scale
        game_y = cam_y - (my - half_h) / self.scale

        self._plan_path((game_x, game_y))

    # Callback per l'evento
    def _on_left_drag(self, *args):
        """Callback per l'evento left drag."""
        # Aggiunge punti al poligono con throttling basato su distanza pixel
        if not self.zone_draw_mode:
            return
            
        if self.zone_draw_type == "door":
            if getattr(self, 'door_rect_start', None):
                gx, gy = self._mouse_to_game()
                self.door_rect_end = (gx, gy)
            return
            
        if not self.zone_draw_points:
            return
            
        mx, my = dpg.get_drawing_mouse_pos()
        if self.zone_last_pixel is None:
            self.zone_last_pixel = (mx, my)
        dpx = abs(mx - self.zone_last_pixel[0]) + abs(my - self.zone_last_pixel[1])
        if dpx >= GPSConfig.ZONA_PUNTO_DIST_PX:
            gx, gy = self._mouse_to_game()
            self.zone_draw_points.append((gx, gy))
            self.zone_last_pixel = (mx, my)

    # Callback per l'evento
    def _on_left_release(self, *args):
        """Callback per l'evento left release."""
        if not self.zone_draw_mode:
            return
            
        if self.zone_draw_type == "door":
            if not getattr(self, 'door_rect_start', None) or not getattr(self, 'door_rect_end', None):
                self.zone_draw_mode = False
                self.auto_status_msg = "Disegno porta annullato"
                return
                
            x1, y1 = self.door_rect_start
            x2, y2 = self.door_rect_end
            
            # Se ha solo cliccato (distanza minima), usa dimensione fissa 3x3
            if abs(x2 - x1) < 0.1 and abs(y2 - y1) < 0.1:
                w, h = 1.5, 1.5
                cx_b, cy_b = x1, y1
            else:
                w = abs(x2 - x1) / 2
                h = abs(y2 - y1) / 2
                cx_b = (x1 + x2) / 2
                cy_b = (y1 + y2) / 2
                
            punti_puliti = [
                [cx_b - w, cy_b - h],
                [cx_b + w, cy_b - h],
                [cx_b + w, cy_b + h],
                [cx_b - w, cy_b + h]
            ]
            
            self.door_rect_start = None
            self.door_rect_end = None

        else:
            if not self.zone_draw_points:
                return
            gx, gy = self._mouse_to_game()
            if self.zone_draw_points[-1] != (gx, gy):
                self.zone_draw_points.append((gx, gy))

            # --- NOVITA': ADATTAMENTO AUTOMATICO ---
            punti_grezzi = list(self.zone_draw_points)
            punti_puliti = self._adatta_punti_alla_mappa(punti_grezzi)
        
            self.zone_draw_points = []
            self.zone_last_pixel = None

        if len(punti_puliti) < 3:
            self.zone_draw_mode = False
            self.zona_in_modifica = None
            self.auto_status_msg = "Area non mappata o troppo piccola"
            return

        if self.zona_in_modifica is not None:
            id_mod = self.zona_in_modifica
            self.zona_in_modifica = None
            self.zone_draw_mode = False
            if self.zone_draw_type == "door":
                self.door_zone_mgr.aggiorna_forma(id_mod, punti_puliti)
                self.auto_status_msg = "Forma zona porta aggiornata"
            else:
                self.zone_mgr.aggiorna_forma(id_mod, punti_puliti)
                self.auto_status_msg = "Forma adattata ai muri"
            self.zone_draw_type = "normal"
            return

        if self.zone_draw_type == "door":
            def on_name_door(nome):
                """Callback di input del nome (zona porta)."""
                self.zone_draw_mode = False
                self.zone_draw_type = "normal"
                if nome:
                    self.door_zone_mgr.aggiungi(nome, punti_puliti, colore="#FF3333")
                    self._refresh_door_zone_list()
                    self.auto_status_msg = f"Zona Porta '{nome}' creata"
                else:
                    self.auto_status_msg = "Annullato"
            self._show_text_input("Nuova Zona Porta", "", on_name_door)
            return

        def on_name(nome):
            """Callback dell'input testo: aggiorna l'attributo `self.nome_lobby`."""
            self.zone_draw_mode = False
            if nome:
                # Crea la zona con i punti gia' "puliti"
                self.zone_mgr.aggiungi(nome, punti_puliti)
                self._refresh_zone_list()
                self.auto_status_msg = f"Zona '{nome}' creata e adattata"
            else:
                self.auto_status_msg = "Annullato"

        self._show_text_input("Nuova Zona", "", on_name)

    def _mouse_to_game(self):
        """Converte (mx, my) dal sistema di riferimento drawlist al sistema di gioco."""
        mx, my = dpg.get_drawing_mouse_pos()
        cam_x, cam_y = self._camera_center()
        half_w = self.canvas_w / 2
        half_h = self.canvas_h / 2
        gx = cam_x + (mx - half_w) / self.scale
        gy = cam_y - (my - half_h) / self.scale
        return (gx, gy)

    def _is_point_in_polygon(self, x, y, poly):
        """Algoritmo Ray Casting per verificare se (x,y) e' dentro il poligono."""
        n = len(poly)
        inside = False
        p1x, p1y = poly[0]
        for i in range(n + 1):
            p2x, p2y = poly[i % n]
            if y > min(p1y, p2y):
                if y <= max(p1y, p2y):
                    if x <= max(p1x, p2x):
                        if p1y != p2y:
                            xints = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        if p1x == p2x or x <= xints:
                            inside = not inside
            p1x, p1y = p2x, p2y
        return inside

    def _camera_center(self):
        """Operazioni telecamera: center."""
        if self.camera_mode == "follow":
            return (self.pos_visuale[0], self.pos_visuale[1])
        return (self.free_cam[0], self.free_cam[1])

    # Callback per l'evento
    def _on_zoom_slider(self, sender, app_data):
        """Callback per l'evento zoom slider."""
        self.scale = max(GPSConfig.MIN_SCALE,
                         min(GPSConfig.MAX_SCALE, app_data))

    def _zoom(self, factor):
        """Applica uno zoom di `factor` mantenendo il cursore come centro dello zoom."""
        self.scale = max(GPSConfig.MIN_SCALE,
                         min(GPSConfig.MAX_SCALE, self.scale * factor))
        if dpg.does_item_exist("zoom_slider"):
            dpg.set_value("zoom_slider", self.scale)

    def _toggle(self, attr):
        """Inverte lo stato di un attributo boolean di self (es. mostra/nascondi layer)."""
        setattr(self, attr, not getattr(self, attr))

    # Callback per l'evento
    def _on_toggle_visited(self, sender, app_data):
        """Callback per l'evento toggle visited."""
        self.show_visited = app_data
        # Cambia le configurazioni di un widget gia' creato
        dpg.configure_item("map_node", show=self.show_visited)

    def _set_camera(self, mode):
        """Imposta la camera sul giocatore (modalita' follow) o libera (drag camera)."""
        self.camera_mode = mode
        if mode == "overview":
            self._fit_to_map()
        elif mode == "free":
            self.free_cam = list(self.pos_visuale)

    def _fit_to_map(self):
        """Calcola scala e offset per inquadrare tutta la mappa nel viewport."""
        if not self.map_bounds: return
        min_x, min_y, max_x, max_y = self.map_bounds
        w_u = max_x - min_x; h_u = max_y - min_y
        if w_u <= 0 or h_u <= 0: return
        scale_x = self.canvas_w / w_u
        scale_y = self.canvas_h / h_u
        self.scale = max(GPSConfig.MIN_SCALE,
                         min(GPSConfig.MAX_SCALE, min(scale_x, scale_y) * 0.95))
        if dpg.does_item_exist("zoom_slider"):
            dpg.set_value("zoom_slider", self.scale)
        self.free_cam = [(min_x + max_x) / 2, (min_y + max_y) / 2]

    def _reset_view(self):
        """Resetta zoom e offset ai valori di default (centra il giocatore)."""
        self.scale = GPSConfig.DEFAULT_SCALE
        if dpg.does_item_exist("zoom_slider"):
            dpg.set_value("zoom_slider", self.scale)
        if self.camera_mode == "free":
            self.free_cam = list(self.pos_visuale)

    # Callback per l'evento
    def _on_auto_checkbox(self, sender, app_data):
        """Callback per l'evento auto checkbox."""
        self.auto_enabled = app_data
        if not app_data:
            self._cancel_auto_move(silent=True)
