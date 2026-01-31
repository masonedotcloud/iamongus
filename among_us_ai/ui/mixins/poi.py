"""
Punti di interesse (POI): UI, navigazione e popup.

Mixin di GPSVisualizerPro: metodi separati per organizzazione, ma
condividono lo stato self.* della classe principale.
"""

from ._imports import *



class PoiMixin:
    """Mixin con i metodi di poi di GPSVisualizerPro."""
    def _refresh_poi_listbox(self):
        """Aggiorna poi listbox."""
        items = []
        # Itera tutti i POI
        for p in self.poi_mgr.poi_list:
            zona_str = f"  [{p['nome_zona']}]" if p.get('nome_zona') else ""
            items.append(f"[{p['id']:02d}] {p['nome']}{zona_str}")
        # Verifica se l'elemento DPG e' gia' stato creato
        if dpg.does_item_exist("poi_listbox"):
            # Cambia le configurazioni di un widget gia' creato
            dpg.configure_item("poi_listbox", items=items)

    def _get_selected_poi(self):
        """Ritorna selected poi."""
        if not self.poi_mgr.poi_list:
            return None
        # Verifica se l'elemento DPG e' gia' stato creato
        if not dpg.does_item_exist("poi_listbox"):
            return None
        sel = dpg.get_value("poi_listbox")
        if not sel:
            return None
        try:
            id_num = int(sel.split(']')[0].lstrip('[').strip())
            return self.poi_mgr.get_by_id(id_num)
        except (ValueError, IndexError):
            return None

    def _naviga_a_poi(self):
        """Avvia la navigazione A* verso poi."""
        p = self._get_selected_poi()
        if p is None:
            # Messaggio di stato mostrato all'utente nel pannello
            self.auto_status_msg = "Seleziona un POI dalla lista"
            return
        if not self.auto_enabled:
            self.auto_enabled = True
            # Verifica se l'elemento DPG e' gia' stato creato
            if dpg.does_item_exist("auto_checkbox"):
                # Aggiorna il valore di un widget DPG
                dpg.set_value("auto_checkbox", True)
        self._plan_path((p['x'], p['y']))
        # Messaggio di stato mostrato all'utente nel pannello
        self.auto_status_msg = f"Navigo verso POI '{p['nome']}'"

    def _elimina_poi(self):
        """Elimina poi."""
        p = self._get_selected_poi()
        if p is None:
            # Messaggio di stato mostrato all'utente nel pannello
            self.auto_status_msg = "Seleziona un POI da eliminare"
            return
        nome  = p['nome']
        id_p  = p['id']
        def on_confirm(yes):
            """Callback di conferma."""
            if yes:
                # Rimuove il POI dal registro
                self.poi_mgr.rimuovi(id_p)
                self._refresh_poi_listbox()
                # Messaggio di stato mostrato all'utente nel pannello
                self.auto_status_msg = f"POI '{nome}' eliminato"
        self._show_confirm(f"Eliminare il POI '{nome}'?", on_confirm)

    def _apri_popup_nuovo_poi(self):
        """Apre il popup nuovo poi."""
        tag = "popup_nuovo_poi"
        # Verifica se l'elemento DPG e' gia' stato creato
        if dpg.does_item_exist(tag):
            # Rimuove l'elemento DPG (cleanup)
            dpg.delete_item(tag)
        px, py = self.pos_target
        vp_w   = dpg.get_viewport_client_width()
        vp_h   = dpg.get_viewport_client_height()

        zona_now  = self._zona_alla_posizione(px, py)
        gz_id_now = zona_now.get('game_zone_id') if zona_now else None
        zl_id_now = zona_now['id']               if zona_now else None
        if zona_now:
            gz_str    = f"  GZ:{gz_id_now}" if gz_id_now is not None else ""
            zona_info = f"[{zl_id_now:02d}] {zona_now['nome']}{gz_str}"
            col_zona  = Colors.ACCENT
        else:
            zona_info = "Fuori da qualsiasi zona"
            col_zona  = (200, 120, 30, 255)

        def do_salva(*_):
            """Callback del bottone Salva del popup."""
            nome_v = dpg.get_value("np_nome").strip()
            x_v    = dpg.get_value("np_x")
            y_v    = dpg.get_value("np_y")
            if not nome_v:
                return
            zona_s  = self._zona_alla_posizione(x_v, y_v) or zona_now
            gz_id_s = zona_s.get('game_zone_id') if zona_s else gz_id_now
            zl_id_s = zona_s['id']               if zona_s else zl_id_now
            # Aggiunge un nuovo POI
            self.poi_mgr.aggiungi(
                nome_v, x_v, y_v,
                id_zona       = gz_id_s,
                id_zona_locale = zl_id_s,
                nome_zona     = zona_s['nome'] if zona_s else None,
            )
            self._refresh_poi_listbox()
            # Messaggio di stato mostrato all'utente nel pannello
            self.auto_status_msg = f"POI '{nome_v}' aggiunto"
            # Verifica se l'elemento DPG e' gia' stato creato
            if dpg.does_item_exist(tag):
                # Rimuove l'elemento DPG (cleanup)
                dpg.delete_item(tag)

        def do_usa_pos(*_):
            """Callback del bottone \"Usa posizione attuale\"."""
            nx = round(self.pos_target[0], 3)
            ny = round(self.pos_target[1], 3)
            # Aggiorna il valore di un widget DPG
            dpg.set_value("np_x", nx)
            # Aggiorna il valore di un widget DPG
            dpg.set_value("np_y", ny)
            z2 = self._zona_alla_posizione(nx, ny)
            if z2:
                gz2   = z2.get('game_zone_id')
                info2 = f"[{z2['id']:02d}] {z2['nome']}" + (f"  GZ:{gz2}" if gz2 is not None else "")
            else:
                info2 = "Fuori da qualsiasi zona"
            # Verifica se l'elemento DPG e' gia' stato creato
            if dpg.does_item_exist("np_zona_info"):
                # Aggiorna il valore di un widget DPG
                dpg.set_value("np_zona_info", info2)

        # Apre la finestra
        with dpg.window(label="Nuovo Punto di Interesse", tag=tag,
                        modal=True, no_resize=True, no_collapse=True,
                        width=400, height=220,
                        pos=(max(0, vp_w // 2 - 200), max(0, vp_h // 2 - 110))):
            dpg.add_text("Zona rilevata automaticamente:", color=Colors.TEXT_DIM)
            dpg.add_text(zona_info, tag="np_zona_info", color=col_zona)
            dpg.add_separator()
            dpg.add_text("Nome:")
            dpg.add_input_text(tag="np_nome", default_value="", width=-1)
            dpg.add_spacer(height=4)
            dpg.add_text("Coordinate:")
            with dpg.group(horizontal=True):
                dpg.add_text("X:")
                dpg.add_input_float(tag="np_x", default_value=round(px, 3), width=155, step=0)
                dpg.add_text("Y:")
                dpg.add_input_float(tag="np_y", default_value=round(py, 3), width=155, step=0)
            dpg.add_button(label="Usa posizione attuale  (aggiorna zona)", width=-1,
                           callback=do_usa_pos)
            dpg.add_spacer(height=6)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Salva", width=190, callback=do_salva)
                dpg.add_button(label="Annulla", width=190,
                               # Rimuove l'elemento DPG (cleanup)
                               callback=lambda *a: dpg.delete_item(tag)
                               # Verifica se l'elemento DPG e' gia' stato creato
                               if dpg.does_item_exist(tag) else None)

    def _apri_popup_modifica_poi(self):
        """Apre il popup modifica poi."""
        p = self._get_selected_poi()
        if p is None:
            # Messaggio di stato mostrato all'utente nel pannello
            self.auto_status_msg = "Seleziona un POI da modificare"
            return
        tag  = "popup_modifica_poi"
        # Verifica se l'elemento DPG e' gia' stato creato
        if dpg.does_item_exist(tag):
            # Rimuove l'elemento DPG (cleanup)
            dpg.delete_item(tag)
        id_p = p['id']
        vp_w = dpg.get_viewport_client_width()
        vp_h = dpg.get_viewport_client_height()

        zona_now = self._zona_alla_posizione(p['x'], p['y'])
        if zona_now:
            gz2      = zona_now.get('game_zone_id')
            zona_info = f"[{zona_now['id']:02d}] {zona_now['nome']}" + (f"  GZ:{gz2}" if gz2 is not None else "")
            col_zona  = Colors.ACCENT
        else:
            zona_info = p.get('nome_zona') or "Fuori da qualsiasi zona"
            col_zona  = (200, 120, 30, 255)

        def do_salva(*_):
            """Callback del bottone Salva del popup."""
            nome_v = dpg.get_value("mp_nome").strip()
            x_v    = dpg.get_value("mp_x")
            y_v    = dpg.get_value("mp_y")
            if not nome_v:
                return
            zona_s  = self._zona_alla_posizione(x_v, y_v) or zona_now
            gz_id_s = zona_s.get('game_zone_id') if zona_s else None
            zl_id_s = zona_s['id']               if zona_s else None
            # Aggiorna i dati del POI
            self.poi_mgr.aggiorna(
                id_p, nome_v, x_v, y_v,
                id_zona       = gz_id_s,
                id_zona_locale = zl_id_s,
                nome_zona     = zona_s['nome'] if zona_s else None,
            )
            self._refresh_poi_listbox()
            # Messaggio di stato mostrato all'utente nel pannello
            self.auto_status_msg = f"POI [{id_p}] aggiornato"
            # Verifica se l'elemento DPG e' gia' stato creato
            if dpg.does_item_exist(tag):
                # Rimuove l'elemento DPG (cleanup)
                dpg.delete_item(tag)

        def do_usa_pos(*_):
            """Callback del bottone \"Usa posizione attuale\"."""
            nx = round(self.pos_target[0], 3)
            ny = round(self.pos_target[1], 3)
            # Aggiorna il valore di un widget DPG
            dpg.set_value("mp_x", nx)
            # Aggiorna il valore di un widget DPG
            dpg.set_value("mp_y", ny)
            z2 = self._zona_alla_posizione(nx, ny)
            if z2:
                gz2   = z2.get('game_zone_id')
                info2 = f"[{z2['id']:02d}] {z2['nome']}" + (f"  GZ:{gz2}" if gz2 is not None else "")
            else:
                info2 = "Fuori da qualsiasi zona"
            # Verifica se l'elemento DPG e' gia' stato creato
            if dpg.does_item_exist("mp_zona_info"):
                # Aggiorna il valore di un widget DPG
                dpg.set_value("mp_zona_info", info2)

        with dpg.window(label=f"Modifica POI [{id_p}]", tag=tag,
                        modal=True, no_resize=True, no_collapse=True,
                        width=400, height=220,
                        pos=(max(0, vp_w // 2 - 200), max(0, vp_h // 2 - 110))):
            dpg.add_text("Zona rilevata:", color=Colors.TEXT_DIM)
            dpg.add_text(zona_info, tag="mp_zona_info", color=col_zona)
            dpg.add_separator()
            dpg.add_text("Nome:")
            dpg.add_input_text(tag="mp_nome", default_value=p['nome'], width=-1)
            dpg.add_spacer(height=4)
            dpg.add_text("Coordinate:")
            with dpg.group(horizontal=True):
                dpg.add_text("X:")
                dpg.add_input_float(tag="mp_x", default_value=p['x'], width=155, step=0)
                dpg.add_text("Y:")
                dpg.add_input_float(tag="mp_y", default_value=p['y'], width=155, step=0)
            dpg.add_button(label="Usa posizione attuale  (aggiorna zona)", width=-1,
                           callback=do_usa_pos)
            dpg.add_spacer(height=6)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Salva", width=190, callback=do_salva)
                dpg.add_button(label="Annulla", width=190,
                               # Rimuove l'elemento DPG (cleanup)
                               callback=lambda *a: dpg.delete_item(tag)
                               # Verifica se l'elemento DPG e' gia' stato creato
                               if dpg.does_item_exist(tag) else None)
