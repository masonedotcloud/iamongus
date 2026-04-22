"""
Popup secondari: nuova fase, nuovo alternativo, link zona di gioco.

Mixin di GPSVisualizerPro.
"""

from ._imports import *


class TasksPopupsSubitemMixin:
    """Mixin con i metodi di tasks popups subitem di GPSVisualizerPro."""
    def _apri_popup_nuova_fase(self):
        """
        Apre il popup di creazione di una nuova fase per la task selezionata.

        Una "fase" e' un waypoint intermedio del percorso della task: un
        punto della mappa dove il bot si ferma per eseguire un sotto-step
        (es. un button da premere) prima del minigioco vero. La fase
        viene aggiunta in coda alla lista ``fasi`` della task.
        """
        t = self._get_selected_reg_task()
        if t is None:
            self.auto_status_msg = "Seleziona una task a cui aggiungere una fase"
            return
        tag = "popup_nuova_fase"
        if dpg.does_item_exist(tag):
            dpg.delete_item(tag)
        px, py = self.pos_target
        vp_w = dpg.get_viewport_client_width()
        vp_h = dpg.get_viewport_client_height()
        id_t = t['id']

        def do_salva(*_):
            """Callback del bottone Salva del popup."""
            nome_v = dpg.get_value("nf_nome").strip()
            x_v = dpg.get_value("nf_x")
            y_v = dpg.get_value("nf_y")
            if not nome_v:
                return
            # Aggiunge una fase intermedia alla task
            self.task_mgr.aggiungi_fase(id_t, nome_v, x_v, y_v)
            self._refresh_reg_task_listbox()
            self.auto_status_msg = f"Fase '{nome_v}' aggiunta a [{id_t}]"
            if dpg.does_item_exist(tag):
                dpg.delete_item(tag)

        def do_usa_pos(*_):
            """Callback del bottone \"Usa posizione attuale\"."""
            dpg.set_value("nf_x", round(self.pos_target[0], 3))
            dpg.set_value("nf_y", round(self.pos_target[1], 3))

        with dpg.window(label=f"Nuova Fase per [{id_t}] {t['nome']}", tag=tag,
                        modal=True, no_resize=True, no_collapse=True,
                        width=360, height=210,
                        pos=(max(0, vp_w // 2 - 180), max(0, vp_h // 2 - 105))):
            dpg.add_text("Nome fase (es. 'Parte 2 - Console'):")
            dpg.add_input_text(tag="nf_nome", width=-1)
            dpg.add_spacer(height=4)
            dpg.add_text("Coordinate posizione fase:")
            with dpg.group(horizontal=True):
                dpg.add_text("X:"); dpg.add_input_float(tag="nf_x", default_value=round(px, 3), width=140, step=0)
                dpg.add_text("Y:"); dpg.add_input_float(tag="nf_y", default_value=round(py, 3), width=140, step=0)
            dpg.add_button(label="Usa posizione attuale", width=-1, callback=do_usa_pos)
            dpg.add_spacer(height=6)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Aggiungi fase", width=170, callback=do_salva)
                dpg.add_button(label="Annulla", width=170,
                               callback=lambda *a: dpg.delete_item(tag) if dpg.does_item_exist(tag) else None)

    def _apri_popup_nuovo_alternativo(self):
        """Apre il popup nuovo alternativo."""
        t = self._get_selected_reg_task()
        if t is None:
            self.auto_status_msg = "Seleziona una task a cui aggiungere un alternativo"
            return
        tag = "popup_nuovo_alternativo"
        if dpg.does_item_exist(tag):
            dpg.delete_item(tag)
        px, py = self.pos_target
        vp_w = dpg.get_viewport_client_width()
        vp_h = dpg.get_viewport_client_height()
        id_t = t['id']

        def do_salva(*_):
            """Callback del bottone Salva del popup."""
            x_v = dpg.get_value("nfr_x")
            y_v = dpg.get_value("nfr_y")
            # Aggiunge un punto alternativo alla task
            self.task_mgr.aggiungi_alternativo(id_t, x_v, y_v)
            self._refresh_reg_task_listbox()
            self.auto_status_msg = f"Alternativo aggiunto a [{id_t}]"
            if dpg.does_item_exist(tag):
                dpg.delete_item(tag)

        def do_usa_pos(*_):
            """Callback del bottone \"Usa posizione attuale\"."""
            dpg.set_value("nfr_x", round(self.pos_target[0], 3))
            dpg.set_value("nfr_y", round(self.pos_target[1], 3))

        with dpg.window(label=f"Nuovo Alternativo per [{id_t}] {t['nome']}", tag=tag,
                        modal=True, no_resize=True, no_collapse=True,
                        width=360, height=170,
                        pos=(max(0, vp_w // 2 - 180), max(0, vp_h // 2 - 85))):
            dpg.add_text("Coordinate posizione alternativa:")
            with dpg.group(horizontal=True):
                dpg.add_text("X:"); dpg.add_input_float(tag="nfr_x", default_value=round(px, 3), width=140, step=0)
                dpg.add_text("Y:"); dpg.add_input_float(tag="nfr_y", default_value=round(py, 3), width=140, step=0)
            dpg.add_button(label="Usa posizione attuale", width=-1, callback=do_usa_pos)
            dpg.add_spacer(height=6)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Aggiungi alternativo", width=170, callback=do_salva)
                dpg.add_button(label="Annulla", width=170,
                               callback=lambda *a: dpg.delete_item(tag) if dpg.does_item_exist(tag) else None)

    def _imposta_game_zone_id(self):
        """Popup per inserire manualmente il game_zone_id sulla zona selezionata."""
        z = self._get_selected_zone()
        if z is None:
            self.auto_status_msg = "Seleziona una zona dalla lista"
            return

        tag = "popup_game_zone_id"
        if dpg.does_item_exist(tag):
            dpg.delete_item(tag)

        vp_w = dpg.get_viewport_client_width()
        vp_h = dpg.get_viewport_client_height()
        id_zona    = z['id']
        nome_zona  = z['nome']
        curr_gzid  = z.get('game_zone_id', None)

        def do_salva(*_):
            """Callback del bottone Salva del popup."""
            raw = dpg.get_value("gzid_input").strip()
            if raw == "":
                self.zone_mgr.set_game_zone_id(id_zona, None)
                self.auto_status_msg = f"ID rimosso da '{nome_zona}'"
            else:
                try:
                    gzid = int(raw)
                    # Controlla unicita'
                    esistente = self.zone_mgr.get_by_game_zone_id(gzid)
                    if esistente and esistente['id'] != id_zona:
                        self.auto_status_msg = (f"GZ:{gzid} già usato da "
                                                f"'{esistente['nome']}' - scegli un altro")
                        return
                    self.zone_mgr.set_game_zone_id(id_zona, gzid)
                    self._refresh_zone_list()
                    self._refresh_reg_task_listbox()   # aggiorna label zone nei task
                    self.auto_status_msg = f"'{nome_zona}' -> GZ:{gzid}"
                except ValueError:
                    self.auto_status_msg = "Inserisci un numero intero"
                    return
            self._refresh_zone_list()
            self._refresh_reg_task_listbox()
            if dpg.does_item_exist(tag):
                dpg.delete_item(tag)

        default_txt = str(curr_gzid) if curr_gzid is not None else ""
        hint_txt    = f"Attuale: GZ:{curr_gzid}" if curr_gzid is not None else "Nessun ID impostato"

        with dpg.window(label=f"ID Zona Gioco - {nome_zona}", tag=tag,
                        modal=True, no_resize=True, no_collapse=True,
                        width=360, height=165,
                        pos=(max(0, vp_w // 2 - 180), max(0, vp_h // 2 - 82))):
            dpg.add_text(hint_txt, color=Colors.TEXT_DIM)
            dpg.add_text("Nuovo game_zone_id  (vuoto = rimuovi):")
            dpg.add_input_text(tag="gzid_input", default_value=default_txt,
                               width=-1, on_enter=True, callback=do_salva)
            dpg.add_spacer(height=6)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Salva", width=170, callback=do_salva)
                dpg.add_button(label="Annulla", width=170,
                               callback=lambda *a: dpg.delete_item(tag)
                               if dpg.does_item_exist(tag) else None)

    def _apri_popup_collegamento_zona(self):
        """Popup per linkare/slinkare una task registrata a una zona tramite game_zone_id."""
        t = self._get_selected_reg_task()
        if t is None:
            self.auto_status_msg = "Seleziona una task registrata"
            return

        tag = "popup_link_zona"
        if dpg.does_item_exist(tag):
            dpg.delete_item(tag)

        vp_w    = dpg.get_viewport_client_width()
        vp_h    = dpg.get_viewport_client_height()
        id_task = t['id']
        nome_t  = t['nome']
        curr_zid = t.get('id_zona', None)

        # Costruisce la lista delle zone che hanno un game_zone_id
        zone_con_id = [(z['nome'], z.get('game_zone_id'))
                       for z in self.zone_mgr.zone if z.get('game_zone_id') is not None]
        zone_con_id.sort(key=lambda x: x[1])

        def do_salva(*_):
            """Callback del bottone Salva del popup."""
            raw = dpg.get_value("lz_input").strip()
            if raw == "" or raw.lower() == "nessuna":
                # Collega la task alla zona di gioco selezionata
                self.task_mgr.imposta_collegamento_zona(id_task, None)
                self.auto_status_msg = f"Link zona rimosso da '{nome_t}'"
            else:
                try:
                    gzid = int(raw)
                    # Collega la task alla zona di gioco selezionata
                    self.task_mgr.imposta_collegamento_zona(id_task, gzid)
                    z = self.zone_mgr.get_by_game_zone_id(gzid)
                    z_nome = z['nome'] if z else "?"
                    self.auto_status_msg = f"'{nome_t}' -> zona '{z_nome}' (GZ:{gzid})"
                except ValueError:
                    self.auto_status_msg = "Inserisci un numero intero o lascia vuoto"
                    return
            self._refresh_reg_task_listbox()
            if dpg.does_item_exist(tag):
                dpg.delete_item(tag)

        curr_str  = f"GZ:{curr_zid}" if curr_zid is not None else "Nessuna"
        curr_zona = self.zone_mgr.get_by_game_zone_id(curr_zid) if curr_zid is not None else None
        curr_desc = (f"  ({curr_zona['nome']})" if curr_zona else "") if curr_zid is not None else ""

        win_h = 180 + min(len(zone_con_id), 8) * 18
        with dpg.window(label=f"Link Zona <-> '{nome_t}'", tag=tag,
                        modal=True, no_resize=True, no_collapse=True,
                        width=380, height=win_h,
                        pos=(max(0, vp_w // 2 - 190), max(0, vp_h // 2 - win_h // 2))):
            dpg.add_text(f"Link attuale: {curr_str}{curr_desc}", color=Colors.TEXT_DIM)
            dpg.add_spacer(height=4)

            if zone_con_id:
                dpg.add_text("Zone disponibili (GZ:ID - Nome):", color=Colors.TEXT_DIM)
                for z_nome, z_gzid in zone_con_id:
                    marker = " < attuale" if z_gzid == curr_zid else ""
                    dpg.add_text(f"  GZ:{z_gzid} - {z_nome}{marker}",
                                 color=Colors.ACCENT if z_gzid == curr_zid else Colors.TEXT)
            else:
                dpg.add_text("Nessuna zona ha ancora un game_zone_id.",
                             color=(220, 120, 30, 255))
                dpg.add_text("Impostalo prima con 'Imposta ID Zona Gioco'.",
                             color=Colors.TEXT_DIM)

            dpg.add_spacer(height=6)
            dpg.add_text("Inserisci GZ:ID da linkare  (vuoto = rimuovi link):")
            default_lz = str(curr_zid) if curr_zid is not None else ""
            dpg.add_input_text(tag="lz_input", default_value=default_lz,
                               width=-1, on_enter=True, callback=do_salva)
            dpg.add_spacer(height=6)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Salva", width=185, callback=do_salva)
                dpg.add_button(label="Annulla", width=185,
                               callback=lambda *a: dpg.delete_item(tag)
                               if dpg.does_item_exist(tag) else None)
