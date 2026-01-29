"""
Dialoghi modali generici: text input, confirm, color picker, help.

Mixin di GPSVisualizerPro: metodi separati per organizzazione, ma
condividono lo stato self.* della classe principale.
"""

from ._imports import *



class DialogsMixin:
    """Mixin con i metodi di dialogs di GPSVisualizerPro."""
    def _show_text_input(self, title, default_text, callback):
        """Mostra un popup modale per inserimento testo. callback(str|None)."""
        tag = "text_input_popup"
        # Verifica se l'elemento DPG e' gia' stato creato
        if dpg.does_item_exist(tag):
            # Rimuove l'elemento DPG (cleanup)
            dpg.delete_item(tag)

        def do_ok(*_):
            """Callback del pulsante OK."""
            # Verifica se l'elemento DPG e' gia' stato creato
            if not dpg.does_item_exist(f"{tag}_input"):
                callback(None)
                return
            value = dpg.get_value(f"{tag}_input")
            # Verifica se l'elemento DPG e' gia' stato creato
            if dpg.does_item_exist(tag):
                # Rimuove l'elemento DPG (cleanup)
                dpg.delete_item(tag)
            if value and value.strip():
                callback(value.strip())
            else:
                callback(None)

        def do_cancel(*_):
            """Callback del pulsante Annulla."""
            # Verifica se l'elemento DPG e' gia' stato creato
            if dpg.does_item_exist(tag):
                # Rimuove l'elemento DPG (cleanup)
                dpg.delete_item(tag)
            callback(None)

        vp_w = dpg.get_viewport_client_width()
        vp_h = dpg.get_viewport_client_height()
        with dpg.window(label=title, tag=tag, modal=True, no_resize=True,
                        no_collapse=True,
                        width=340, height=135,
                        pos=(max(0, vp_w // 2 - 170),
                             max(0, vp_h // 2 - 68))):
            dpg.add_input_text(tag=f"{tag}_input",
                               default_value=default_text or "",
                               width=-1, on_enter=True,
                               callback=do_ok)
            dpg.add_spacer(height=4)
            with dpg.group(horizontal=True):
                dpg.add_button(label="OK",      width=155, callback=do_ok)
                dpg.add_button(label="Annulla", width=155, callback=do_cancel)

        try:
            dpg.focus_item(f"{tag}_input")
        except Exception:
            pass

    def _show_confirm(self, message, callback):
        """Mostra un popup modale di conferma. callback(bool)."""
        tag = "confirm_popup"
        # Verifica se l'elemento DPG e' gia' stato creato
        if dpg.does_item_exist(tag):
            # Rimuove l'elemento DPG (cleanup)
            dpg.delete_item(tag)

        def do_yes(*_):
            """Callback del pulsante Si."""
            # Verifica se l'elemento DPG e' gia' stato creato
            if dpg.does_item_exist(tag):
                # Rimuove l'elemento DPG (cleanup)
                dpg.delete_item(tag)
            callback(True)

        def do_no(*_):
            """Callback del pulsante No."""
            # Verifica se l'elemento DPG e' gia' stato creato
            if dpg.does_item_exist(tag):
                # Rimuove l'elemento DPG (cleanup)
                dpg.delete_item(tag)
            callback(False)

        vp_w = dpg.get_viewport_client_width()
        vp_h = dpg.get_viewport_client_height()
        # Apre la finestra
        with dpg.window(label="Conferma", tag=tag, modal=True, no_resize=True,
                        no_collapse=True,
                        width=340, height=115,
                        pos=(max(0, vp_w // 2 - 170),
                             max(0, vp_h // 2 - 57))):
            dpg.add_text(message)
            dpg.add_spacer(height=6)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Si",  width=155, callback=do_yes)
                dpg.add_button(label="No",  width=155, callback=do_no)

    def _show_color_picker(self, zona):
        """Popup con la palette: clicca un colore per applicarlo alla zona."""
        tag = "color_picker_popup"
        # Verifica se l'elemento DPG e' gia' stato creato
        if dpg.does_item_exist(tag):
            # Rimuove l'elemento DPG (cleanup)
            dpg.delete_item(tag)

        def pick(col_hex):
            """Callback selezione colore dalla palette."""
            self.zone_mgr.cambia_colore(zona['id'], col_hex)
            self._refresh_zone_list()
            # Messaggio di stato mostrato all'utente nel pannello
            self.auto_status_msg = f"Colore di '{zona['nome']}' aggiornato"
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

        with dpg.window(label=f"Colore: {zona['nome']}", tag=tag, modal=True,
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
                        # Tema per colorare il bottone
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
                           callback=lambda *a: dpg.delete_item(tag)
                                                # Verifica se l'elemento DPG e' gia' stato creato
                                                if dpg.does_item_exist(tag) else None)

    def _show_help(self):
        """Mostra help."""
        # Verifica se l'elemento DPG e' gia' stato creato
        if dpg.does_item_exist("help_win"):
            dpg.show_item("help_win"); return
        # Apre la finestra
        with dpg.window(label="Informazioni", tag="help_win",
                        width=520, height=470, pos=(180, 130)):
            dpg.add_text("Among Us AI Bot", color=Colors.ACCENT)
            dpg.add_separator()
            dpg.add_text("Mouse:")
            dpg.add_text("  Sinistro   = destinazione con pathfinding A*",
                         color=Colors.TEXT_DIM)
            dpg.add_text("  Destro     = annulla destinazione",
                         color=Colors.TEXT_DIM)
            dpg.add_text("  Rotella (drag) = sposta la mappa", color=Colors.TEXT_DIM)
            dpg.add_text("  Rotella (scroll) = zoom", color=Colors.TEXT_DIM)
            dpg.add_separator()
            dpg.add_text("Tastiera:")
            dpg.add_text("  F / R / O = telecamera", color=Colors.TEXT_DIM)
            dpg.add_text("  G / T / C / H / P = toggle layers",
                         color=Colors.TEXT_DIM)
            dpg.add_text("  M = abilita / disabilita auto-move",
                         color=Colors.TEXT_DIM)
            dpg.add_text("  F4 / FINE (END) = ferma esecuzione task",
                         color=Colors.TEXT_DIM)
            dpg.add_text("  ESC = annulla", color=Colors.TEXT_DIM)
            dpg.add_separator()
            dpg.add_text("Pathfinding:", color=Colors.TARGET)
            dpg.add_text("A* lavora sulle celle gia' visitate del mapper.",
                         color=Colors.TEXT_DIM)
            dpg.add_text("Piu' la mappa e' completa, piu' il percorso e' ottimale.",
                         color=Colors.TEXT_DIM)
            dpg.add_text("Il path viene semplificato con 'string-pulling'.",
                         color=Colors.TEXT_DIM)
            dpg.add_text("Se il player resta fermo >0.8s, si fa replan.",
                         color=Colors.TEXT_DIM)
            dpg.add_text("Se la mappa ha buchi, dilate +1 cella li tappa.",
                         color=Colors.TEXT_DIM)
