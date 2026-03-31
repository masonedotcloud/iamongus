"""
Costruzione interfaccia DPG: viewport, pannello laterale, tema.

Mixin di GPSVisualizerPro: metodi separati per organizzazione, ma
condividono lo stato self.* della classe principale.
"""

from ._imports import *



class UISetupMixin:
    """Mixin con i metodi di u i setup di GPSVisualizerPro."""
    def _setup_interfaccia(self):
        """Inizializza interfaccia."""
        dpg.create_context()
        self._setup_theme()

        with dpg.window(tag="main_win", no_title_bar=True, no_resize=True,
                        no_move=True,
                        no_scrollbar=True, no_scroll_with_mouse=True,
                        no_bring_to_front_on_focus=True):

            # Barra dei menu in cima alla finestra
            with dpg.menu_bar():
                # Menu
                with dpg.menu(label="File"):
                    dpg.add_menu_item(label="Ricarica mappa",
                        callback=lambda *a: self._ricarica_mappa())
                    dpg.add_menu_item(label="Esporta trail JSON",
                        callback=lambda *a: self._esporta_trail())
                    dpg.add_separator()
                    dpg.add_menu_item(label="Esporta tutto  (ZIP + PNG mappa)",
                        callback=lambda *a: self._esporta_tutto())
                    dpg.add_separator()
                    dpg.add_menu_item(label="Esci",
                        callback=lambda *a: dpg.stop_dearpygui())
                # Menu
                with dpg.menu(label="Vista"):
                    dpg.add_menu_item(label="Segui giocatore   [F]",
                        callback=lambda *a: self._set_camera("follow"))
                    dpg.add_menu_item(label="Telecamera libera [R]",
                        callback=lambda *a: self._set_camera("free"))
                    dpg.add_menu_item(label="Panoramica mappa  [O]",
                        callback=lambda *a: self._set_camera("overview"))
                    dpg.add_separator()
                    dpg.add_menu_item(label="Reset zoom",
                        callback=lambda *a: self._reset_view())
                # Menu
                with dpg.menu(label="Auto-move"):
                    dpg.add_menu_item(label="Abilita / Disabilita [M]",
                        callback=lambda *a: self._toggle_auto_enabled())
                    dpg.add_menu_item(label="Annulla [ESC]",
                        callback=lambda *a: self._cancel_auto_move())
                # Menu
                with dpg.menu(label="Strumenti"):
                    dpg.add_menu_item(label="Cancella trail",
                        callback=lambda *a: self._clear_trail())
                    dpg.add_menu_item(label="Reset statistiche",
                        callback=lambda *a: self._reset_distance())
                    dpg.add_separator()
                    dpg.add_menu_item(label="Calibra pulsante 'Use'...",
                        callback=lambda *a: self._apri_popup_calibra_use_button())
                    dpg.add_separator()
                    dpg.add_menu_item(label="Preview giro Auto-All (F1)",
                        callback=lambda *a: self._toggle_preview_giro())
                    dpg.add_menu_item(label="Come scegliere le task...",
                        callback=lambda *a: self._apri_popup_pesi_pianificatore())
                # Menu
                with dpg.menu(label="?"):
                    dpg.add_menu_item(label="Info e scorciatoie",
                        callback=lambda *a: self._show_help())

            with dpg.group(horizontal=True):
                with dpg.child_window(tag="canvas_container",
                                      width=-GPSConfig.SIDE_PANEL_W,
                                      height=-GPSConfig.STATUS_BAR_H,
                                      border=False, no_scrollbar=True):
                    with dpg.drawlist(tag="canvas",
                                      width=self.canvas_w,
                                      height=self.canvas_h):
                        with dpg.draw_node(tag="grid_node"):   pass
                        with dpg.draw_node(tag="map_node"):
                            step_u = GPSConfig.CELL_STEP
                            for kx, ky in self.visitati_coords:
                                dpg.draw_rectangle(
                                    (kx, -ky), (kx + step_u, -ky + step_u),
                                    color=Colors.VISITED, fill=Colors.VISITED)
                        with dpg.draw_node(tag="zone_node"):   pass
                        with dpg.draw_node(tag="task_node"):   pass
                        with dpg.draw_node(tag="poi_node"):    pass
                        with dpg.draw_node(tag="trail_node"):  pass
                        with dpg.draw_node(tag="path_node"):   pass
                        with dpg.draw_node(tag="target_node"): pass
                        with dpg.draw_node(tag="other_players_node"): pass
                        with dpg.draw_node(tag="doors_node"): pass
                        with dpg.draw_node(tag="player_node"): pass
                        # Sopra a tutto: preview del giro Auto-All (F1)
                        with dpg.draw_node(tag="giro_preview_node"): pass
                        with dpg.draw_node(tag="hud_node"):    pass

                with dpg.child_window(tag="side_panel",
                                      width=GPSConfig.SIDE_PANEL_W - 10,
                                      height=-GPSConfig.STATUS_BAR_H,
                                      border=False):
                    self._costruisci_pannello()

            with dpg.child_window(tag="status_bar",
                                  height=GPSConfig.STATUS_BAR_H,
                                  border=False, no_scrollbar=True):
                with dpg.group(horizontal=True):
                    dpg.add_text("X: 0.00", tag="status_x", color=Colors.ACCENT)
                    dpg.add_text("|", color=Colors.TEXT_DIM)
                    dpg.add_text("Y: 0.00", tag="status_y", color=Colors.ACCENT)
                    dpg.add_text("|", color=Colors.TEXT_DIM)
                    dpg.add_text("FPS: 0",  tag="status_fps")
                    dpg.add_text("|", color=Colors.TEXT_DIM)
                    dpg.add_text("Mode: follow", tag="status_mode")
                    dpg.add_text("|", color=Colors.TEXT_DIM)
                    dpg.add_text("Zoom: 60", tag="status_zoom")
                    dpg.add_text("|", color=Colors.TEXT_DIM)
                    dpg.add_text("Auto: OFF", tag="status_auto",
                                 color=Colors.TEXT_DIM)

        with dpg.handler_registry():
            dpg.add_mouse_wheel_handler(callback=self._on_mouse_wheel)
            dpg.add_mouse_click_handler(button=dpg.mvMouseButton_Middle,
                                        callback=self._on_middle_click)
            dpg.add_mouse_drag_handler(button=dpg.mvMouseButton_Middle,
                                       callback=self._on_middle_drag)
            dpg.add_mouse_release_handler(button=dpg.mvMouseButton_Middle,
                                          callback=self._on_middle_release)
            dpg.add_mouse_click_handler(button=dpg.mvMouseButton_Left,
                                        callback=self._on_left_click)
            dpg.add_mouse_drag_handler(button=dpg.mvMouseButton_Left,
                                       callback=self._on_left_drag)
            dpg.add_mouse_release_handler(button=dpg.mvMouseButton_Left,
                                          callback=self._on_left_release)
            dpg.add_mouse_click_handler(button=dpg.mvMouseButton_Right,
                                        callback=lambda *a: self._cancel_all())

            dpg.add_key_press_handler(dpg.mvKey_F,
                callback=lambda *a: self._set_camera("follow"))
            dpg.add_key_press_handler(dpg.mvKey_R,
                callback=lambda *a: self._set_camera("free"))
            dpg.add_key_press_handler(dpg.mvKey_O,
                callback=lambda *a: self._set_camera("overview"))
            dpg.add_key_press_handler(dpg.mvKey_G,
                callback=lambda *a: self._toggle('show_grid'))
            dpg.add_key_press_handler(dpg.mvKey_T,
                callback=lambda *a: self._toggle('show_trail'))
            dpg.add_key_press_handler(dpg.mvKey_H,
                callback=lambda *a: self._toggle('show_hud'))
            dpg.add_key_press_handler(dpg.mvKey_C,
                callback=lambda *a: self._toggle('show_crosshair'))
            dpg.add_key_press_handler(dpg.mvKey_P,
                callback=lambda *a: self._toggle('show_path'))
            dpg.add_key_press_handler(dpg.mvKey_M,
                callback=lambda *a: self._toggle_auto_enabled())
            dpg.add_key_press_handler(dpg.mvKey_N,
                callback=lambda *a: self._start_new_zone_mode())
            dpg.add_key_press_handler(dpg.mvKey_F1,
                callback=lambda *a: self._toggle_preview_giro())
            dpg.add_key_press_handler(dpg.mvKey_Escape,
                callback=lambda *a: self._cancel_all())

        dpg.create_viewport(title="Among Us AI Bot",
                            width=GPSConfig.WINDOW_W,
                            height=GPSConfig.WINDOW_H,
                            resizable=True,
                            min_width=800, min_height=500)
        dpg.set_viewport_resize_callback(self._on_viewport_resize)
        dpg.setup_dearpygui()
        dpg.show_viewport()
        dpg.set_primary_window("main_win", True)

        # Popola la listbox con le zone caricate dal file
        self._refresh_zone_list()
        # Popola la listbox con le task registrate
        self._refresh_reg_task_listbox()
        # Popola listbox zone porte
        self._refresh_door_zone_list()
        # Popola la listbox con i POI
        self._refresh_poi_listbox()

    def _costruisci_pannello(self):
        """
        Costruzione del pannello laterale.

        Layout:
        - In cima: sezione fissa sempre visibile (Telecamera, Zoom,
          Auto-movimento) - i controlli usati piu' di frequente.
        - Al centro: TabBar con 5 tab (Zone, Task, POI, Vista, Stats).
        - In basso: collapsing header con le scorciatoie da tastiera.

        Estetica: niente icone, label discorsive, larghezze fisse
        coerenti, spaziature di 4/6/8 px.
        """
        # =====================================================================
        # SEZIONE FISSA (in cima, sempre visibile senza scroll)
        # =====================================================================
        dpg.add_text("CONTROLLI", color=Colors.ACCENT)
        dpg.add_separator()

        # --- Telecamera ---
        dpg.add_spacer(height=4)
        dpg.add_text("Modalita' telecamera", color=Colors.TEXT_DIM)
        with dpg.group(horizontal=True):
            dpg.add_button(label="Segui",   width=104,
                callback=lambda *a: self._set_camera("follow"))
            dpg.add_button(label="Libera",  width=104,
                callback=lambda *a: self._set_camera("free"))
            dpg.add_button(label="Tutta",   width=104,
                callback=lambda *a: self._set_camera("overview"))

        # --- Zoom ---
        dpg.add_spacer(height=8)
        dpg.add_text("Zoom della mappa", color=Colors.TEXT_DIM)
        dpg.add_slider_float(tag="zoom_slider",
                             default_value=self.scale,
                             min_value=GPSConfig.MIN_SCALE,
                             max_value=GPSConfig.MAX_SCALE,
                             width=-1,
                             callback=self._on_zoom_slider)
        with dpg.group(horizontal=True):
            dpg.add_button(label="Riduci",   width=104,
                callback=lambda *a: self._zoom(0.8))
            dpg.add_button(label="Aumenta",  width=104,
                callback=lambda *a: self._zoom(1.25))
            dpg.add_button(label="Predefinito", width=104,
                callback=lambda *a: self._reset_view())

        # --- Auto-Movement ---
        dpg.add_spacer(height=10)
        dpg.add_separator()
        dpg.add_text("AUTO-MOVIMENTO", color=Colors.ACCENT)
        dpg.add_separator()
        dpg.add_spacer(height=4)

        dpg.add_checkbox(label="Abilita (click sulla mappa)",
                         default_value=self.auto_enabled,
                         tag="auto_checkbox",
                         callback=self._on_auto_checkbox)
        dpg.add_spacer(height=4)

        # Riepilogo stato in tabella allineata (etichetta a sinistra, valore a destra)
        with dpg.table(header_row=False, borders_innerH=False,
                       borders_outerH=False, borders_innerV=False,
                       borders_outerV=False,
                       policy=dpg.mvTable_SizingStretchProp):
            dpg.add_table_column(init_width_or_weight=0.35)
            dpg.add_table_column(init_width_or_weight=0.65)
            with dpg.table_row():
                dpg.add_text("Stato:",  color=Colors.TEXT_DIM)
                dpg.add_text("inattivo", tag="auto_state_label",
                             color=Colors.TEXT_DIM)
            with dpg.table_row():
                dpg.add_text("Target:", color=Colors.TEXT_DIM)
                dpg.add_text("-", tag="auto_target_label")
            with dpg.table_row():
                dpg.add_text("Percorso:", color=Colors.TEXT_DIM)
                dpg.add_text("0 waypoint", tag="auto_path_label")

        dpg.add_spacer(height=6)
        dpg.add_button(label="Annulla movimento (ESC)", width=-1,
                       callback=lambda *a: self._cancel_auto_move())
        dpg.add_checkbox(label="Mostra percorso sulla mappa",
                         default_value=self.show_path,
                         callback=lambda s, a: setattr(self, 'show_path', a))

        # =====================================================================
        # TAB BAR
        # =====================================================================
        dpg.add_spacer(height=10)
        with dpg.tab_bar(tag="side_panel_tabs"):

            # ============================ ZONE ============================
            with dpg.tab(label="Zone"):
                dpg.add_spacer(height=6)

                with dpg.collapsing_header(label="Zone nominate",
                                           default_open=True):
                    dpg.add_spacer(height=4)
                    dpg.add_text("Aree definite a mano sulla mappa.",
                                 color=Colors.TEXT_DIM)
                    dpg.add_spacer(height=4)
                    dpg.add_button(label="Disegna nuova zona  [N]", width=-1,
                                   tag="btn_nuova_zona",
                                   callback=lambda *a: self._start_new_zone_mode())
                    dpg.add_spacer(height=4)
                    dpg.add_listbox(tag="zone_listbox", items=[],
                                    num_items=6, width=-1)
                    dpg.add_spacer(height=4)
                    with dpg.group(horizontal=True):
                        dpg.add_button(label="Centra",       width=156,
                                       callback=lambda *a: self._vai_a_zona())
                        dpg.add_button(label="Naviga (A*)",  width=156,
                                       callback=lambda *a: self._naviga_a_zona())
                    with dpg.group(horizontal=True):
                        dpg.add_button(label="Modifica forma", width=156,
                                       callback=lambda *a: self._modifica_forma_zona())
                        dpg.add_button(label="Cambia colore",  width=156,
                                       callback=lambda *a: self._cambia_colore_zona())
                    with dpg.group(horizontal=True):
                        dpg.add_button(label="Rinomina",        width=104,
                                       callback=lambda *a: self._rinomina_zona())
                        dpg.add_button(label="Adatta",          width=104,
                                       callback=lambda *a: self._forza_adattamento_zona())
                        dpg.add_button(label="Elimina",         width=104,
                                       callback=lambda *a: self._elimina_zona())
                    dpg.add_spacer(height=4)
                    dpg.add_button(label="Imposta ID zona di gioco", width=-1,
                                   callback=lambda *a: self._imposta_game_zone_id())
                    dpg.add_spacer(height=2)

                dpg.add_spacer(height=8)

                with dpg.collapsing_header(label="Zone porte (filtro YOLO)",
                                           default_open=False):
                    dpg.add_spacer(height=4)
                    dpg.add_text("Aree dove ignorare le porte rilevate.",
                                 color=Colors.TEXT_DIM)
                    dpg.add_spacer(height=4)
                    dpg.add_button(label="Disegna nuova zona porta", width=-1,
                                   callback=lambda *a: self._start_new_door_zone_mode())
                    dpg.add_spacer(height=4)
                    dpg.add_listbox(tag="door_zone_listbox", items=[],
                                    num_items=4, width=-1)
                    dpg.add_spacer(height=4)
                    with dpg.group(horizontal=True):
                        dpg.add_button(label="Centra",         width=104,
                                       callback=lambda *a: self._vai_a_door_zona())
                        dpg.add_button(label="Modifica forma", width=104,
                                       callback=lambda *a: self._modifica_forma_door_zona())
                        dpg.add_button(label="Cambia colore",  width=104,
                                       callback=lambda *a: self._cambia_colore_door_zona())
                    with dpg.group(horizontal=True):
                        dpg.add_button(label="Rinomina", width=156,
                                       callback=lambda *a: self._rinomina_door_zona())
                        dpg.add_button(label="Elimina",  width=156,
                                       callback=lambda *a: self._elimina_door_zone())
                    dpg.add_spacer(height=4)
                    dpg.add_checkbox(label="Mostra zone porte sulla mappa",
                                     default_value=True,
                                     callback=lambda s, a: setattr(self, 'show_door_zones', a))
                    dpg.add_spacer(height=2)

            # ============================ TASK ============================
            with dpg.tab(label="Task"):
                dpg.add_spacer(height=6)

                dpg.add_button(label="Gestione padre / figlia",
                               width=-1, height=30,
                               callback=lambda *a: self._apri_popup_padre_figlia())

                dpg.add_spacer(height=8)

                with dpg.collapsing_header(label="Task in memoria (RAM)",
                                           default_open=True):
                    dpg.add_spacer(height=4)
                    dpg.add_text("Task lette dal gioco in tempo reale.",
                                 color=Colors.TEXT_DIM)
                    dpg.add_spacer(height=4)
                    with dpg.group(horizontal=True):
                        dpg.add_text("Elenco:", color=Colors.TEXT_DIM)
                        dpg.add_checkbox(label="Ordina A-Z",
                                         default_value=False,
                                         tag="sort_mem_tasks_chk",
                                         callback=lambda *a: self._refresh_mem_task_listbox())
                    dpg.add_listbox(tag="mem_task_listbox", items=[],
                                    num_items=6, width=-1)
                    dpg.add_spacer(height=4)
                    with dpg.group(horizontal=True):
                        dpg.add_button(label="Naviga (A*)",     width=104,
                                       callback=lambda *a: self._naviga_a_task_memoria())
                        dpg.add_button(label="Avvia task",      width=104,
                                       callback=lambda *a: self._avvia_task_selezionata())
                        dpg.add_button(label="Registra nuova", width=104,
                                       callback=lambda *a: self._registra_task_sconosciuta())
                    dpg.add_spacer(height=4)
                    dpg.add_button(label="Esegui automaticamente tutte le task",
                                   width=-1, tag="btn_auto_all",
                                   callback=lambda *a: self._toggle_auto_all())
                    dpg.add_spacer(height=4)
                    with dpg.group(horizontal=True):
                        dpg.add_button(label="Modifica task",       width=156,
                                       callback=lambda *a: self._modifica_task_da_memoria())
                        dpg.add_button(label="Ferma esecuzione",    width=156,
                                       tag="btn_stop_task",
                                       callback=lambda *a: self._ferma_processo_task())
                    dpg.add_spacer(height=2)
                    dpg.add_text("", tag="processo_status",
                                 color=(200, 200, 200, 200))

                dpg.add_spacer(height=8)

                with dpg.collapsing_header(label="Task registrate",
                                           default_open=False):
                    dpg.add_spacer(height=4)
                    dpg.add_text("Task salvate dall'utente con azioni custom.",
                                 color=Colors.TEXT_DIM)
                    dpg.add_spacer(height=4)
                    with dpg.group(horizontal=True):
                        dpg.add_text("Elenco:", color=Colors.TEXT_DIM)
                        dpg.add_checkbox(label="Ordina A-Z",
                                         default_value=False,
                                         tag="sort_reg_tasks_chk",
                                         callback=lambda *a: self._refresh_reg_task_listbox())
                    dpg.add_listbox(tag="reg_task_listbox", items=[],
                                    num_items=6, width=-1)
                    dpg.add_spacer(height=4)
                    with dpg.group(horizontal=True):
                        dpg.add_button(label="Nuova task",        width=156,
                                       callback=lambda *a: self._apri_popup_nuova_task())
                        dpg.add_button(label="Modifica task",     width=156,
                                       callback=lambda *a: self._apri_popup_modifica_task())
                    with dpg.group(horizontal=True):
                        dpg.add_button(label="Aggiungi fase",     width=156,
                                       callback=lambda *a: self._apri_popup_nuova_fase())
                        dpg.add_button(label="Aggiungi alternativo", width=156,
                                       callback=lambda *a: self._apri_popup_nuovo_alternativo())
                    with dpg.group(horizontal=True):
                        dpg.add_button(label="Naviga (A*)",       width=156,
                                       callback=lambda *a: self._naviga_a_task_registrata())
                        dpg.add_button(label="Elimina task",      width=156,
                                       callback=lambda *a: self._elimina_task_registrata())
                    dpg.add_spacer(height=4)
                    with dpg.group(horizontal=True):
                        dpg.add_button(label="Genera file .py",   width=156,
                                       tag="btn_genera_py",
                                       callback=lambda *a: self._genera_file_esecuzione())
                        dpg.add_text("", tag="genera_py_status",
                                     color=(0, 200, 120, 255))
                    dpg.add_spacer(height=4)
                    dpg.add_button(label="Collega task a zona di gioco", width=-1,
                                   callback=lambda *a: self._apri_popup_collegamento_zona())
                    dpg.add_spacer(height=2)

            # ============================ POI =============================
            with dpg.tab(label="POI"):
                dpg.add_spacer(height=6)

                dpg.add_text("Punti di interesse sulla mappa.",
                             color=Colors.TEXT_DIM)
                dpg.add_spacer(height=4)
                dpg.add_checkbox(label="Mostra sulla mappa",
                                 default_value=self.show_poi,
                                 callback=lambda s, a: setattr(self, 'show_poi', a))
                dpg.add_spacer(height=4)
                dpg.add_listbox(tag="poi_listbox", items=[],
                                num_items=10, width=-1)
                dpg.add_spacer(height=4)
                with dpg.group(horizontal=True):
                    dpg.add_button(label="Nuovo POI",      width=156,
                                   callback=lambda *a: self._apri_popup_nuovo_poi())
                    dpg.add_button(label="Modifica",       width=156,
                                   callback=lambda *a: self._apri_popup_modifica_poi())
                with dpg.group(horizontal=True):
                    dpg.add_button(label="Naviga (A*)",    width=156,
                                   callback=lambda *a: self._naviga_a_poi())
                    dpg.add_button(label="Elimina",        width=156,
                                   callback=lambda *a: self._elimina_poi())

            # =========================== VISTA ============================
            with dpg.tab(label="Vista"):
                dpg.add_spacer(height=6)

                with dpg.collapsing_header(label="Livelli visibili",
                                           default_open=True):
                    dpg.add_spacer(height=4)
                    dpg.add_text("Mostra o nascondi i livelli sulla mappa.",
                                 color=Colors.TEXT_DIM)
                    dpg.add_spacer(height=4)
                    dpg.add_checkbox(label="Griglia",
                                     default_value=self.show_grid,
                                     callback=lambda s, a: setattr(self, 'show_grid', a))
                    dpg.add_checkbox(label="Scia (trail)",
                                     default_value=self.show_trail,
                                     callback=lambda s, a: setattr(self, 'show_trail', a))
                    dpg.add_checkbox(label="Mappa visitata",
                                     default_value=self.show_visited,
                                     callback=self._on_toggle_visited)
                    dpg.add_checkbox(label="Mirino centrale",
                                     default_value=self.show_crosshair,
                                     callback=lambda s, a: setattr(self, 'show_crosshair', a))
                    dpg.add_checkbox(label="Linee zona-task",
                                     default_value=self.show_task_links,
                                     callback=lambda s, a: setattr(self, 'show_task_links', a))
                    dpg.add_checkbox(label="Mostra solo task in memoria",
                                     default_value=self.show_only_active_tasks,
                                     callback=lambda s, a: setattr(self, 'show_only_active_tasks', a))
                    dpg.add_checkbox(label="Overlay informativo (HUD)",
                                     default_value=self.show_hud,
                                     callback=lambda s, a: setattr(self, 'show_hud', a))
                    dpg.add_spacer(height=2)

                dpg.add_spacer(height=8)

                with dpg.collapsing_header(label="Rilevamento YOLO",
                                           default_open=False):
                    dpg.add_spacer(height=4)
                    dpg.add_text("Visualizza giocatori e porte rilevati.",
                                 color=Colors.TEXT_DIM)
                    dpg.add_spacer(height=4)
                    dpg.add_checkbox(label="Altri giocatori (YOLO)",
                                     default_value=self.show_other_players,
                                     callback=lambda s, a: setattr(self, 'show_other_players', a))
                    dpg.add_checkbox(label="Porte chiuse rilevate (YOLO)",
                                     default_value=self.show_detected_doors,
                                     callback=lambda s, a: setattr(self, 'show_detected_doors', a))
                    dpg.add_spacer(height=6)
                    dpg.add_text("Altezza camera (calibrazione)",
                                 color=Colors.TEXT_DIM)
                    dpg.add_slider_float(tag="yolo_cam_slider",
                                         default_value=self.yolo_camera_height,
                                         min_value=3.0, max_value=12.0, width=-1,
                                         callback=lambda s, a: setattr(self, 'yolo_camera_height', a))
                    dpg.add_checkbox(label="Auto-calibra YOLO durante il movimento",
                                     default_value=self.yolo_auto_calibrate,
                                     callback=lambda s, a: setattr(self, 'yolo_auto_calibrate', a))
                    dpg.add_spacer(height=2)

                dpg.add_spacer(height=8)

                with dpg.collapsing_header(label="Smoothing telecamera",
                                           default_open=False):
                    dpg.add_spacer(height=4)
                    dpg.add_text("Velocita' di interpolazione del movimento.",
                                 color=Colors.TEXT_DIM)
                    dpg.add_spacer(height=4)
                    dpg.add_slider_float(label="Smoothing",
                                         default_value=GPSConfig.SMOOTHING,
                                         min_value=1.0, max_value=50.0, width=-100,
                                         callback=lambda s, a: setattr(GPSConfig, 'SMOOTHING', a))
                    dpg.add_spacer(height=2)

            # =========================== STATS ============================
            with dpg.tab(label="Stats"):
                dpg.add_spacer(height=6)

                dpg.add_text("Statistiche della sessione corrente.",
                             color=Colors.TEXT_DIM)
                dpg.add_spacer(height=8)

                with dpg.table(header_row=False,
                               borders_innerH=False, borders_outerH=False,
                               borders_innerV=False, borders_outerV=False,
                               policy=dpg.mvTable_SizingStretchProp):
                    dpg.add_table_column(init_width_or_weight=0.55)
                    dpg.add_table_column(init_width_or_weight=0.45)

                    with dpg.table_row():
                        dpg.add_text("Distanza percorsa:", color=Colors.TEXT_DIM)
                        dpg.add_text("0.00 u", tag="stat_dist")
                    with dpg.table_row():
                        dpg.add_text("Tempo sessione:", color=Colors.TEXT_DIM)
                        dpg.add_text("00:00", tag="stat_time")
                    with dpg.table_row():
                        dpg.add_text("Celle mappa:", color=Colors.TEXT_DIM)
                        dpg.add_text(f"{len(self.visitati_coords)}",
                                     tag="stat_visited")
                    with dpg.table_row():
                        dpg.add_text("Celle calpestabili:", color=Colors.TEXT_DIM)
                        dpg.add_text(f"{len(self.pathfinder.walkable)}",
                                     tag="stat_walkable")
                    with dpg.table_row():
                        dpg.add_text("Punti del trail:", color=Colors.TEXT_DIM)
                        dpg.add_text("0", tag="stat_trail")

        # =====================================================================
        # FOOTER - Scorciatoie da tastiera
        # =====================================================================
        dpg.add_spacer(height=12)
        with dpg.collapsing_header(label="Scorciatoie da tastiera",
                                   default_open=False):
            dpg.add_spacer(height=4)
            dpg.add_text(
                "F / R / O           Telecamera (segui / libera / panoramica)\n"
                "G / T / C / H / P   Mostra-nascondi livelli\n"
                "M                   Abilita auto-movimento\n"
                "N                   Disegna nuova zona\n"
                "F4 / FINE (END)     Ferma esecuzione (globale)\n"
                "Click sinistro      Imposta destinazione (pathfinding)\n"
                "Click destro / ESC  Annulla operazione corrente\n"
                "Rotellina mouse     Zoom\n"
                "Tasto centrale + drag  Pan della mappa",
                color=Colors.TEXT_DIM)
            dpg.add_spacer(height=2)

    def _setup_theme(self):
        """Inizializza theme."""
        # Tema globale: palette principale, padding e arrotondamenti.
        with dpg.theme() as self.global_theme:
            with dpg.theme_component(dpg.mvAll):
                dpg.add_theme_color(dpg.mvThemeCol_WindowBg,       Colors.BG)
                dpg.add_theme_color(dpg.mvThemeCol_ChildBg,        Colors.BG)
                dpg.add_theme_color(dpg.mvThemeCol_MenuBarBg,      Colors.PANEL_BG)
                dpg.add_theme_color(dpg.mvThemeCol_PopupBg,        Colors.PANEL_BG)
                dpg.add_theme_color(dpg.mvThemeCol_Button,         (40, 42, 52, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered,  (0, 130, 210, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,   (0, 170, 240, 255))
                dpg.add_theme_color(dpg.mvThemeCol_FrameBg,        (28, 28, 34, 255))
                dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, (40, 40, 48, 255))
                dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive,  (50, 50, 60, 255))
                dpg.add_theme_color(dpg.mvThemeCol_SliderGrab,     Colors.ACCENT)
                dpg.add_theme_color(dpg.mvThemeCol_SliderGrabActive, (0, 230, 255, 255))
                dpg.add_theme_color(dpg.mvThemeCol_CheckMark,      Colors.ACCENT)
                dpg.add_theme_color(dpg.mvThemeCol_Text,           Colors.TEXT)
                dpg.add_theme_color(dpg.mvThemeCol_TextDisabled,   Colors.TEXT_DIM)
                dpg.add_theme_color(dpg.mvThemeCol_Separator,      (60, 60, 72, 255))
                dpg.add_theme_color(dpg.mvThemeCol_Header,         (45, 50, 60, 255))
                dpg.add_theme_color(dpg.mvThemeCol_HeaderHovered,  (0, 110, 170, 255))
                dpg.add_theme_color(dpg.mvThemeCol_HeaderActive,   (0, 140, 200, 255))
                dpg.add_theme_color(dpg.mvThemeCol_Tab,            (30, 32, 40, 255))
                dpg.add_theme_color(dpg.mvThemeCol_TabHovered,     (0, 130, 210, 255))
                dpg.add_theme_color(dpg.mvThemeCol_TabActive,      (0, 100, 160, 255))
                dpg.add_theme_color(dpg.mvThemeCol_TabUnfocused,   (24, 26, 32, 255))
                dpg.add_theme_color(dpg.mvThemeCol_TabUnfocusedActive, (30, 32, 40, 255))
                # Stile: arrotondamento e padding piu' generosi
                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding,    6)
                dpg.add_theme_style(dpg.mvStyleVar_GrabRounding,     6)
                dpg.add_theme_style(dpg.mvStyleVar_TabRounding,      6)
                dpg.add_theme_style(dpg.mvStyleVar_PopupRounding,    6)
                dpg.add_theme_style(dpg.mvStyleVar_ChildRounding,    6)
                dpg.add_theme_style(dpg.mvStyleVar_ScrollbarRounding,8)
                dpg.add_theme_style(dpg.mvStyleVar_WindowPadding,    8, 8)
                dpg.add_theme_style(dpg.mvStyleVar_FramePadding,     6, 4)
                dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing,      6, 5)
                dpg.add_theme_style(dpg.mvStyleVar_ItemInnerSpacing, 6, 4)
                dpg.add_theme_style(dpg.mvStyleVar_IndentSpacing,   12)
        dpg.bind_theme(self.global_theme)

        # ---------- Tema "azione primaria" (Avvia Task, Esegui TUTTE) ----------
        # Verde acceso: usato per i bottoni di azione "go!"
        with dpg.theme() as self._theme_btn_primary:
            with dpg.theme_component(dpg.mvButton):
                dpg.add_theme_color(dpg.mvThemeCol_Button,        (32, 130, 80, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (40, 180, 110, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,  (50, 220, 140, 255))
                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 6)

        # ---------- Tema "azione distruttiva" (Stop, Elimina) ----------
        # Rosso scuro: usato per bottoni che fermano o cancellano qualcosa
        with dpg.theme() as self._theme_btn_danger:
            with dpg.theme_component(dpg.mvButton):
                dpg.add_theme_color(dpg.mvThemeCol_Button,        (140, 40, 50, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (200, 60, 70, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,  (240, 80, 90, 255))
                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 6)

        # ---------- Tema "azione di creazione" (+ Nuova Zona, + Nuovo POI) ----------
        # Blu turchese: per bottoni che aggiungono qualcosa
        with dpg.theme() as self._theme_btn_create:
            with dpg.theme_component(dpg.mvButton):
                dpg.add_theme_color(dpg.mvThemeCol_Button,        (30, 100, 140, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (40, 140, 200, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,  (50, 180, 240, 255))
                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 6)
