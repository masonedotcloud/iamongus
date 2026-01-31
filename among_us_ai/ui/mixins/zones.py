"""
Gestione delle zone nominate e delle zone porta (UI).

Mixin di GPSVisualizerPro: metodi separati per organizzazione, ma
condividono lo stato self.* della classe principale.
"""

from ._imports import *



class ZonesMixin:
    """Mixin con i metodi di zones di GPSVisualizerPro."""
    def _start_new_zone_mode(self):
        """Entra in modalita' disegno: il prossimo click+drag crea un poligono."""
        if self.zone_draw_mode:
            self._cancel_all()
            return
        self.zone_draw_mode = True
        self.zone_draw_type = "normal"
        self.zone_draw_points = []
        self.zone_last_pixel = None
        self.zona_in_modifica = None
        # Messaggio di stato mostrato all'utente nel pannello
        self.auto_status_msg = "Trascina col tasto sinistro per disegnare il poligono"

    def _start_new_door_zone_mode(self):
        """Avvia new door zone mode."""
        if self.zone_draw_mode:
            self._cancel_all()
            return
        self.zone_draw_mode = True
        self.zone_draw_type = "door"
        self.zone_draw_points = []
        self.door_rect_start = None
        self.door_rect_end = None
        self.zone_last_pixel = None
        self.zona_in_modifica = None
        # Messaggio di stato mostrato all'utente nel pannello
        self.auto_status_msg = "Trascina col tasto sinistro per creare la Zona Porta"

    def _refresh_zone_list(self):
        """Aggiorna zone list."""
        items = []
        for z in self.zone_mgr.zone:
            gzid = z.get('game_zone_id')
            id_str = f" GZ:{gzid}" if gzid is not None else ""
            items.append(f"[{z['id']:02d}]{id_str} {z['nome']}")
        # Verifica se l'elemento DPG e' gia' stato creato
        if dpg.does_item_exist("zone_listbox"):
            # Cambia le configurazioni di un widget gia' creato
            dpg.configure_item("zone_listbox", items=items)

    def _get_selected_zone(self):
        """Ritorna la zona selezionata nella listbox, oppure None."""
        if not self.zone_mgr.zone:
            return None
        # Verifica se l'elemento DPG e' gia' stato creato
        if not dpg.does_item_exist("zone_listbox"):
            return None
        selected = dpg.get_value("zone_listbox")
        if not selected:
            return None
        # Formato "[NN] nome" -> estraggo l'ID
        try:
            id_str = selected.split(']')[0].lstrip('[').strip()
            id_num = int(id_str)
            for z in self.zone_mgr.zone:
                if z['id'] == id_num:
                    return z
        except (ValueError, IndexError):
            pass
        return None

    def _refresh_door_zone_list(self):
        """Aggiorna door zone list."""
        items = []
        for z in self.door_zone_mgr.zone:
            items.append(f"[{z['id']:02d}] {z['nome']}")
        # Verifica se l'elemento DPG e' gia' stato creato
        if dpg.does_item_exist("door_zone_listbox"):
            # Cambia le configurazioni di un widget gia' creato
            dpg.configure_item("door_zone_listbox", items=items)

    def _get_selected_door_zone(self):
        """Ritorna selected door zone."""
        if not self.door_zone_mgr.zone: return None
        # Verifica se l'elemento DPG e' gia' stato creato
        if not dpg.does_item_exist("door_zone_listbox"): return None
        sel = dpg.get_value("door_zone_listbox")
        if not sel: return None
        try:
            id_num = int(sel.split(']')[0].lstrip('[').strip())
            return next((z for z in self.door_zone_mgr.zone if z['id'] == id_num), None)
        except: return None

    def _elimina_door_zone(self):
        """Elimina door zone."""
        z = self._get_selected_door_zone()
        if z is None: return
        def on_confirm(yes):
            """Callback di conferma."""
            if yes:
                self.door_zone_mgr.rimuovi(z['id'])
                self._refresh_door_zone_list()
        self._show_confirm(f"Eliminare Zona Porta '{z['nome']}'?", on_confirm)

    def _vai_a_door_zona(self):
        """Centra la telecamera su door zona."""
        z = self._get_selected_door_zone()
        if z is None:
            # Messaggio di stato mostrato all'utente nel pannello
            self.auto_status_msg = "Seleziona una zona porta dalla lista"
            return
        cx, cy = ZoneManager.centroide(z)
        self.camera_mode = "free"
        self.free_cam = [cx, cy]
        x1, y1, x2, y2 = ZoneManager.bbox(z)
        w = x2 - x1
        h = y2 - y1
        if w > 0 and h > 0:
            scale_x = self.canvas_w / (w * 1.5)
            scale_y = self.canvas_h / (h * 1.5)
            nuova = min(scale_x, scale_y)
            self.scale = max(GPSConfig.MIN_SCALE,
                             min(GPSConfig.MAX_SCALE, nuova))
            # Verifica se l'elemento DPG e' gia' stato creato
            if dpg.does_item_exist("zoom_slider"):
                # Aggiorna il valore di un widget DPG
                dpg.set_value("zoom_slider", self.scale)
        # Messaggio di stato mostrato all'utente nel pannello
        self.auto_status_msg = f"Centrato su '{z['nome']}'"

    def _modifica_forma_door_zona(self):
        """Modifica forma door zona."""
        z = self._get_selected_door_zone()
        if z is None:
            # Messaggio di stato mostrato all'utente nel pannello
            self.auto_status_msg = "Seleziona una zona porta dalla lista"
            return
        self.zona_in_modifica = z['id']
        self.zone_draw_mode = True
        self.zone_draw_type = "door"
        self.zone_draw_points = []
        self.door_rect_start = None
        self.door_rect_end = None
        self.zone_last_pixel = None
        # Messaggio di stato mostrato all'utente nel pannello
        self.auto_status_msg = f"Ridisegna '{z['nome']}' trascinando un rettangolo"

    def _cambia_colore_door_zona(self):
        """Apre il color picker per la zona porta selezionata."""
        z = self._get_selected_door_zone()
        if z is None:
            # Messaggio di stato mostrato all'utente nel pannello
            self.auto_status_msg = "Seleziona una zona porta dalla lista"
            return
        tag = "color_picker_popup_door"
        # Verifica se l'elemento DPG e' gia' stato creato
        if dpg.does_item_exist(tag):
            # Rimuove l'elemento DPG (cleanup)
            dpg.delete_item(tag)

        def pick(col_hex):
            """Callback selezione colore dalla palette."""
            self.door_zone_mgr.cambia_colore(z['id'], col_hex)
            self._refresh_door_zone_list()
            # Messaggio di stato mostrato all'utente nel pannello
            self.auto_status_msg = f"Colore di '{z['nome']}' aggiornato"
            # Verifica se l'elemento DPG e' gia' stato creato
            if dpg.does_item_exist(tag):
                # Rimuove l'elemento DPG (cleanup)
                dpg.delete_item(tag)

        vp_w = dpg.get_viewport_client_width()
        vp_h = dpg.get_viewport_client_height()
        cols_per_row = 4
        rows = [GPSConfig.COLORI_ZONE[i:i + cols_per_row]
                for i in range(0, len(GPSConfig.COLORI_ZONE), cols_per_row)]
        n_rows = len(rows)
        win_h = 70 + n_rows * 42

        with dpg.window(label=f"Colore: {z['nome']}", tag=tag, modal=True,
                        no_resize=True, no_collapse=True,
                        width=300, height=win_h,
                        pos=(max(0, vp_w // 2 - 150),
                             max(0, vp_h // 2 - win_h // 2))):
            dpg.add_text("Scegli un colore:")
            dpg.add_spacer(height=4)
            for row in rows:
                with dpg.group(horizontal=True):
                    for col_hex in row:
                        rgba = _hex_to_rgba(col_hex)
                        btn_tag = f"{tag}_btn_{col_hex}"
                        dpg.add_button(label=" ", tag=btn_tag,
                                       width=60, height=32,
                                       callback=lambda s, a, u=col_hex: pick(u))
                        # Tema personalizzato (colori e spaziature)
                        with dpg.theme() as th:
                            with dpg.theme_component(dpg.mvButton):
                                dpg.add_theme_color(dpg.mvThemeCol_Button, rgba)
                                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered,
                                                    (min(255, rgba[0] + 30),
                                                     min(255, rgba[1] + 30),
                                                     min(255, rgba[2] + 30), 255))
                                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, rgba)
                        dpg.bind_item_theme(btn_tag, th)
            dpg.add_spacer(height=6)
            dpg.add_button(label="Annulla", width=-1,
                           # Rimuove l'elemento DPG (cleanup)
                           callback=lambda *a: dpg.delete_item(tag) if dpg.does_item_exist(tag) else None)

    def _rinomina_door_zona(self):
        """Rinomina door zona."""
        z = self._get_selected_door_zone()
        if z is None:
            # Messaggio di stato mostrato all'utente nel pannello
            self.auto_status_msg = "Seleziona una zona porta dalla lista"
            return
        def on_name(nuovo):
            """Callback di input del nome."""
            if nuovo:
                self.door_zone_mgr.rinomina(z['id'], nuovo)
                self._refresh_door_zone_list()
                # Messaggio di stato mostrato all'utente nel pannello
                self.auto_status_msg = f"Zona porta rinominata in '{nuovo}'"
        self._show_text_input("Rinomina Zona Porta", z['nome'], on_name)

    def _vai_a_zona(self):
        """Centra la camera sulla zona selezionata e adatta lo zoom."""
        z = self._get_selected_zone()
        if z is None:
            # Messaggio di stato mostrato all'utente nel pannello
            self.auto_status_msg = "Seleziona una zona dalla lista"
            return
        cx, cy = ZoneManager.centroide(z)
        self.camera_mode = "free"
        self.free_cam = [cx, cy]
        # Zoom per inquadrare il poligono con margine
        x1, y1, x2, y2 = ZoneManager.bbox(z)
        w = x2 - x1
        h = y2 - y1
        if w > 0 and h > 0:
            scale_x = self.canvas_w / (w * 1.5)
            scale_y = self.canvas_h / (h * 1.5)
            nuova = min(scale_x, scale_y)
            self.scale = max(GPSConfig.MIN_SCALE,
                             min(GPSConfig.MAX_SCALE, nuova))
            # Verifica se l'elemento DPG e' gia' stato creato
            if dpg.does_item_exist("zoom_slider"):
                # Aggiorna il valore di un widget DPG
                dpg.set_value("zoom_slider", self.scale)
        # Messaggio di stato mostrato all'utente nel pannello
        self.auto_status_msg = f"Centrato su '{z['nome']}'"

    def _naviga_a_zona(self):
        """Usa A* per muovere il player verso il miglior punto calpestabile della zona."""
        z = self._get_selected_zone()
        if z is None:
            # Messaggio di stato mostrato all'utente nel pannello
            self.auto_status_msg = "Seleziona una zona dalla lista"
            return
        
        if not self.auto_enabled:
            self.auto_enabled = True
            # Verifica se l'elemento DPG e' gia' stato creato
            if dpg.does_item_exist("auto_checkbox"):
                # Aggiorna il valore di un widget DPG
                dpg.set_value("auto_checkbox", True)

        punti_poligono = z['punti']
        cx_geom, cy_geom = ZoneManager.centroide(z)
        
        # Filtra tutti i punti calpestabili che cadono dentro la zona
        walkable_in_zone = []
        for cell_key in self.pathfinder.walkable:
            gx, gy = self.pathfinder._coord(cell_key)
            if self._is_point_in_polygon(gx, gy, punti_poligono):
                walkable_in_zone.append((gx, gy))

        if walkable_in_zone:
            # Scegliamo il punto calpestabile piu' vicino al centro della zona
            target = min(walkable_in_zone, key=lambda p: math.hypot(p[0]-cx_geom, p[1]-cy_geom))
            self._plan_path(target)
            # Messaggio di stato mostrato all'utente nel pannello
            self.auto_status_msg = f"Navigazione interna a '{z['nome']}'"
        else:
            # Se la zona non e' stata ancora esplorata/mappata, fallback al centroide
            # ma il pathfinder cerchera' comunque la cella calpestabile esterna piu' vicina.
            self._plan_path((cx_geom, cy_geom))
            # Messaggio di stato mostrato all'utente nel pannello
            self.auto_status_msg = f"Zona '{z['nome']}' non mappata: vado al confine"

    def _modifica_forma_zona(self):
        """Entra in modalita' ridisegna-forma per la zona selezionata."""
        z = self._get_selected_zone()
        if z is None:
            # Messaggio di stato mostrato all'utente nel pannello
            self.auto_status_msg = "Seleziona una zona dalla lista"
            return
        self.zona_in_modifica = z['id']
        self.zone_draw_mode = True
        self.zone_draw_points = []
        self.zone_last_pixel = None
        # Messaggio di stato mostrato all'utente nel pannello
        self.auto_status_msg = f"Ridisegna '{z['nome']}' col tasto sinistro"

    def _cambia_colore_zona(self):
        """Apre un popup con la palette per scegliere il nuovo colore."""
        z = self._get_selected_zone()
        if z is None:
            # Messaggio di stato mostrato all'utente nel pannello
            self.auto_status_msg = "Seleziona una zona dalla lista"
            return
        self._show_color_picker(z)

    def _forza_adattamento_zona(self):
        """Prende la zona selezionata e la modella sulla mappa attuale."""
        z = self._get_selected_zone()
        if z is None:
            # Messaggio di stato mostrato all'utente nel pannello
            self.auto_status_msg = "Seleziona una zona"
            return
        
        nuovi_punti = self._adatta_punti_alla_mappa(z['punti'])
        self.zone_mgr.aggiorna_forma(z['id'], nuovi_punti)
        # Messaggio di stato mostrato all'utente nel pannello
        self.auto_status_msg = f"Forma di '{z['nome']}' ottimizzata"

    def _rinomina_zona(self):
        """Rinomina zona."""
        z = self._get_selected_zone()
        if z is None:
            # Messaggio di stato mostrato all'utente nel pannello
            self.auto_status_msg = "Seleziona una zona dalla lista"
            return
        def on_name(nuovo):
            """Callback di input del nome."""
            if nuovo:
                self.zone_mgr.rinomina(z['id'], nuovo)
                self._refresh_zone_list()
                # Messaggio di stato mostrato all'utente nel pannello
                self.auto_status_msg = f"Zona rinominata in '{nuovo}'"
        self._show_text_input("Rinomina Zona", z['nome'], on_name)

    def _elimina_zona(self):
        """Elimina zona."""
        z = self._get_selected_zone()
        if z is None:
            # Messaggio di stato mostrato all'utente nel pannello
            self.auto_status_msg = "Seleziona una zona dalla lista"
            return
        nome = z['nome']
        id_zona = z['id']
        def on_confirm(yes):
            """Callback di conferma."""
            if yes:
                # Rimuove la zona dal registro
                self.zone_mgr.rimuovi(id_zona)
                self._refresh_zone_list()
                # Messaggio di stato mostrato all'utente nel pannello
                self.auto_status_msg = f"Zona '{nome}' eliminata"
        self._show_confirm(f"Eliminare la zona '{nome}' ?", on_confirm)

    def _zona_alla_posizione(self, x, y):
        """
        Ritorna la zona (dict) in cui cade il punto (x, y).
        Se il punto e' fuori dai confini, calcola e restituisce la zona piu' vicina.
        """
        if not self.zone_mgr.zone:
            return None

        # 1. Controllo geometrico: il punto e' esattamente dentro un poligono?
        for z in self.zone_mgr.zone:
            if self._is_point_in_polygon(x, y, z['punti']):
                return z

        # 2. Fallback: se sei fuori dai poligoni, trova la zona piu' vicina tramite centroide
        zona_piu_vicina = None
        dist_minima = float('inf')

        for z in self.zone_mgr.zone:
            cx, cy = ZoneManager.centroide(z)
            dist = math.hypot(x - cx, y - cy)
            if dist < dist_minima:
                dist_minima = dist
                zona_piu_vicina = z

        return zona_piu_vicina

    def _adatta_punti_alla_mappa(self, punti_originali):
        """Sposta i punti del poligono sulle celle calpestabili piu' vicine."""
        punti_adattati = []
        for px, py in punti_originali:
            # Cerca la cella calpestabile piu' vicina al punto disegnato a mano
            cella_vicina = self.pathfinder.nearest_walkable(px, py, radius=10)
            if cella_vicina:
                gx, gy = self.pathfinder._coord(cella_vicina)
                punti_adattati.append([gx, gy])
            else:
                # Se e' troppo lontano da zone conosciute, tieni il punto originale
                punti_adattati.append([px, py])
        
        # Rimuove duplicati consecutivi che potrebbero crearsi con lo snap
        risultato = []
        for p in punti_adattati:
            if not risultato or (p[0] != risultato[-1][0] or p[1] != risultato[-1][1]):
                risultato.append(p)
        return risultato
