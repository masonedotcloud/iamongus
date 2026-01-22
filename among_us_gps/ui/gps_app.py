"""
Applicazione principale: GPS Visualizer Pro.

E' la "god class" che orchestra tutto: lettura RAM in thread, scanner YOLO,
rendering DPG, pathfinding, gestione task/zone/POI, popup di editing,
input simulato per il movimento automatico ecc.

Per mantenibilita' la classe e' stata lasciata in un file singolo (164
metodi). Suddividerla in mixin avrebbe richiesto di stravolgere il flusso
di stato condiviso tra rendering, input e logica di task/navigazione.
Ogni gruppo di metodi e' marcato da un commento "# ================= ... ".

Layout dei metodi (per orientarsi):
- __init__ + carica_mappa + bounds
- _setup_interfaccia / _costruisci_pannello / _setup_theme : UI setup
- _leggi_memoria / _yolo_scanner_loop : thread di sfondo
- _on_*  : event handler DPG (mouse/zoom/drag)
- _update_auto_move / _update_auto_all : tick del pathfinding
- _refresh_*_listbox : aggiornamento liste sidebar
- _apri_popup_*  : finestre modali
- _avvia_task_* / _ferma_processo_task : ciclo di vita esecuzione task
- _render_* : drawing chiamato in aggiorna_frame
- run() : main loop DPG
"""

import atexit
import json
import math
import os
import random
import subprocess
import sys
import threading
import time

import dearpygui.dearpygui as dpg

from ..core.config import GPSConfig, Colors
from ..core.geometry import hex_to_rgba as _hex_to_rgba, get_client_rect
from ..core import stop_flag
from ..core.win_deps import (
    WIN_OK as _WIN_OK,
    mss,
    np,
    pyautogui,
    win32api,
    win32gui,
)
from ..game_io import AmongUsMemoryReader, AmongUsTaskReader
from ..io_input import KeyController, SCAN_CODES
from ..io_input.key_controller import _send_scan
from ..managers import PoiManager, TaskManager, ZoneManager
from ..pathfinding import Pathfinder
from .task_action_editor import TaskActionEditor


class GPSVisualizerPro:
    def __init__(self):
        self.reader      = AmongUsMemoryReader()
        self.task_reader = AmongUsTaskReader(GPSConfig.TASKS_DEF_FILE)
        self.visitati_coords = []

        self.pos_target  = [0.0, 0.0]
        self.pos_visuale = [0.0, 0.0]

        self.scale = GPSConfig.DEFAULT_SCALE
        self.canvas_w = GPSConfig.WINDOW_W - GPSConfig.SIDE_PANEL_W - 20
        self.canvas_h = GPSConfig.WINDOW_H - GPSConfig.STATUS_BAR_H - 60

        self.camera_mode = "follow"
        self.free_cam = [0.0, 0.0]
        self.is_panning = False
        self.pan_start_cam = (0.0, 0.0)

        self.show_grid = True
        self.show_trail = True
        self.show_visited = True
        self.show_crosshair = True
        self.show_hud = True
        self.show_path = True
        self.show_task_links = False
        self.show_only_active_tasks = True
        
        # --- Scanner giocatori YOLO ---
        self.show_other_players = True
        self.show_detected_doors = True
        self.yolo_camera_height = 6.0
        self.yolo_auto_calibrate = False
        self.detected_players = []  # Lista di dict: {'x': ..., 'y': ..., 'time': ...}
        self.detected_doors = []    # Lista di dict: {'x': ..., 'y': ..., 'time': ...}

        self.trail = []
        self.last_trail_time = 0.0
        self.total_distance = 0.0
        self.last_pos_for_dist = None
        self.session_start = time.time()

        # Auto-movimento + pathfinding
        self.key_ctrl = KeyController()
        self.pathfinder = Pathfinder(GPSConfig.CELL_STEP)
        self.auto_enabled = False
        self.auto_final_target = None      # (x,y) clicked
        self.auto_path = []                # [(x,y), ...]  waypoints in game coords
        self.auto_path_index = 0
        self.auto_stuck_pos = None
        self.auto_stuck_timer = 0.0
        self.auto_status_msg = ""
        self._on_arrival_callback = None   # callable() chiamato una volta all'arrivo
        
        # --- Auto-Execute All (Auto-Quest) ---
        self.auto_execute_all = False
        self._auto_all_timer = 0.0

        # --- Zone ---
        self.zone_mgr = ZoneManager(GPSConfig.ZONE_FILE)
        self.door_zone_mgr = ZoneManager("door_zones_skeld.json")
        self.zone_draw_mode = False
        self.zone_draw_type = "normal"
        self.zone_draw_points = []
        self.door_rect_start = None
        self.door_rect_end = None
        self.zone_last_pixel = None
        self.zona_in_modifica = None

        # --- Task ---
        self.task_mgr = TaskManager(GPSConfig.TASK_FILE, GPSConfig.TASKS_DEF_FILE)

        # --- Punti di Interesse ---
        self.poi_mgr  = PoiManager(GPSConfig.POI_FILE)
        self.show_poi = True
        self.memory_tasks           = []
        self.task_launch_log        = []
        self._task_launch_nome      = ""
        self._task_launch_steps     = []
        self._task_launch_id        = None   # id task in corso di avvio
        self._task_launch_arrivo    = False  # True quando il player è arrivato (fase 3)
        self._task_launch_timer_arr = 0.0    # timer fase 3
        self._task_process          = None   # subprocess.Popen del file .py in esecuzione
        self._task_process_task_id  = None   # id task associata al processo attivo
        self._pending_refresh_task_list = False
        
        # Cooldown per le task (Idea 3): { id_task: timestamp_ready }
        self.task_cooldowns         = {}
        self.task_internal_steps    = {} # Tiene traccia dei chunk (fasi) completate localmente

        # Editor delle azioni (finestra DPG separata)
        self.action_editor          = TaskActionEditor(self.task_mgr)

        self.map_bounds = None
        self.running = True

        self.carica_mappa()
        self._calcola_bounds_mappa()
        self.pathfinder.rebuild(self.visitati_coords)

        self.mem_thread = threading.Thread(target=self._leggi_memoria, daemon=True)
        self.mem_thread.start()
        
        # Avvio scanner YOLO in background
        self.yolo_scanner_thread = threading.Thread(target=self._yolo_scanner_loop, daemon=True)
        self.yolo_scanner_thread.start()

        atexit.register(self.key_ctrl.release_all)
        atexit.register(self._ferma_processo_task)
        self._setup_interfaccia()

    # ================= THREAD MEMORIA =================
    def _leggi_memoria(self):
        while self.running:
            # --- Posizione giocatore ---
            pos = self.reader.get_position()
            if pos:
                self.pos_target = list(pos)

            # --- Task dalla RAM ---
            tasks = self.task_reader.get_tasks()
            if tasks is not None:
                self.memory_tasks = tasks
                # Sync automatica nomi: se una task registrata ha raw_game_id
                # e il gioco ora conosce il nome vero, aggiorna il JSON
                self._sync_nomi_task_da_ram(tasks)

                # Pulisce gli step interni per le task che sono state terminate nel gioco
                for mt in tasks:
                    if mt.get('done', False):
                        reg = self.task_mgr.find_registered(tipo=mt.get('tipo'), room_id=mt.get('room_id'))
                        if reg and reg['id'] in self.task_internal_steps:
                            self.task_internal_steps[reg['id']] = 0

            time.sleep(0.05)

    def _sync_nomi_task_da_ram(self, ram_tasks):
        """
        Aggiorna i nomi testuali nel JSON se la RAM fornisce nomi migliori.
        Usa la combinazione (tipo, room_id) come chiave.
        """
        if not ram_tasks:
            return
        
        # Mappa (tipo, room_id) -> nome dal gioco
        ram_dict = {(mt['tipo'], mt['room_id']): mt['nome'] for mt in ram_tasks
                    if not mt['nome'].startswith("Task Type ")}
        
        aggiornato = False
        for t in self.task_mgr.task_list:
            chiave = (t.get('tipo'), t.get('room_id'))
            nome_gioco = ram_dict.get(chiave)
            
            if nome_gioco is None:
                continue
                
            prefisso = f"{t.get('zone_nome')}: " if t.get('zone_nome') else ""
            nome_atteso = f"{prefisso}{nome_gioco}"
            
            if t['nome'] != nome_atteso:
                t['nome'] = nome_atteso
                aggiornato = True
                
        if aggiornato:
            self.task_mgr.salva()
            self._pending_refresh_task_list = True

    # ================= MAPPA =================
    def carica_mappa(self):
        if not os.path.exists(GPSConfig.MAP_FILE): return
        try:
            with open(GPSConfig.MAP_FILE, 'r') as f:
                data = json.load(f)
                for k in data.get('visitati', []):
                    try:
                        kx, ky = map(float, k.split(','))
                        self.visitati_coords.append((kx, ky))
                    except ValueError:
                        pass
        except Exception as e:
            print(f"Errore caricamento mappa: {e}")

    def _calcola_bounds_mappa(self):
        if not self.visitati_coords:
            self.map_bounds = (-10, -10, 10, 10); return
        xs = [p[0] for p in self.visitati_coords]
        ys = [p[1] for p in self.visitati_coords]
        pad = 2.0
        self.map_bounds = (min(xs) - pad, min(ys) - pad,
                           max(xs) + pad, max(ys) + pad)

    # ================= UI =================
    def _setup_interfaccia(self):
        dpg.create_context()
        self._setup_theme()

        with dpg.window(tag="main_win", no_title_bar=True, no_resize=True,
                        no_move=True, no_scrollbar=True,
                        no_bring_to_front_on_focus=True):

            with dpg.menu_bar():
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
                with dpg.menu(label="Auto-move"):
                    dpg.add_menu_item(label="Abilita / Disabilita [M]",
                        callback=lambda *a: self._toggle_auto_enabled())
                    dpg.add_menu_item(label="Annulla [ESC]",
                        callback=lambda *a: self._cancel_auto_move())
                with dpg.menu(label="Strumenti"):
                    dpg.add_menu_item(label="Cancella trail",
                        callback=lambda *a: self._clear_trail())
                    dpg.add_menu_item(label="Reset statistiche",
                        callback=lambda *a: self._reset_distance())
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
            dpg.add_key_press_handler(dpg.mvKey_Escape,
                callback=lambda *a: self._cancel_all())

        dpg.create_viewport(title="Among Us — Among Us AI Bot",
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
        dpg.add_text("CONTROLLI", color=Colors.ACCENT)
        dpg.add_separator()

        dpg.add_text("Telecamera")
        with dpg.group(horizontal=True):
            dpg.add_button(label="Follow", width=80,
                callback=lambda *a: self._set_camera("follow"))
            dpg.add_button(label="Libera", width=80,
                callback=lambda *a: self._set_camera("free"))
            dpg.add_button(label="Tutta", width=80,
                callback=lambda *a: self._set_camera("overview"))

        dpg.add_spacer(height=10)
        dpg.add_text("Zoom")
        dpg.add_slider_float(tag="zoom_slider",
                             default_value=self.scale,
                             min_value=GPSConfig.MIN_SCALE,
                             max_value=GPSConfig.MAX_SCALE,
                             width=-1,
                             callback=self._on_zoom_slider)
        with dpg.group(horizontal=True):
            dpg.add_button(label=" - ", width=50,
                callback=lambda *a: self._zoom(0.8))
            dpg.add_button(label=" + ", width=50,
                callback=lambda *a: self._zoom(1.25))
            dpg.add_button(label="Reset", width=110,
                callback=lambda *a: self._reset_view())

        dpg.add_spacer(height=10)
        dpg.add_separator()
        dpg.add_text("AUTO-MOVEMENT", color=Colors.ACCENT)
        dpg.add_separator()

        dpg.add_checkbox(label="Abilita (click sulla mappa)",
                         default_value=self.auto_enabled,
                         tag="auto_checkbox",
                         callback=self._on_auto_checkbox)
        dpg.add_text("Stato:", color=Colors.TEXT_DIM)
        dpg.add_text("inattivo", tag="auto_state_label", color=Colors.TEXT_DIM)
        dpg.add_text("Target:", color=Colors.TEXT_DIM)
        dpg.add_text("—", tag="auto_target_label")
        dpg.add_text("Path:", color=Colors.TEXT_DIM)
        dpg.add_text("0 waypoint", tag="auto_path_label")
        dpg.add_button(label="Stop (ESC)", width=-1,
                       callback=lambda *a: self._cancel_auto_move())
        dpg.add_checkbox(label="Mostra percorso",
                         default_value=self.show_path,
                         callback=lambda s, a: setattr(self, 'show_path', a))

        # ================== ZONE ==================
        dpg.add_spacer(height=10)
        dpg.add_separator()
        dpg.add_text("ZONE", color=Colors.ACCENT)
        dpg.add_separator()

        dpg.add_button(label="+ Nuova Zona  [N]", width=-1,
                       tag="btn_nuova_zona",
                       callback=lambda *a: self._start_new_zone_mode())
        dpg.add_listbox(tag="zone_listbox", items=[],
                        num_items=6, width=-1)
        with dpg.group(horizontal=True):
            dpg.add_button(label="Centra", width=85,
                           callback=lambda *a: self._vai_a_zona())
            dpg.add_button(label="Naviga A*", width=85,
                           callback=lambda *a: self._naviga_a_zona())
        with dpg.group(horizontal=True):
            dpg.add_button(label="Forma", width=85,
                           callback=lambda *a: self._modifica_forma_zona())
            dpg.add_button(label="Colore", width=85,
                           callback=lambda *a: self._cambia_colore_zona())
        with dpg.group(horizontal=True):
            dpg.add_button(label="Rinomina", width=85,
                           callback=lambda *a: self._rinomina_zona())
            dpg.add_button(label="Adatta", width=85,
                           callback=lambda *a: self._forza_adattamento_zona())
            dpg.add_button(label="Elimina", width=85,
                           callback=lambda *a: self._elimina_zona())
        dpg.add_button(label="Imposta ID Zona Gioco", width=-1,
                       callback=lambda *a: self._imposta_game_zone_id())

        dpg.add_spacer(height=10)
        dpg.add_separator()
        dpg.add_text("ZONE PORTE (FILTRO YOLO)", color=(255, 100, 100))
        dpg.add_separator()

        dpg.add_button(label="+ Disegna Zona Porta", width=-1,
                       callback=lambda *a: self._start_new_door_zone_mode())
        dpg.add_listbox(tag="door_zone_listbox", items=[], num_items=4, width=-1)
        with dpg.group(horizontal=True):
            dpg.add_button(label="Centra", width=85,
                           callback=lambda *a: self._vai_a_door_zona())
            dpg.add_button(label="Forma", width=85,
                           callback=lambda *a: self._modifica_forma_door_zona())
            dpg.add_button(label="Colore", width=85,
                           callback=lambda *a: self._cambia_colore_door_zona())
        with dpg.group(horizontal=True):
            dpg.add_button(label="Rinomina", width=85,
                           callback=lambda *a: self._rinomina_door_zona())
            dpg.add_button(label="Elimina", width=85,
                           callback=lambda *a: self._elimina_door_zone())
        dpg.add_checkbox(label="Mostra Zone Porte su Mappa", default_value=True,
                         callback=lambda s, a: setattr(self, 'show_door_zones', a))

        dpg.add_spacer(height=10)
        dpg.add_separator()
        dpg.add_text("Livelli visibili")
        dpg.add_checkbox(label="Griglia", default_value=self.show_grid,
                         callback=lambda s, a: setattr(self, 'show_grid', a))
        dpg.add_checkbox(label="Scia (trail)", default_value=self.show_trail,
                         callback=lambda s, a: setattr(self, 'show_trail', a))
        dpg.add_checkbox(label="Mappa visitata", default_value=self.show_visited,
                         callback=self._on_toggle_visited)
        dpg.add_checkbox(label="Mirino centrale", default_value=self.show_crosshair,
                         callback=lambda s, a: setattr(self, 'show_crosshair', a))
        dpg.add_checkbox(label="Linee Zona-Task", default_value=self.show_task_links,
                         callback=lambda s, a: setattr(self, 'show_task_links', a))
        dpg.add_checkbox(label="Mostra solo task in memoria", default_value=self.show_only_active_tasks,
                         callback=lambda s, a: setattr(self, 'show_only_active_tasks', a))                 
        dpg.add_checkbox(label="Altri giocatori (YOLO)", default_value=self.show_other_players,
                         callback=lambda s, a: setattr(self, 'show_other_players', a))
        dpg.add_checkbox(label="Porte chiuse rilevate (YOLO)", default_value=self.show_detected_doors,
                         callback=lambda s, a: setattr(self, 'show_detected_doors', a))
        with dpg.group(horizontal=True):
            dpg.add_slider_float(tag="yolo_cam_slider", default_value=self.yolo_camera_height,
                                 min_value=3.0, max_value=12.0, width=-130,
                                 callback=lambda s, a: setattr(self, 'yolo_camera_height', a))
            dpg.add_text("Cam Height")
        dpg.add_checkbox(label="Auto-calibra YOLO (movimento)", default_value=self.yolo_auto_calibrate,
                         callback=lambda s, a: setattr(self, 'yolo_auto_calibrate', a))
        dpg.add_checkbox(label="HUD overlay", default_value=self.show_hud,
                         callback=lambda s, a: setattr(self, 'show_hud', a))

        dpg.add_spacer(height=8)
        dpg.add_slider_float(label="Smoothing",
                             default_value=GPSConfig.SMOOTHING,
                             min_value=1.0, max_value=50.0, width=-80,
                             callback=lambda s, a: setattr(GPSConfig, 'SMOOTHING', a))

        dpg.add_spacer(height=10)
        dpg.add_separator()
        dpg.add_text("TASK", color=Colors.ACCENT)
        dpg.add_separator()
        dpg.add_button(label="Relazioni Padre ↔ Figlia",
                       width=-1, height=28,
                       callback=lambda *a: self._apri_popup_relazioni_task())

        # --- Memoria: task rilevate dal gioco ---
        with dpg.group(horizontal=True):
            dpg.add_text("Task in memoria:", color=Colors.TEXT_DIM)
            dpg.add_checkbox(label="A-Z", default_value=False, tag="sort_mem_tasks_chk", callback=lambda *a: self._refresh_mem_task_listbox())
        dpg.add_listbox(tag="mem_task_listbox", items=[], num_items=5, width=-1)
        with dpg.group(horizontal=True):
            dpg.add_button(label="Vai (A*)", width=85,
                           callback=lambda *a: self._naviga_a_task_memoria())
            dpg.add_button(label="Avvia Task", width=85,
                           callback=lambda *a: self._avvia_task_selezionata())
            dpg.add_button(label="Registra ?", width=80,
                           callback=lambda *a: self._registra_task_sconosciuta())
        dpg.add_button(label="▶ Esegui TUTTE le Task", width=-1, tag="btn_auto_all",
                       callback=lambda *a: self._toggle_auto_all())
        with dpg.group(horizontal=True):
            dpg.add_button(label="Modifica", width=120,
                           callback=lambda *a: self._modifica_task_da_memoria())
            dpg.add_button(label="⏹ Stop Task", width=120,
                           tag="btn_stop_task",
                           callback=lambda *a: self._ferma_processo_task())
            dpg.add_text("", tag="processo_status", color=(200, 200, 200, 200))

        dpg.add_spacer(height=8)
        dpg.add_separator()
        with dpg.group(horizontal=True):
            dpg.add_text("Task Registrate:", color=Colors.TEXT_DIM)
            dpg.add_checkbox(label="A-Z", default_value=False, tag="sort_reg_tasks_chk", callback=lambda *a: self._refresh_reg_task_listbox())
        dpg.add_listbox(tag="reg_task_listbox", items=[], num_items=5, width=-1)
        with dpg.group(horizontal=True):
            dpg.add_button(label="Nuova Task", width=125,
                           callback=lambda *a: self._apri_popup_nuova_task())
            dpg.add_button(label="Modifica", width=125,
                           callback=lambda *a: self._apri_popup_modifica_task())
        with dpg.group(horizontal=True):
            dpg.add_button(label="+ Fase", width=62,
                           callback=lambda *a: self._apri_popup_nuova_fase())
            dpg.add_button(label="+ Fratello", width=76,
                           callback=lambda *a: self._apri_popup_nuovo_fratello())
            dpg.add_button(label="Vai", width=55,
                           callback=lambda *a: self._naviga_a_task_registrata())
            dpg.add_button(label="Elimina", width=65,
                           callback=lambda *a: self._elimina_task_registrata())
        with dpg.group(horizontal=True):
            dpg.add_button(label="Genera .py", width=127,
                           tag="btn_genera_py",
                           callback=lambda *a: self._genera_file_esecuzione())
            dpg.add_text("", tag="genera_py_status", color=(0, 200, 120, 255))
        dpg.add_button(label="Link Zona ↔ Task", width=-1,
                       callback=lambda *a: self._apri_popup_link_zona())

        # ================== PUNTI DI INTERESSE ==================
        dpg.add_spacer(height=10)
        dpg.add_separator()
        dpg.add_text("PUNTI DI INTERESSE", color=(255, 160, 60, 255))
        dpg.add_separator()

        dpg.add_checkbox(label="Mostra sulla mappa", default_value=self.show_poi,
                         callback=lambda s, a: setattr(self, 'show_poi', a))
        dpg.add_listbox(tag="poi_listbox", items=[], num_items=5, width=-1)
        with dpg.group(horizontal=True):
            dpg.add_button(label="+ Nuovo POI", width=127,
                           callback=lambda *a: self._apri_popup_nuovo_poi())
            dpg.add_button(label="Modifica", width=123,
                           callback=lambda *a: self._apri_popup_modifica_poi())
        with dpg.group(horizontal=True):
            dpg.add_button(label="Vai (A*)", width=127,
                           callback=lambda *a: self._naviga_a_poi())
            dpg.add_button(label="Elimina", width=123,
                           callback=lambda *a: self._elimina_poi())

        dpg.add_spacer(height=10)
        dpg.add_separator()
        dpg.add_text("STATISTICHE", color=Colors.ACCENT)
        dpg.add_separator()
        dpg.add_text("Distanza percorsa:", color=Colors.TEXT_DIM)
        dpg.add_text("0.00 u", tag="stat_dist")
        dpg.add_text("Tempo sessione:", color=Colors.TEXT_DIM)
        dpg.add_text("00:00", tag="stat_time")
        dpg.add_text("Celle mappa:", color=Colors.TEXT_DIM)
        dpg.add_text(f"{len(self.visitati_coords)}", tag="stat_visited")
        dpg.add_text("Celle calpestabili:", color=Colors.TEXT_DIM)
        dpg.add_text(f"{len(self.pathfinder.walkable)}", tag="stat_walkable")
        dpg.add_text("Punti del trail:", color=Colors.TEXT_DIM)
        dpg.add_text("0", tag="stat_trail")

        dpg.add_spacer(height=10)
        dpg.add_separator()
        dpg.add_text("SCORCIATOIE", color=Colors.ACCENT)
        dpg.add_separator()
        dpg.add_text(
            "F / R / O = telecamera\n"
            "G / T / C / H / P = toggle layers\n"
            "M = abilita auto-move\n"
            "N = nuova zona\n"
            "F4 / FINE (END) = ferma esecuzione (globale)\n"
            "Click SX = destinazione (pathfinding)\n"
            "Click DX / ESC = annulla\n"
            "Rotellina = zoom\n"
            "Middle + drag = pan mappa",
            color=Colors.TEXT_DIM)

    def _setup_theme(self):
        with dpg.theme() as self.global_theme:
            with dpg.theme_component(dpg.mvAll):
                dpg.add_theme_color(dpg.mvThemeCol_WindowBg,       Colors.BG)
                dpg.add_theme_color(dpg.mvThemeCol_ChildBg,        Colors.BG)
                dpg.add_theme_color(dpg.mvThemeCol_MenuBarBg,      Colors.PANEL_BG)
                dpg.add_theme_color(dpg.mvThemeCol_PopupBg,        Colors.PANEL_BG)
                dpg.add_theme_color(dpg.mvThemeCol_Button,         (32, 32, 40, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered,  (0, 120, 200, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,   (0, 160, 230, 255))
                dpg.add_theme_color(dpg.mvThemeCol_FrameBg,        (28, 28, 34, 255))
                dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, (40, 40, 48, 255))
                dpg.add_theme_color(dpg.mvThemeCol_SliderGrab,     Colors.ACCENT)
                dpg.add_theme_color(dpg.mvThemeCol_CheckMark,      Colors.ACCENT)
                dpg.add_theme_color(dpg.mvThemeCol_Text,           Colors.TEXT)
                dpg.add_theme_color(dpg.mvThemeCol_Separator,      (60, 60, 70, 255))
                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding,  4)
                dpg.add_theme_style(dpg.mvStyleVar_WindowPadding,  6, 6)
                dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing,    6, 4)
        dpg.bind_theme(self.global_theme)

    # ================= SCANNER RADAR YOLO =================
    def _yolo_scanner_loop(self):
        """Gira in background per rilevare altri giocatori a schermo e mapparli sulle coordinate GPS."""
        try:
            from ultralytics import YOLO
            import mss
            import numpy as np
        except ImportError:
            return
            
        model_path = getattr(GPSConfig, 'YOLO_PLAYER_MODEL', 'yolo_players.pt')
        door_model_path = getattr(GPSConfig, 'YOLO_DOOR_MODEL', 'porte.pt')
        
        model = YOLO(model_path) if os.path.exists(model_path) else None
        door_model = YOLO(door_model_path) if os.path.exists(door_model_path) else None
        
        if model is None and door_model is None:
            return
        
        while self.running:
            # Sospende se non deve scansionare nulla
            if not self.show_other_players and not self.auto_enabled and door_model is None:
                time.sleep(0.5)
                continue
                
            hwnd = win32gui.FindWindow(None, "Among Us")
            if not hwnd:
                time.sleep(1.0)
                continue
                
            rect = win32gui.GetWindowRect(hwnd)
            crect = win32gui.GetClientRect(hwnd)
            bw = int((rect[2] - rect[0] - crect[2]) / 2)
            th = int(rect[3] - rect[1] - crect[3] - bw)
            wx, wy = rect[0] + bw, rect[1] + th
            ww, wh = crect[2], crect[3]
            
            if ww <= 0 or wh <= 0:
                time.sleep(0.5)
                continue
                
            with mss.mss() as sct:
                monitor = {"top": wy, "left": wx, "width": ww, "height": wh}
                try:
                    img = np.array(sct.grab(monitor))[:, :, :3]
                except Exception:
                    time.sleep(0.5)
                    continue
                    
            
            cx_screen, cy_screen = ww / 2, wh / 2

            # La dimensione ortografica standard di Unity per Among Us è solitamente 3.0 (6.0 in altezza totale)
            # Utilizziamo la variabile che può essere auto-calibrata dal movimento o aggiustata manualmente
            cam_h = getattr(self, 'yolo_camera_height', 6.0)
            pixels_per_unit = wh / cam_h
            
            # IMPORTANTE: La telecamera di gioco punta al petto del giocatore, non ai piedi. Offset di ~0.36 unità in su.
            camera_world_y = self.pos_target[1] + 0.36
            
            current_time = time.time()
            # --- RILEVAMENTO GIOCATORI ---
            if model and self.show_other_players:
                results = model(img, conf=0.85, verbose=False)
                boxes = results[0].boxes

                # --- AUTO CALIBRAZIONE BASATA SUL MODO DI MUOVERSI ---
                current_pos = tuple(self.pos_target)
                if getattr(self, 'yolo_auto_calibrate', False) and getattr(self, '_yolo_prev_pos', None):
                    prev_pos = self._yolo_prev_pos
                    prev_boxes = getattr(self, '_yolo_prev_boxes', [])
                    
                    dx_w = current_pos[0] - prev_pos[0]
                    dy_w = current_pos[1] - prev_pos[1]
                    dist_w = math.hypot(dx_w, dy_w)
                    
                    # Calibra solo se noi ci muoviamo e vediamo ESATTAMENTE un giocatore (per evitare mixup di ID)
                    if dist_w > 0.05 and len(boxes) == 1 and len(prev_boxes) == 1:
                        b_curr = boxes[0].xyxy[0].tolist()
                        b_prev = prev_boxes[0]
                        
                        # Ignoriamo noi stessi (se è al centro)
                        if math.hypot(((b_curr[0]+b_curr[2])/2) - cx_screen, ((b_curr[1]+b_curr[3])/2) - cy_screen) > (wh * 0.15):
                            cx_curr = (b_curr[0] + b_curr[2]) / 2
                            cy_curr = b_curr[3]
                            cx_prev = (b_prev[0] + b_prev[2]) / 2
                            cy_prev = b_prev[3]
                            
                            dx_p = cx_curr - cx_prev
                            dy_p = cy_curr - cy_prev
                            dist_p = math.hypot(dx_p, dy_p)
                            
                            # Se il giocatore avvistato si è spostato a schermo
                            if dist_p > 5:
                                calculated_ppu = dist_p / dist_w
                                calculated_h = wh / calculated_ppu
                                
                                # Filtro passa basso: diamo un piccolo peso al nuovo calcolo (smoothing 5%)
                                if 3.0 < calculated_h < 12.0:
                                    self.yolo_camera_height = self.yolo_camera_height * 0.95 + calculated_h * 0.05
                                    try:
                                        if dpg.does_item_exist("yolo_cam_slider"):
                                            dpg.set_value("yolo_cam_slider", self.yolo_camera_height)
                                    except Exception:
                                        pass

                self._yolo_prev_pos = current_pos
                self._yolo_prev_boxes = [box.xyxy[0].tolist() for box in boxes]

                new_detections = []
                
                for box in boxes:
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    center_x = (x1 + x2) / 2
                    center_y = (y1 + y2) / 2
                    
                    cls_id = int(box.cls[0]) if hasattr(box, 'cls') else 36
                    
                    YOLO_COLORS = {
                        0: ('Red', (197, 17, 17)), 1: ('Blue', (19, 46, 209)), 2: ('Green', (17, 127, 45)),
                        3: ('Pink', (237, 84, 186)), 4: ('Orange', (239, 125, 13)), 5: ('Yellow', (245, 245, 87)),
                        6: ('Black', (63, 71, 78)), 7: ('White', (214, 224, 240)), 8: ('Purple', (107, 47, 187)),
                        9: ('Brown', (113, 73, 30)), 10: ('Cyan', (56, 254, 220)), 11: ('Lime', (80, 239, 57)),
                        12: ('Maroon', (107, 43, 60)), 13: ('Rose', (236, 192, 211)), 14: ('Banana', (255, 255, 103)),
                        15: ('Gray', (113, 136, 144)), 16: ('Tan', (145, 136, 119)), 17: ('Coral', (215, 100, 100))
                    }
                    
                    if cls_id < 18:
                        color_name, player_col = YOLO_COLORS.get(cls_id, ('Unknown', (150, 150, 150)))
                        is_dead = False
                    elif cls_id < 36:
                        color_name, player_col = YOLO_COLORS.get(cls_id - 18, ('Unknown', (150, 150, 150)))
                        is_dead = True
                    elif cls_id == 36:
                        color_name, player_col = ('Unknown', (150, 150, 150))
                        is_dead = False
                    else: # 37 o fallback
                        color_name, player_col = ('Unknown', (150, 150, 150))
                        is_dead = True
                    
                    # Ignora il nostro giocatore usando il centro della box e un raggio dinamico (15% dell'altezza dello schermo)
                    if math.hypot(center_x - cx_screen, center_y - cy_screen) < (wh * 0.15):
                        continue
                        
                    px = center_x
                    py = y2  # Base del rettangolo (piedi esatti del giocatore rilevato)
                    
                    dx = px - cx_screen
                    dy = py - cy_screen
                    
                    world_x = self.pos_target[0] + (dx / pixels_per_unit)
                    world_y = camera_world_y - (dy / pixels_per_unit)  # Invertito perché la Y di gioco va verso l'alto
                    
                    # --- SNAP ALLA MAPPA CALPESTABILE (e filtro muri) ---
                    # Evita che i giocatori vengano renderizzati fuori dai muri o nel vuoto
                    if getattr(self, 'pathfinder', None) and self.pathfinder.walkable:
                        snapped_cell = self.pathfinder.nearest_walkable(world_x, world_y, radius=4)
                        if snapped_cell:
                            snap_x, snap_y = self.pathfinder._coord(snapped_cell)
                            # Se la detection cade troppo profondamente in un muro (dist > 1.2), è un falso positivo ambientale
                            if math.hypot(world_x - snap_x, world_y - snap_y) > 1.2:
                                continue
                            world_x, world_y = snap_x, snap_y
                        else:
                            # Troppo lontano (oltre ~1.2 mattonelle) dalle zone calpestabili
                            continue

                    # Estrazione fallback se la classe è sconosciuta
                    if color_name == 'Unknown':
                        perc_y = 0.5 if is_dead else 0.6
                        color_y = int(y1 + (y2 - y1) * perc_y)
                        color_x = int(center_x)
                        color_y = max(0, min(wh - 1, color_y))
                        color_x = max(0, min(ww - 1, color_x))
                        b, g, r = img[color_y, color_x]
                        player_col = (int(r), int(g), int(b))
                    
                    new_detections.append({
                        'x': world_x, 'y': world_y, 'time': current_time, 
                        'color': player_col, 'name': color_name, 'is_dead': is_dead
                    })
                    
                for nd in new_detections:
                    best_match = None
                    best_score = float('inf')
                    
                    for dp in self.detected_players:
                        dist = math.hypot(nd['x'] - dp['x'], nd['y'] - dp['y'])
                        time_diff = nd['time'] - dp['time']
                        
                        # Anti-Teleport: se la velocità richiesta è > 15 unità al secondo, non è lui
                        if time_diff > 0.1 and (dist / time_diff) > 15.0:
                            continue
                            
                        # Anti-Zombie: Se è segnato morto, non può essere vivo se dello stesso colore
                        if dp.get('is_dead', False) and not nd['is_dead']:
                            if dp.get('name') != 'Unknown' and nd['name'] == dp.get('name'):
                                continue
                                 
                        # 1. Match ESATTO della classe (colore univoco nel gioco)
                        if nd['name'] != 'Unknown' and nd['name'] == dp.get('name'):
                            best_match = dp
                            break
                            
                        # 2. Fallback per classi Unknown
                        if nd['name'] == 'Unknown' or dp.get('name') == 'Unknown':
                            c_diff = abs(nd['color'][0] - dp['color'][0]) + \
                                     abs(nd['color'][1] - dp['color'][1]) + \
                                     abs(nd['color'][2] - dp['color'][2])
                            if dist < 0.8 or (c_diff < 60 and dist < 5.0) or c_diff < 40:
                                score = (dist * 10) + c_diff
                                if score < best_score:
                                    best_score = score
                                    best_match = dp
                                
                    if best_match:
                        best_match['x'] = nd['x']
                        best_match['y'] = nd['y']
                        best_match['time'] = nd['time']
                        best_match['is_dead'] = nd['is_dead']
                        
                        if best_match.get('name') == 'Unknown' and nd['name'] != 'Unknown':
                            best_match['name'] = nd['name']
                            best_match['color'] = nd['color']
                        elif best_match.get('name') == 'Unknown':
                            best_match['color'] = (
                                int((best_match['color'][0] * 0.7) + (nd['color'][0] * 0.3)),
                                int((best_match['color'][1] * 0.7) + (nd['color'][1] * 0.3)),
                                int((best_match['color'][2] * 0.7) + (nd['color'][2] * 0.3))
                            )
                    else:
                        self.detected_players.append(nd)

                # Pulizia fantasmi: se guardiamo un punto e il player non c'è più, lo facciamo sparire
                view_radius = 4.5
                if len(new_detections) < 10:
                    for dp in self.detected_players:
                        if not dp.get('is_dead', False):
                            dist_cam = math.hypot(dp['x'] - self.pos_target[0], dp['y'] - self.pos_target[1])
                            if dist_cam < view_radius:
                                if not any(math.hypot(nd['x'] - dp['x'], nd['y'] - dp['y']) < 1.5 for nd in new_detections):
                                    dp['time'] -= 5.0  # Invecchia rapidamente
                                    
                # Rimuovi player troppo vecchi (30s) per non saturare la memoria
                self.detected_players = [dp for dp in self.detected_players if current_time - dp['time'] < 30.0 or dp.get('is_dead', False)]

            # --- RILEVAMENTO PORTE CHIUSE ---
            if door_model:
                door_results = door_model(img, conf=0.80, verbose=False)
                door_boxes = door_results[0].boxes
                new_doors = []
                
                for box in door_boxes:
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    center_x = (x1 + x2) / 2
                    center_y = (y1 + y2) / 2
                    
                    dx = center_x - cx_screen
                    dy = center_y - cy_screen
                    
                    world_x = self.pos_target[0] + (dx / pixels_per_unit)
                    world_y = camera_world_y - (dy / pixels_per_unit)
                    
                    # Filtro zone valide per le porte per scartare falsi positivi YOLO
                    valid_zone = False
                    if not self.door_zone_mgr.zone:
                        valid_zone = True # Se non hai disegnato zone, le accetta tutte
                    else:
                        for dz in self.door_zone_mgr.zone:
                            if self._is_point_in_polygon(world_x, world_y, dz.get('punti', [])):
                                valid_zone = True
                                break
                    if not valid_zone:
                        continue

                    new_doors.append({'x': world_x, 'y': world_y, 'time': current_time})
                
                for nd in new_doors:
                    matched = False
                    for d in getattr(self, 'detected_doors', []):
                        if math.hypot(nd['x'] - d['x'], nd['y'] - d['y']) < 1.5:
                            d['x'] = nd['x']
                            d['y'] = nd['y']
                            d['time'] = current_time
                            matched = True
                            break
                    if not matched:
                        if not hasattr(self, 'detected_doors'):
                            self.detected_doors = []
                        self.detected_doors.append(nd)
                
                self.detected_doors = [d for d in getattr(self, 'detected_doors', []) if current_time - d['time'] < 1.0]
            
            time.sleep(0.15)  # Circa ~6 FPS per lo scanning radar, per non appesantire la CPU

    # ================= CALLBACKS =================
    def _on_viewport_resize(self, *args):
        vp_w = dpg.get_viewport_client_width()
        vp_h = dpg.get_viewport_client_height()
        self.canvas_w = max(200, vp_w - GPSConfig.SIDE_PANEL_W - 20)
        self.canvas_h = max(200, vp_h - GPSConfig.STATUS_BAR_H - 60)
        dpg.configure_item("canvas", width=self.canvas_w, height=self.canvas_h)

    def _on_mouse_wheel(self, sender, app_data):
        if not dpg.is_item_hovered("canvas"): return
        factor = 1.15 if app_data > 0 else 1.0 / 1.15
        self._zoom(factor)

    def _on_middle_click(self, *args):
        if not dpg.is_item_hovered("canvas"): return
        if self.camera_mode == "follow":
            self.free_cam = list(self.pos_visuale)
            self.camera_mode = "free"
        self.is_panning = True
        self.pan_start_cam = tuple(self.free_cam)

    def _on_middle_drag(self, sender, app_data):
        if not self.is_panning: return
        _, dx, dy = app_data
        self.free_cam[0] = self.pan_start_cam[0] - dx / self.scale
        self.free_cam[1] = self.pan_start_cam[1] + dy / self.scale

    def _on_middle_release(self, *args):
        self.is_panning = False

    def _on_left_click(self, *args):
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

    def _on_left_drag(self, *args):
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

    def _on_left_release(self, *args):
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

            # --- NOVITÀ: ADATTAMENTO AUTOMATICO ---
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
            self.zone_draw_mode = False
            if nome:
                # Crea la zona con i punti già "puliti"
                self.zone_mgr.aggiungi(nome, punti_puliti)
                self._refresh_zone_list()
                self.auto_status_msg = f"Zona '{nome}' creata e adattata"
            else:
                self.auto_status_msg = "Annullato"

        self._show_text_input("Nuova Zona", "", on_name)

    def _mouse_to_game(self):
        mx, my = dpg.get_drawing_mouse_pos()
        cam_x, cam_y = self._camera_center()
        half_w = self.canvas_w / 2
        half_h = self.canvas_h / 2
        gx = cam_x + (mx - half_w) / self.scale
        gy = cam_y - (my - half_h) / self.scale
        return (gx, gy)

    def _is_point_in_polygon(self, x, y, poly):
        """Algoritmo Ray Casting per verificare se (x,y) è dentro il poligono."""
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

    def _plan_path(self, goal_xy):
        """Calcola A* assicurandosi che il target sia su una cella calpestabile."""
        # SNAP: Trova la cella calpestabile più vicina al click/centroide
        snapped_goal_key = self.pathfinder.nearest_walkable(goal_xy[0], goal_xy[1], GPSConfig.NEAREST_SEARCH_RADIUS)
        
        if snapped_goal_key is None:
            self.auto_path = []
            self.auto_path_index = 0
            self.auto_status_msg = "Punto irraggiungibile (non mappato)"
            self.key_ctrl.release_all()
            return

        # Usa le coordinate della cella reale come target finale
        actual_goal = self.pathfinder._coord(snapped_goal_key)
        self.auto_final_target = actual_goal 
        
        start = (self.pos_target[0], self.pos_target[1])
        t0 = time.time()
        
        # Calcola il percorso verso il punto "snappato"
        path = self.pathfinder.astar(start, actual_goal, max_nodes=GPSConfig.ASTAR_MAX_NODES)
        elapsed_ms = (time.time() - t0) * 1000

        if not path:
            self.auto_path = []
            self.auto_path_index = 0
            self.auto_status_msg = "In attesa (percorso bloccato)..."
            self.key_ctrl.release_all()
            return

        # Aggiungo il goal esatto come ultimo waypoint (per precisione finale
        # rispetto alla cella piu' vicina) SOLO se e' raggiungibile in linea
        # retta dal goal snapped — altrimenti il bot tenta di camminare nel
        # muro per arrivarci e va in loop di stuck/replan.
        if path:
            last = path[-1]
            dist_extra = math.hypot(last[0] - goal_xy[0], last[1] - goal_xy[1])
            if 0.05 < dist_extra < 1.0 and self.pathfinder.line_walkable_coords(last, goal_xy):
                path.append(goal_xy)

        self.auto_path = path
        self.auto_path_index = 0
        self.auto_stuck_pos = tuple(self.pos_target)
        self.auto_stuck_timer = 0.0
        self.auto_status_msg = f"Path: {len(path)} wp ({elapsed_ms:.0f}ms)"

    def _camera_center(self):
        if self.camera_mode == "follow":
            return (self.pos_visuale[0], self.pos_visuale[1])
        return (self.free_cam[0], self.free_cam[1])

    def _on_zoom_slider(self, sender, app_data):
        self.scale = max(GPSConfig.MIN_SCALE,
                         min(GPSConfig.MAX_SCALE, app_data))

    def _zoom(self, factor):
        self.scale = max(GPSConfig.MIN_SCALE,
                         min(GPSConfig.MAX_SCALE, self.scale * factor))
        if dpg.does_item_exist("zoom_slider"):
            dpg.set_value("zoom_slider", self.scale)

    def _toggle(self, attr):
        setattr(self, attr, not getattr(self, attr))

    def _on_toggle_visited(self, sender, app_data):
        self.show_visited = app_data
        dpg.configure_item("map_node", show=self.show_visited)

    def _set_camera(self, mode):
        self.camera_mode = mode
        if mode == "overview":
            self._fit_to_map()
        elif mode == "free":
            self.free_cam = list(self.pos_visuale)

    def _fit_to_map(self):
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
        self.scale = GPSConfig.DEFAULT_SCALE
        if dpg.does_item_exist("zoom_slider"):
            dpg.set_value("zoom_slider", self.scale)
        if self.camera_mode == "free":
            self.free_cam = list(self.pos_visuale)

    def _on_auto_checkbox(self, sender, app_data):
        self.auto_enabled = app_data
        if not app_data:
            self._cancel_auto_move(silent=True)

    def _toggle_auto_enabled(self):
        self.auto_enabled = not self.auto_enabled
        if dpg.does_item_exist("auto_checkbox"):
            dpg.set_value("auto_checkbox", self.auto_enabled)
        if not self.auto_enabled:
            self._cancel_auto_move(silent=True)
        else:
            self.auto_status_msg = "Pronto: clicca sulla mappa"

    def _cancel_auto_move(self, silent=False, stop_auto_all=True):
        self.auto_final_target = None
        self.auto_path = []
        self.auto_path_index = 0
        self.auto_is_2p_task = False
        self._task_fratelli_pendenti = None
        self.key_ctrl.release_all()
        
        if stop_auto_all:
            self.auto_execute_all = False
            self._current_auto_all_task_id = None
            if dpg.does_item_exist("btn_auto_all"):
                with dpg.theme() as th:
                    with dpg.theme_component(dpg.mvButton):
                        dpg.add_theme_color(dpg.mvThemeCol_Text, Colors.TEXT)
                dpg.bind_item_theme("btn_auto_all", th)
                dpg.configure_item("btn_auto_all", label="▶ Esegui TUTTE le Task")
            
        if not silent:
            self.auto_status_msg = "Annullato"

    def _cancel_all(self):
        """Annulla sia il disegno/modifica zona sia il pathfinding."""
        if (self.zone_draw_mode or self.zone_draw_points
                or getattr(self, 'door_rect_start', None)
                or self.zona_in_modifica is not None):
            self.zone_draw_mode = False
            self.zone_draw_type = "normal"
            self.zone_draw_points = []
            self.door_rect_start = None
            self.door_rect_end = None
            self.zone_last_pixel = None
            self.zona_in_modifica = None
            self.auto_status_msg = "Disegno zona annullato"
        self._cancel_auto_move()
        
    def _get_task_target_coords(self, reg_task):
        """
        Calcola la coordinata bersaglio esatta di una task in base allo step 
        registrato in memoria (es: se siamo a 1/2, naviga alla fase 0).
        Ritorna (x, y, step).
        """
        x, y = reg_task['x'], reg_task['y']
        step = 0
        # Cerca lo step attuale in RAM
        for mt in getattr(self, 'memory_tasks', []):
            if mt.get('tipo') == reg_task.get('tipo') and mt.get('room_id') == reg_task.get('room_id'):
                try:
                    step = int(mt['prog'].split('/')[0])
                except: pass
                break
                
        fasi = reg_task.get('fasi', [])
        # Se lo step è maggiore di 0 e c'è una fase mappata corrispondente
        if step > 0 and step <= len(fasi):
            x, y = fasi[step - 1]['x'], fasi[step - 1]['y']
            
        return x, y, step

    def _imposta_navigazione_2p(self, reg):
        """
        Prepara la logica di navigazione per le task a 2 giocatori. 
        Ritorna la coordinata (x,y) iniziale ottimale (la più vicina).
        """
        self.auto_is_2p_task = False
        if reg.get('due_giocatori'):
            loc_A = (reg['x'], reg['y'])
            loc_B = None
            if reg.get('fasi') and len(reg['fasi']) > 0:
                loc_B = (reg['fasi'][0]['x'], reg['fasi'][0]['y'])

            if loc_B:
                self.auto_is_2p_task = True
                self.auto_2p_loc_A = loc_A
                self.auto_2p_loc_B = loc_B
                self._2p_last_switch_time = 0.0

                start_pos = (self.pos_target[0], self.pos_target[1])
                
                # Calcola il percorso reale (A*) per capire quale è effettivamente più vicino
                path_A = self.pathfinder.astar(start_pos, loc_A)
                path_B = self.pathfinder.astar(start_pos, loc_B)
                
                def calc_len(p):
                    if not p: return float('inf')
                    if len(p) < 2: return 0.0
                    return sum(math.hypot(p[i+1][0]-p[i][0], p[i+1][1]-p[i][1]) for i in range(len(p)-1))
                
                dist_A = calc_len(path_A)
                dist_B = calc_len(path_B)

                if dist_A <= dist_B and dist_A != float('inf'):
                    target = loc_A
                    step = 0
                elif dist_B < float('inf'):
                    target = loc_B
                    step = 1
                else:
                    # Fallback alla distanza in linea d'aria se non ancora mappato
                    d_A = math.hypot(start_pos[0]-loc_A[0], start_pos[1]-loc_A[1])
                    d_B = math.hypot(start_pos[0]-loc_B[0], start_pos[1]-loc_B[1])
                    target = loc_A if d_A <= d_B else loc_B
                    step = 0 if target == loc_A else 1
                    
                self.auto_2p_current_target = target
                return target, step
        return None, None

    def _toggle_auto_all(self):
        """Attiva o disattiva l'esecuzione automatica in loop di tutte le task."""
        self.auto_execute_all = not self.auto_execute_all
        if self.auto_execute_all:
            with dpg.theme() as th:
                with dpg.theme_component(dpg.mvButton):
                    dpg.add_theme_color(dpg.mvThemeCol_Text, (0, 255, 100, 255))
            dpg.bind_item_theme("btn_auto_all", th)
            dpg.configure_item("btn_auto_all", label="⏹ Ferma Esecuzione Totale")
            self.auto_status_msg = "Auto-All attivato: cerco task..."
            self._auto_all_timer = 1.0 # Forza il check immediato
        else:
            self._cancel_auto_move()
            self._ferma_processo_task()

    def _update_auto_all(self, dt):
        """Loop logico dell'Auto-Quest: sceglie e avvia la prossima task se libero."""
        if not self.auto_execute_all:
            return

        # Se il bot sta viaggiando verso una task, eseguendo una task o gestendo popup: aspetta
        if self.auto_path or self._task_process is not None or getattr(self, '_task_launch_arrivo', False):
            return
        if dpg.does_item_exist("task_launch_popup"):
            return

        self._auto_all_timer += dt
        if self._auto_all_timer < 1.0: # Check throttling (1 secondo)
            return
        self._auto_all_timer = 0.0

        if not self.memory_tasks:
            return

        enriched = self.task_mgr.get_memory_tasks_info(self.memory_tasks)
        candidati = []
        in_cooldown = 0
        non_registrate = 0

        for t in enriched:
            if t['done']: continue
            reg = t.get('reg_task')
            if not reg:
                non_registrate += 1
                continue
            rem = self.task_cooldowns.get(reg['id'], 0) - time.time()
            if rem > 0:
                in_cooldown += 1
                continue
            candidati.append(t)

        if not candidati:
            if non_registrate > 0:
                self.auto_status_msg = f"Auto-All in attesa: {non_registrate} task NON registrate."
            elif in_cooldown > 0:
                self.auto_status_msg = f"Auto-All in attesa: {in_cooldown} task in cooldown..."
            else:
                self.auto_status_msg = "Tutte le task completate! Vittoria!"
                self._toggle_auto_all()
            return

        # Trova la task valida PIÙ VICINA
        cx, cy = self.pos_target
        closest = None
        min_dist = float('inf')
        for c in candidati:
            rx, ry = c['reg_task']['x'], c['reg_task']['y']
            dist = math.hypot(cx - rx, cy - ry)
            if dist < min_dist:
                min_dist = dist
                closest = c
                
        if closest:
            print(f"[Auto-All] Scelta task più vicina: {closest['reg_task']['nome']} (Dist: {min_dist:.1f})")
            self._avvia_task_selezionata(task_to_run=closest)

    def _check_2p_yolo_thread(self, current_target_is_A):
        """Esegue l'analisi YOLO asincrona per vedere se il pannello è occupato da un altro player."""
        if getattr(self, '_2p_yolo_active', False): return
        self._2p_yolo_active = True
        try:
            import mss
            import numpy as np
            from ultralytics import YOLO
            import os
            import win32gui

            if not getattr(self, 'yolo_player_loaded', False):
                model_path = getattr(GPSConfig, 'YOLO_PLAYER_MODEL', 'yolo_players.pt')
                if os.path.exists(model_path):
                    self.yolo_player = YOLO(model_path)
                else:
                    self.yolo_player = None
                    print(f"[YOLO 2P] Modello non trovato: {model_path}")
                self.yolo_player_loaded = True

            if getattr(self, 'yolo_player', None) is None:
                self._2p_yolo_active = False
                return

            hwnd = win32gui.FindWindow(None, "Among Us")
            if not hwnd:
                self._2p_yolo_active = False
                return

            rect = win32gui.GetWindowRect(hwnd)
            crect = win32gui.GetClientRect(hwnd)
            bw = int((rect[2] - rect[0] - crect[2]) / 2)
            th = int(rect[3] - rect[1] - crect[3] - bw)
            wx, wy = rect[0] + bw, rect[1] + th
            ww, wh = crect[2], crect[3]

            with mss.mss() as sct:
                monitor = {"top": wy, "left": wx, "width": ww, "height": wh}
                img = np.array(sct.grab(monitor))[:, :, :3]

            results = self.yolo_player(img, conf=0.75, verbose=False)
            boxes = results[0].boxes

            # Cerca player che non siamo noi (il nostro player è al centro dello schermo)
            other_players_found = False
            cx_screen, cy_screen = ww / 2, wh / 2

            for box in boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                px = (x1 + x2) / 2
                py = (y1 + y2) / 2

                # Tolleranza di 70px dal centro; se è oltre, è sicuramente un altro giocatore
                dist_from_center = math.hypot(px - cx_screen, py - cy_screen)
                if dist_from_center > 70:
                    other_players_found = True
                    break

            if other_players_found:
                new_target = self.auto_2p_loc_B if current_target_is_A else self.auto_2p_loc_A
                
                if new_target and new_target != self.auto_2p_current_target:
                    self.auto_2p_current_target = new_target
                    self._pending_2p_replan = new_target
                    print(f"[YOLO 2P] Player rilevato al pannello! Spostamento alla seconda postazione.")

        except Exception as e:
            print(f"[YOLO 2P] Errore: {e}")
        finally:
            self._2p_yolo_active = False

    # ================= GESTIONE ZONE =================
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
        self.auto_status_msg = "Trascina col tasto sinistro per disegnare il poligono"

    def _start_new_door_zone_mode(self):
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
        self.auto_status_msg = "Trascina col tasto sinistro per creare la Zona Porta"

    def _refresh_zone_list(self):
        items = []
        for z in self.zone_mgr.zone:
            gzid = z.get('game_zone_id')
            id_str = f" GZ:{gzid}" if gzid is not None else ""
            items.append(f"[{z['id']:02d}]{id_str} {z['nome']}")
        if dpg.does_item_exist("zone_listbox"):
            dpg.configure_item("zone_listbox", items=items)

    def _get_selected_zone(self):
        """Ritorna la zona selezionata nella listbox, oppure None."""
        if not self.zone_mgr.zone:
            return None
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
        items = []
        for z in self.door_zone_mgr.zone:
            items.append(f"[{z['id']:02d}] {z['nome']}")
        if dpg.does_item_exist("door_zone_listbox"):
            dpg.configure_item("door_zone_listbox", items=items)

    def _get_selected_door_zone(self):
        if not self.door_zone_mgr.zone: return None
        if not dpg.does_item_exist("door_zone_listbox"): return None
        sel = dpg.get_value("door_zone_listbox")
        if not sel: return None
        try:
            id_num = int(sel.split(']')[0].lstrip('[').strip())
            return next((z for z in self.door_zone_mgr.zone if z['id'] == id_num), None)
        except: return None

    def _elimina_door_zone(self):
        z = self._get_selected_door_zone()
        if z is None: return
        def on_confirm(yes):
            if yes:
                self.door_zone_mgr.rimuovi(z['id'])
                self._refresh_door_zone_list()
        self._show_confirm(f"Eliminare Zona Porta '{z['nome']}'?", on_confirm)

    def _vai_a_door_zona(self):
        z = self._get_selected_door_zone()
        if z is None:
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
            if dpg.does_item_exist("zoom_slider"):
                dpg.set_value("zoom_slider", self.scale)
        self.auto_status_msg = f"Centrato su '{z['nome']}'"

    def _modifica_forma_door_zona(self):
        z = self._get_selected_door_zone()
        if z is None:
            self.auto_status_msg = "Seleziona una zona porta dalla lista"
            return
        self.zona_in_modifica = z['id']
        self.zone_draw_mode = True
        self.zone_draw_type = "door"
        self.zone_draw_points = []
        self.door_rect_start = None
        self.door_rect_end = None
        self.zone_last_pixel = None
        self.auto_status_msg = f"Ridisegna '{z['nome']}' trascinando un rettangolo"

    def _cambia_colore_door_zona(self):
        z = self._get_selected_door_zone()
        if z is None:
            self.auto_status_msg = "Seleziona una zona porta dalla lista"
            return
        tag = "color_picker_popup_door"
        if dpg.does_item_exist(tag):
            dpg.delete_item(tag)

        def pick(col_hex):
            self.door_zone_mgr.cambia_colore(z['id'], col_hex)
            self._refresh_door_zone_list()
            self.auto_status_msg = f"Colore di '{z['nome']}' aggiornato"
            if dpg.does_item_exist(tag):
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
                           callback=lambda *a: dpg.delete_item(tag) if dpg.does_item_exist(tag) else None)

    def _rinomina_door_zona(self):
        z = self._get_selected_door_zone()
        if z is None:
            self.auto_status_msg = "Seleziona una zona porta dalla lista"
            return
        def on_name(nuovo):
            if nuovo:
                self.door_zone_mgr.rinomina(z['id'], nuovo)
                self._refresh_door_zone_list()
                self.auto_status_msg = f"Zona porta rinominata in '{nuovo}'"
        self._show_text_input("Rinomina Zona Porta", z['nome'], on_name)

    def _vai_a_zona(self):
        """Centra la camera sulla zona selezionata e adatta lo zoom."""
        z = self._get_selected_zone()
        if z is None:
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
            if dpg.does_item_exist("zoom_slider"):
                dpg.set_value("zoom_slider", self.scale)
        self.auto_status_msg = f"Centrato su '{z['nome']}'"

    def _naviga_a_zona(self):
        """Usa A* per muovere il player verso il miglior punto calpestabile della zona."""
        z = self._get_selected_zone()
        if z is None:
            self.auto_status_msg = "Seleziona una zona dalla lista"
            return
        
        if not self.auto_enabled:
            self.auto_enabled = True
            if dpg.does_item_exist("auto_checkbox"):
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
            # Scegliamo il punto calpestabile più vicino al centro della zona
            target = min(walkable_in_zone, key=lambda p: math.hypot(p[0]-cx_geom, p[1]-cy_geom))
            self._plan_path(target)
            self.auto_status_msg = f"Navigazione interna a '{z['nome']}'"
        else:
            # Se la zona non è stata ancora esplorata/mappata, fallback al centroide
            # ma il pathfinder cercherà comunque la cella calpestabile esterna più vicina.
            self._plan_path((cx_geom, cy_geom))
            self.auto_status_msg = f"Zona '{z['nome']}' non mappata: vado al confine"

    def _modifica_forma_zona(self):
        """Entra in modalita' ridisegna-forma per la zona selezionata."""
        z = self._get_selected_zone()
        if z is None:
            self.auto_status_msg = "Seleziona una zona dalla lista"
            return
        self.zona_in_modifica = z['id']
        self.zone_draw_mode = True
        self.zone_draw_points = []
        self.zone_last_pixel = None
        self.auto_status_msg = f"Ridisegna '{z['nome']}' col tasto sinistro"

    def _cambia_colore_zona(self):
        """Apre un popup con la palette per scegliere il nuovo colore."""
        z = self._get_selected_zone()
        if z is None:
            self.auto_status_msg = "Seleziona una zona dalla lista"
            return
        self._show_color_picker(z)
    
    def _forza_adattamento_zona(self):
        """Prende la zona selezionata e la modella sulla mappa attuale."""
        z = self._get_selected_zone()
        if z is None:
            self.auto_status_msg = "Seleziona una zona"
            return
        
        nuovi_punti = self._adatta_punti_alla_mappa(z['punti'])
        self.zone_mgr.aggiorna_forma(z['id'], nuovi_punti)
        self.auto_status_msg = f"Forma di '{z['nome']}' ottimizzata"

    def _rinomina_zona(self):
        z = self._get_selected_zone()
        if z is None:
            self.auto_status_msg = "Seleziona una zona dalla lista"
            return
        def on_name(nuovo):
            if nuovo:
                self.zone_mgr.rinomina(z['id'], nuovo)
                self._refresh_zone_list()
                self.auto_status_msg = f"Zona rinominata in '{nuovo}'"
        self._show_text_input("Rinomina Zona", z['nome'], on_name)

    def _elimina_zona(self):
        z = self._get_selected_zone()
        if z is None:
            self.auto_status_msg = "Seleziona una zona dalla lista"
            return
        nome = z['nome']
        id_zona = z['id']
        def on_confirm(yes):
            if yes:
                self.zone_mgr.rimuovi(id_zona)
                self._refresh_zone_list()
                self.auto_status_msg = f"Zona '{nome}' eliminata"
        self._show_confirm(f"Eliminare la zona '{nome}' ?", on_confirm)

    # ================= GESTIONE TASK =================

    def _refresh_mem_task_listbox(self):
        """
        Aggiorna la listbox task in memoria senza il match ID.
        Formato: [STATO] [ID:ROOM_ID] LUOGO: NOME TASK [PROG] (COORD)
        """
        enriched = self.task_mgr.get_memory_tasks_info(self.memory_tasks)
        
        if dpg.does_item_exist("sort_mem_tasks_chk") and dpg.get_value("sort_mem_tasks_chk"):
            enriched.sort(key=lambda x: (x['reg_task']['nome'] if x.get('reg_task') else x['nome']).lower())
            
        items = []
        for t in enriched:
            # Stato: [V] completata, [-] in corso
            stato = "[V]" if t['done'] else "[-]"
            room_id = t.get('room_id', '?')
            reg = t['reg_task']
            
            if reg:
                # Controllo Cooldown
                cd = self.task_cooldowns.get(reg['id'], 0)
                rem = cd - time.time()
                
                # Task Registrata: Formato "Luogo: Nome Task"
                # Puliamo il nome da eventuali prefissi doppi
                nome_pulito = reg['nome'].split(": ", 1)[-1]
                luogo = reg.get('zone_nome', 'Mappa')
                display_name = f"{luogo}: {nome_pulito}"
                
                coord_str = f" ({reg['x']:.1f},{reg['y']:.1f})"
                
                if rem > 0:
                    items.append(f"[WAIT {int(rem)}s] [ID:{room_id}] {display_name} [{t['prog']}]{coord_str}")
                else:
                    items.append(f"{stato} [ID:{room_id}] {display_name} [{t['prog']}]{coord_str}")
            else:
                # Task Sconosciuta: Nome base dalla RAM
                items.append(f"{stato} [ID:{room_id}] {t['nome']} [{t['prog']}]")
                
        if dpg.does_item_exist("mem_task_listbox"):
            dpg.configure_item("mem_task_listbox", items=items)

    def _refresh_reg_task_listbox(self):
        """
        Aggiorna la listbox delle task registrate dall'utente con tutti i
        dettagli rilevanti: flag vitale/due-giocatori, zona, numero fasi,
        e SOPRATTUTTO il legame padre/figlia (sia da che a) e l'origine
        delle azioni (proprie o ereditate).

        Formato riga:
            [ID] [!][2P] Nome  A:N  +Nf  [Z:gzid=nome]  ↳P:XX  +Nfigli
        dove:
            A:N      = numero azioni proprie
            A:0←PXX  = questa task non ha azioni proprie e le eredita da XX
            ↳P:XX    = questa task è FIGLIA di XX (indipendente dal fatto che
                       erediti o meno: può anche avere azioni proprie)
            +Nfigli  = questa task è PADRE di N task figlie
        """
        items = []
        
        tasks_to_render = list(self.task_mgr.task_list)
        if dpg.does_item_exist("sort_reg_tasks_chk") and dpg.get_value("sort_reg_tasks_chk"):
            tasks_to_render.sort(key=lambda x: x['nome'].lower())
            
        for t in tasks_to_render:
            vitale_str = " [!]" if t.get('vitale') else ""
            due_p_str  = " [2P]" if t.get('due_giocatori') else ""
            custom_str = " [C]" if t.get('codice_custom') else ""

            # Fasi
            n_fasi   = len(t.get('fasi', []))
            fasi_str = f" +{n_fasi}f" if n_fasi else ""
            
            # Fratelli
            n_frat   = len(t.get('fratelli', []))
            frat_str = f" ~{n_frat}fr" if n_frat else ""

            # Zona
            zone_id  = t.get('zone_id')
            zona_str = ""
            if zone_id is not None:
                z = self.zone_mgr.get_by_game_zone_id(zone_id)
                zona_str = f" [Z:{zone_id}={z['nome'] if z else '?'}]"

            # Azioni: numero proprie + eventuale ereditarietà
            n_azioni_proprie = len(t.get('azioni', []))
            if n_azioni_proprie > 0:
                azioni_str = f" A:{n_azioni_proprie}"
            else:
                # Nessuna azione propria: controllo se eredita dal padre
                _, src_id = self.task_mgr.get_azioni_effettive(t['id'])
                if src_id is not None and src_id != t['id']:
                    azioni_str = f" A:0←P{src_id:02d}"
                else:
                    azioni_str = " A:0"

            # Relazioni padre/figlia
            parent_str  = ""
            parent_id   = t.get('parent_id')
            if parent_id is not None:
                padre = self.task_mgr.get_by_id(parent_id)
                parent_nome = (padre['nome'].split(": ", 1)[-1][:15]
                               if padre else '?')
                parent_str = f"  ↳P:{parent_id:02d}({parent_nome})"

            # Task padre di quante figlie?
            figli = self.task_mgr.get_figli(t['id'])
            figli_str = f"  +{len(figli)}figli" if figli else ""

            items.append(
                f"[{t['id']:02d}]{vitale_str}{due_p_str}{custom_str} {t['nome']}"
                f"{azioni_str}{fasi_str}{frat_str}{zona_str}{parent_str}{figli_str}"
            )

        if dpg.does_item_exist("reg_task_listbox"):
            dpg.configure_item("reg_task_listbox", items=items)

    def _get_selected_mem_task(self):
        """
        Ritorna la task RAM selezionata ricostruendo la stringa esatta per il match.
        """
        if not self.memory_tasks:
            return None
        if not dpg.does_item_exist("mem_task_listbox"):
            return None
        
        sel = dpg.get_value("mem_task_listbox")
        if not sel:
            return None
            
        enriched = self.task_mgr.get_memory_tasks_info(self.memory_tasks)
        for t in enriched:
            stato = "[V]" if t['done'] else "[-]"
            room_id = t.get('room_id', '?')
            reg = t['reg_task']
            
            if reg:
                # Sincronizza il prefisso WAIT per far combaciare correttamente la stringa
                cd = self.task_cooldowns.get(reg['id'], 0)
                rem = cd - time.time()
                
                nome_pulito = reg['nome'].split(": ", 1)[-1]
                luogo = reg.get('zone_nome', 'Mappa')
                display_name = f"{luogo}: {nome_pulito}"
                coord_str = f" ({reg['x']:.1f},{reg['y']:.1f})"
                
                if rem > 0:
                    item_str = f"[WAIT {int(rem)}s] [ID:{room_id}] {display_name} [{t['prog']}]{coord_str}"
                else:
                    item_str = f"{stato} [ID:{room_id}] {display_name} [{t['prog']}]{coord_str}"
            else:
                item_str = f"{stato} [ID:{room_id}] {t['nome']} [{t['prog']}]"
                
            if item_str == sel:
                return t
                
        return None

    def _get_selected_reg_task(self):
        if not self.task_mgr.task_list:
            return None
        if not dpg.does_item_exist("reg_task_listbox"):
            return None
        sel = dpg.get_value("reg_task_listbox")
        if not sel:
            return None
        try:
            id_str = sel.split(']')[0].lstrip('[').strip()
            id_num = int(id_str)
            return self.task_mgr.get_by_id(id_num)
        except (ValueError, IndexError):
            return None

    def _naviga_a_task_memoria(self, task_to_nav=None):
        """Naviga con A* verso la task in memoria selezionata, usando le coordinate registrate."""
        t = task_to_nav if task_to_nav is not None else self._get_selected_mem_task()
        if t is None:
            self.auto_status_msg = "Seleziona una task dalla lista memoria"
            return
        reg = t.get('reg_task')
        if reg is None:
            self.auto_status_msg = f"Task '{t['nome']}' non ancora registrata — aggiungila prima"
            return
            
        # Controllo Cooldown
        rem = self.task_cooldowns.get(reg['id'], 0) - time.time()
        if rem > 0:
            self.auto_status_msg = f"Task in cooldown. Riprova tra {int(rem)}s"
            return
            
        if not self.auto_enabled:
            self.auto_enabled = True
            if dpg.does_item_exist("auto_checkbox"):
                dpg.set_value("auto_checkbox", True)
        
        target_2p, step_2p = self._imposta_navigazione_2p(reg)
        if target_2p:
            self._plan_path(target_2p)
            self.auto_status_msg = f"Navigo verso '{reg['nome']}' (Tappa {step_2p})"
        else:
            punti_possibili = [(reg['x'], reg['y'])]
            for fr in reg.get('fratelli', []):
                punti_possibili.append((fr['x'], fr['y']))
                
            if len(punti_possibili) > 1:
                self._task_fratelli_pendenti = punti_possibili
                cx, cy = self.pos_target
                closest = min(punti_possibili, key=lambda p: math.hypot(cx - p[0], cy - p[1]))
                tx, ty = closest
                self.auto_status_msg = f"Navigo verso '{reg['nome']}' (Cerco lock visivo...)"
            else:
                self._task_fratelli_pendenti = None
                tx, ty, step = self._get_task_target_coords(reg)
                self.auto_status_msg = f"Navigo verso '{reg['nome']}'"
                
            self._plan_path((tx, ty))

    def _modifica_task_da_memoria(self):
        """
        Apre il popup di modifica per la task REGISTRATA collegata alla task
        in memoria attualmente selezionata.
        Utile per modificare nome, coordinate, azioni, padre/figlia ecc. senza
        dover prima trovare manualmente la corrispondente voce nella lista
        delle task registrate.
        Se la task in memoria non è ancora registrata, suggerisce di usare
        prima il pulsante 'Registra ?'.
        """
        t = self._get_selected_mem_task()
        if t is None:
            self.auto_status_msg = "Seleziona una task dalla lista memoria"
            return
        reg = t.get('reg_task')
        if reg is None:
            self.auto_status_msg = (
                f"'{t['nome']}' non è ancora registrata — "
                f"usa 'Registra ?' per aggiungere i dettagli, "
                f"poi potrai modificarla qui."
            )
            return
        # Apre il popup di modifica passando la task registrata direttamente,
        # senza bisogno di selezionarla prima nella listbox delle registrate.
        self._apri_popup_modifica_task(task=reg)

    def _avvia_task_selezionata(self, task_to_run=None):
        """
        Flusso coerente in 3 fasi:
          FASE 1 — Predisposizione (immediata):
            Crea/verifica il file .py, mostra popup con log di setup,
            poi avvia la navigazione A* verso la task.
          FASE 2 — In viaggio:
            Il popup rimane aperto e mostra "In viaggio verso X...".
            Il player cammina automaticamente verso la task.
          FASE 3 — Arrivo + Esecuzione:
            Appena il player arriva, il popup aggiorna con gli step di lancio
            (animazione breve), poi avvia il subprocess e si chiude.
        """
        t = task_to_run if task_to_run is not None else self._get_selected_mem_task()
        if t is None:
            self.auto_status_msg = "Seleziona una task da avviare"
            return

        nome    = t['nome']
        reg     = t.get('reg_task')
        id_task = reg['id'] if reg else None

        if reg is None:
            self.auto_status_msg = f"'{nome}' non registrata — aggiungila prima"
            return
            
        self._current_auto_all_task_id = id_task
            
        # Controllo Cooldown
        rem = self.task_cooldowns.get(id_task, 0) - time.time()
        if rem > 0:
            self.auto_status_msg = f"Task in cooldown. Riprova tra {int(rem)}s"
            return

        tag = "task_launch_popup"
        if dpg.does_item_exist(tag):
            dpg.delete_item(tag)

        # ── FASE 1: predisposizione (sincrona, prima di aprire il popup) ──
        filepath, pred_log = self.task_mgr.predisponi_esecuzione(id_task)

        # Avvia navigazione A*
        if not self.auto_enabled:
            self.auto_enabled = True
            if dpg.does_item_exist("auto_checkbox"):
                dpg.set_value("auto_checkbox", True)
        
        target_2p, step_2p = self._imposta_navigazione_2p(reg)
        if target_2p:
            self._plan_path(target_2p)
        else:
            punti_possibili = [(reg['x'], reg['y'])]
            for fr in reg.get('fratelli', []):
                punti_possibili.append((fr['x'], fr['y']))
                
            if len(punti_possibili) > 1:
                self._task_fratelli_pendenti = punti_possibili
                cx, cy = self.pos_target
                closest = min(punti_possibili, key=lambda p: math.hypot(cx - p[0], cy - p[1]))
                tx, ty = closest
            else:
                self._task_fratelli_pendenti = None
                tx, ty, step = self._get_task_target_coords(reg)
                
            self._plan_path((tx, ty))

        # ── Apri popup con log di setup + messaggio "in viaggio" ──
        setup_lines = "\n".join(pred_log)
        viaggio_txt = f"{setup_lines}\n\n>> Navigazione verso '{nome}'...\n>> In attesa di arrivo..."

        vp_w = dpg.get_viewport_client_width()
        vp_h = dpg.get_viewport_client_height()

        with dpg.window(label=f"Task: {nome}", tag=tag,
                        modal=True, no_resize=True, no_collapse=True,
                        no_close=True,
                        width=440, height=260,
                        pos=(max(0, vp_w // 2 - 220),
                             max(0, vp_h // 2 - 130))):
            dpg.add_text(viaggio_txt, tag="task_launch_popup_text",
                         color=(0, 200, 255, 255), wrap=420)

        # Disabilita l'animazione a step (il popup è già pieno di testo)
        self.task_launch_active = False
        self._task_launch_nome  = nome
        self._task_launch_id    = id_task
        self._task_fallback_idx = 0

        # ── FASE 2→3: callback all'arrivo ──
        def on_arrivo():
            """Chiamato da _update_auto_move quando il player raggiunge la task."""
            if not dpg.does_item_exist("task_launch_popup_text"):
                self._avvia_subprocess_task(id_task)
                return

            time.sleep(0.3) # pausa per stabilità visiva (frame capture screen)

            # --- CHECK VISUALE (Use Button / Alone Giallo) ---
            curr_target = getattr(self, '_current_nav_target', (tx, ty))
            if not self._controlla_task_attiva(curr_target[0], curr_target[1]):
                fratelli = reg.get('fratelli', [])
                curr_fratello = getattr(self, '_task_fratello_idx', 0)
                if curr_fratello < len(fratelli):
                    next_target = (fratelli[curr_fratello]['x'], fratelli[curr_fratello]['y'])
                    self._task_fratello_idx = curr_fratello + 1
                    self.auto_status_msg = f"Task non attiva qui, navigo al fratello {self._task_fratello_idx}..."
                    print(f"[Visual Check] Niente USE o alone giallo. Navigo a fratello: {next_target}")
                    self._current_nav_target = next_target
                    self._plan_path(next_target)
                    self._on_arrival_callback = on_arrivo
                    return
                else:
                    print(f"[Visual Check] Nessun fratello rimanente o tutti inattivi, procedo comunque.")

            # Aggiorna popup con gli step di lancio animati
            self._task_launch_steps     = (TaskManager.STATI_LAUNCH
                                           + [f">> '{nome}' IN ESECUZIONE ★"])
            self._task_launch_timer_arr = 0.0
            self._task_launch_arrivo    = True  # flag: siamo in fase 3
            dpg.configure_item("task_launch_popup_text", color=(0, 220, 120, 255))
            self.auto_status_msg = f"Arrivato a '{nome}' — avvio in corso..."

        self._current_nav_target = target_2p if target_2p else (tx, ty)
        self._task_fratello_idx = 0
        self._on_arrival_callback   = on_arrivo
        self._task_launch_arrivo    = False
        self._task_launch_timer_arr = 0.0
        self.auto_status_msg        = f"In viaggio verso '{nome}'..."

    def _update_task_launch(self, dt):
        """
        Gestisce l'animazione del popup nelle due fasi attive:
        - Fase 3 (arrivo): anima gli step di lancio e poi avvia il subprocess.
        (La fase 1 popola il popup in modo statico, nessuna animazione.)
        """
        if not getattr(self, '_task_launch_arrivo', False):
            return

        self._task_launch_timer_arr += dt
        steps    = self._task_launch_steps
        interval = 0.4
        idx      = min(int(self._task_launch_timer_arr / interval), len(steps))

        log_text = "\n".join(steps[:idx])
        if dpg.does_item_exist("task_launch_popup_text"):
            dpg.set_value("task_launch_popup_text", log_text)

        # Dopo aver mostrato tutti gli step + 1s di pausa: avvia subprocess e chiudi
        close_at = len(steps) * interval + 1.0
        if self._task_launch_timer_arr >= close_at:
            self._task_launch_arrivo = False
            if dpg.does_item_exist("task_launch_popup"):
                dpg.delete_item("task_launch_popup")

            # --- PREMUTA DELLA BARRA SPAZIATRICE ---
            # Simula la pressione di SPAZIO per far aprire il minigioco.
            try:
                _send_scan(SCAN_CODES['SPACE'], keyup=False)
                time.sleep(0.05)
                _send_scan(SCAN_CODES['SPACE'], keyup=True)
            except Exception as e:
                print(f"[Input] Errore pressione SPAZIO: {e}")
            # ---------------------------------------

            id_task = getattr(self, '_task_launch_id', None)
            if id_task is not None:
                self._avvia_subprocess_task(id_task)

    def _avvia_subprocess_task(self, id_task):
        """
        Avvia il file .py della task come processo separato (non bloccante).
        Se c'è già un processo attivo per la stessa task, non ne avvia un secondo.
        """
        task = self.task_mgr.get_by_id(id_task)
        if task is None:
            self.auto_status_msg = "Errore: task non trovata"
            return

        exec_info = task.setdefault('esecuzione', {})

        azioni_eff, src_id = self.task_mgr.get_azioni_effettive(id_task)
        target_id = src_id if (src_id is not None and src_id != id_task) else id_task
        target_task = self.task_mgr.get_by_id(target_id)
        
        # Assicuriamoci di usare sempre il file del padre se si eredita
        target_exec = target_task.setdefault('esecuzione', {})
        filepath  = target_exec.get('file')

        # Se il file non esiste ancora, crealo ora
        if not filepath or not os.path.exists(filepath):
            filepath = self.task_mgr.crea_file_esecuzione(target_id)
            if not filepath:
                self.auto_status_msg = f"Errore: impossibile creare file .py per '{target_task['nome']}'"
                return
            exec_info['file'] = filepath
            target_exec['file'] = filepath
            self.task_mgr.salva()

        # Se il file esiste ma è vecchio (senza blocco __main__), rigeneralo
        try:
            with open(filepath, 'r', encoding='utf-8') as fh:
                contenuto = fh.read()
            if ('current_step=TASK_META' not in contenuto or 'sys.exit(1)' not in contenuto or 'GetForegroundWindow() != hwnd' not in contenuto) and not target_task.get('codice_custom', False):
                print(f"[Exec] File '{os.path.basename(filepath)}' obsoleto — rigenero")
                filepath = self.task_mgr.crea_file_esecuzione(target_id)
                exec_info['file'] = filepath
                target_exec['file'] = filepath
                self.task_mgr.salva()
        except Exception:
            pass

        # Evita doppio avvio dello stesso processo
        if (self._task_process is not None
                and self._task_process.poll() is None
                and self._task_process_task_id == id_task):
            self.auto_status_msg = f"'{task['nome']}' è già in esecuzione"
            return

        _, _, ram_step = self._get_task_target_coords(task)
        
        # Prende lo step massimo tra quello della RAM (se il giocatore l'ha fatto a mano) 
        # e quello interno (guidato dalle azioni di Cooldown nello script)
        internal_step = self.task_internal_steps.get(id_task, 0)
        script_step = max(ram_step, internal_step)

        try:
            abs_filepath = os.path.abspath(filepath)
            # cwd = directory di lancio del bot (dove stanno mappa_skeld.json,
            # i modelli .pt, ecc.). Nell'originale __file__ era main.py nella
            # cartella radice; con il package __file__ e' dentro among_us_gps/ui/
            # quindi usiamo os.getcwd() che e' la cwd del processo principale.
            self._task_process = subprocess.Popen(
                [sys.executable, "-u", abs_filepath, "--step", str(script_step)],
                cwd=os.getcwd(),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,   # unifica stderr in stdout
                bufsize=0,
            )
            self._task_process_task_id = id_task
            self.task_mgr.imposta_stato_esecuzione(id_task, 'running')
            self.auto_status_msg = f"▶ '{task['nome']}' avviata (PID {self._task_process.pid})"
            print(f"[Exec] Avviato '{abs_filepath}' — PID {self._task_process.pid}", flush=True)

            # Thread che legge stdout del processo e stampa riga per riga
            proc_ref  = self._task_process
            nome_task = task['nome']
            def _leggi_output(proc, nome, tid, sys_ref):
                try:
                    for raw in proc.stdout:
                        line = raw.decode('utf-8', errors='replace').rstrip('\n')
                        print(f"[{nome}] {line}", flush=True)
                        if line.startswith("__COOLDOWN__:"):
                            try:
                                cd_val = float(line.split(":")[1])
                                sys_ref.task_cooldowns[tid] = time.time() + cd_val
                                
                                # Lo script ha eseguito con successo un blocco/fase, salviamo in memoria locale
                                curr = sys_ref.task_internal_steps.get(tid, 0)
                                sys_ref.task_internal_steps[tid] = curr + 1
                                
                                print(f"[{nome}] Timer cooldown impostato per {cd_val}s", flush=True)
                            except ValueError:
                                pass
                except Exception:
                    pass
            t = threading.Thread(
                target=_leggi_output,
                args=(proc_ref, nome_task, id_task, self),
                daemon=True,
            )
            t.start()
        except Exception as e:
            self.task_mgr.imposta_stato_esecuzione(id_task, 'error')
            self.auto_status_msg = f"Errore avvio: {e}"
            print(f"[Exec] Errore avvio '{filepath}': {e}")

    def _controlla_processo_task(self):
        """
        Controlla se il processo in esecuzione è terminato e aggiorna lo stato.
        Va chiamato nel loop principale (aggiorna_frame).
        """
        if self._task_process is None:
            return
        ret = self._task_process.poll()
        if ret is None:
            # --- Controllo completamento RAM in tempo reale ---
            id_task = self._task_process_task_id
            if id_task is not None:
                task_reg = self.task_mgr.get_by_id(id_task)
                if task_reg:
                    tipo = task_reg.get('tipo')
                    room_id = task_reg.get('room_id')
                    # Cerca la task corrispondente in memoria
                    for mt in getattr(self, 'memory_tasks', []):
                        if mt.get('tipo') == tipo and mt.get('room_id') == room_id:
                            if mt.get('done', False):
                                # La task è finita nel gioco! Termina il processo.
                                self._ferma_processo_task(success=True)
                                return
            return  # ancora in esecuzione

        # Processo terminato
        id_task = self._task_process_task_id
        if id_task is not None:
            task = self.task_mgr.get_by_id(id_task)
            
            # --- LOGICA DI FALLBACK: Se la task fallisce e ha Fratelli, usali come posizioni alternative ---
            if ret != 0 and task and task.get('fratelli'):
                fratelli = task.get('fratelli', [])
                curr_fallback = getattr(self, '_task_fallback_idx', 0)
                if curr_fallback < len(fratelli):
                    next_target = (fratelli[curr_fallback]['x'], fratelli[curr_fallback]['y'])
                    self._task_fallback_idx = curr_fallback + 1
                    self.auto_status_msg = f"Task fallita, provo fratello {self._task_fallback_idx}..."
                    print(f"[Fallback] Errore esecuzione. Navigo al punto alternativo: {next_target}")
                    
                    self._task_process = None
                    self._task_process_task_id = None
                    
                    self._current_nav_target = next_target
                    self._plan_path(next_target)
                    
                    def on_arrivo_fallback():
                        self._avvia_subprocess_task(id_task)
                        
                    self._on_arrival_callback = on_arrivo_fallback
                    return
            # -----------------------------------------------------------------------------------------

            nuovo_stato = 'done' if ret == 0 else 'error'
            self.task_mgr.imposta_stato_esecuzione(id_task, nuovo_stato)

            # Applica Cooldown se il processo è finito senza errori e la task lo richiede
            if ret == 0 and task and task.get('cooldown', 0) > 0:
                self.task_cooldowns[id_task] = time.time() + task['cooldown']

            # --- COOLDOWN DI SICUREZZA contro il loop infinito ---
            # Se il subprocess e' terminato (con qualsiasi exit code) ma la
            # task NON risulta done in RAM, applichiamo un cooldown breve
            # per evitare che Auto-All la rilanci subito in ciclo. Succede
            # quando il bot non arriva esatto sul punto, oppure il minigioco
            # non si apre per qualunque motivo.
            if task:
                task_done_in_ram = False
                tipo_t   = task.get('tipo')
                room_t   = task.get('room_id')
                for mt in getattr(self, 'memory_tasks', []):
                    if (mt.get('tipo') == tipo_t
                            and mt.get('room_id') == room_t
                            and mt.get('done', False)):
                        task_done_in_ram = True
                        break
                if not task_done_in_ram:
                    existing_cd = self.task_cooldowns.get(id_task, 0)
                    safety_cd = time.time() + 8.0   # 8 s di tregua
                    if safety_cd > existing_cd:
                        self.task_cooldowns[id_task] = safety_cd
                        print(f"[Loop guard] Task non completata in RAM — cooldown di sicurezza 8s")

            nome = task['nome'] if task else f"#{id_task}"
            icona = "✓" if ret == 0 else "✗"
            self.auto_status_msg = f"{icona} '{nome}' terminata (exit {ret})"
            print(f"[Exec] '{nome}' terminata — exit code {ret}")

        self._task_process         = None
        self._task_process_task_id = None

    def _ferma_processo_task(self, success=False):
        """Termina il processo attivo (se presente) e aggiorna lo stato a idle."""
        # Rilascia sempre il mouse per evitare che rimanga incastrato sul gioco
        if _WIN_OK:
            try:
                pyautogui.mouseUp(button='left')
            except Exception:
                pass
                
        if self._task_process is None or self._task_process.poll() is not None:
            if not success:
                self.auto_status_msg = "Nessun processo da fermare"
            return
        try:
            self._task_process.terminate()
            self._task_process.wait(timeout=3)
        except Exception:
            try:
                self._task_process.kill()
            except Exception:
                pass
        id_task = self._task_process_task_id
        if id_task is not None:
            nuovo_stato = 'done' if success else 'idle'
            self.task_mgr.imposta_stato_esecuzione(id_task, nuovo_stato)
            task = self.task_mgr.get_by_id(id_task)
            nome = task['nome'] if task else f"#{id_task}"
            if success:
                self.auto_status_msg = f"✓ '{nome}' completata (Memoria)"
                print(f"[Exec] '{nome}' interrotta automaticamente (successo in RAM)")
            else:
                self.auto_status_msg = f"⏹ '{nome}' fermata"
                print(f"[Exec] '{nome}' terminata forzatamente")
        self._task_process         = None
        self._task_process_task_id = None

    def _registra_task_sconosciuta(self):
        """
        Se la task selezionata in memoria non è mappata, apre il popup
        di registrazione pre-compilato con nome, tipo e room_id (identificatori univoci).
        """
        t = self._get_selected_mem_task()
        if t is None:
            self.auto_status_msg = "Seleziona una task dalla lista"
            return
        if t.get('reg_task') is not None:
            self.auto_status_msg = f"'{t['nome']}' è già registrata"
            return

        # Dati univoci e persistenti della task
        tipo_id = t.get('tipo')
        room_id = t.get('room_id')

        tag = "popup_registra_sconosciuta"
        if dpg.does_item_exist(tag):
            dpg.delete_item(tag)

        px, py = self.pos_target
        vp_w   = dpg.get_viewport_client_width()
        vp_h   = dpg.get_viewport_client_height()

        # --- Zona rilevata automaticamente dalla posizione attuale ---
        zona_now  = self._zona_alla_posizione(px, py)
        gz_id_now = zona_now.get('game_zone_id') if zona_now else None
        zl_id_now = zona_now['id']               if zona_now else None

        # Pre-compila nome vuoto per far scegliere all'utente
        nome_default = ""

        if zona_now:
            gz_str    = f"  GZ:{gz_id_now}" if gz_id_now is not None else "  (nessun game_zone_id)"
            zona_info = f"[{zl_id_now:02d}] {zona_now['nome']}{gz_str}"
            col_zona  = Colors.ACCENT
        else:
            zona_info = "Fuori da qualsiasi zona - zone_id non impostato"
            col_zona  = (200, 120, 30, 255)

        def do_salva(*_):
            nome_v      = dpg.get_value("rs_nome").strip()
            x_v         = dpg.get_value("rs_x")
            y_v         = dpg.get_value("rs_y")
            vitale_v    = dpg.get_value("rs_vitale")
            due_p_v     = dpg.get_value("rs_due_p")
            if not nome_v:
                return

            # Ricalcola la zona basandosi sulle coordinate finali scelte nel popup
            zona_s  = self._zona_alla_posizione(x_v, y_v) or zona_now
            gz_id_s = zona_s.get('game_zone_id') if zona_s else gz_id_now
            zl_id_s = zona_s['id']               if zona_s else zl_id_now

            # Salvataggio tramite TaskManager usando i nuovi parametri
            self.task_mgr.aggiungi(
                nome_v, x_v, y_v,
                room_id       = room_id,
                tipo          = tipo_id,
                zone_id       = gz_id_s,
                zone_local_id = zl_id_s,
                zone_nome     = zona_s['nome'] if zona_s else None,
                vitale        = vitale_v,
                due_giocatori = due_p_v,
            )
            self._refresh_reg_task_listbox()
            self._refresh_mem_task_listbox()
            
            zona_msg = f" in '{zona_s['nome']}'" if zona_s else ""
            self.auto_status_msg = (f"Task '{nome_v}' registrata{zona_msg}  "
                                    f"tipo={tipo_id}  room={room_id}")
            if dpg.does_item_exist(tag):
                dpg.delete_item(tag)

        def do_usa_pos(*_):
            nx = round(self.pos_target[0], 3)
            ny = round(self.pos_target[1], 3)
            dpg.set_value("rs_x", nx)
            dpg.set_value("rs_y", ny)
            
            # Aggiorna label della zona in tempo reale se il giocatore si sposta
            z2 = self._zona_alla_posizione(nx, ny)
            if z2:
                gz2   = z2.get('game_zone_id')
                info2 = f"[{z2['id']:02d}] {z2['nome']}" + (f"  GZ:{gz2}" if gz2 is not None else "")
            else:
                info2 = "Fuori da qualsiasi zona"
            if dpg.does_item_exist("rs_zona_info"):
                dpg.set_value("rs_zona_info", info2)

        # Mostriamo gli ID utili a schermo per debug e chiarezza
        id_str = f"Task Type: {tipo_id}  |  Room ID: {room_id}"
        
        with dpg.window(label="Registra Task", tag=tag,
                        modal=True, no_resize=True, no_collapse=True,
                        width=400, height=315,
                        pos=(max(0, vp_w // 2 - 200), max(0, vp_h // 2 - 147))):
            dpg.add_text(id_str, color=Colors.ACCENT)
            dpg.add_text("Zona rilevata automaticamente:", color=Colors.TEXT_DIM)
            dpg.add_text(zona_info, tag="rs_zona_info", color=col_zona)
            dpg.add_separator()
            dpg.add_text("Nome  (puoi modificarlo):")
            dpg.add_input_text(tag="rs_nome", default_value=nome_default, width=-1)
            dpg.add_spacer(height=4)
            dpg.add_text("Coordinate:")
            with dpg.group(horizontal=True):
                dpg.add_text("X:")
                dpg.add_input_float(tag="rs_x", default_value=round(px, 3), width=155, step=0)
                dpg.add_text("Y:")
                dpg.add_input_float(tag="rs_y", default_value=round(py, 3), width=155, step=0)
            dpg.add_button(label="Usa posizione attuale  (aggiorna zona)", width=-1,
                           callback=do_usa_pos)
            dpg.add_spacer(height=6)
            dpg.add_checkbox(tag="rs_vitale", label=" Task di VITALE importanza  [!]",
                             default_value=False)
            dpg.add_checkbox(tag="rs_due_p", label=" Richiede due giocatori  [2P]",
                             default_value=False)
            dpg.add_spacer(height=6)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Salva", width=195, callback=do_salva)
                dpg.add_button(label="Annulla", width=195,
                               callback=lambda *a: dpg.delete_item(tag)
                               if dpg.does_item_exist(tag) else None)

    def _get_raw_task_id(self, nome_task):
        """
        Cerca l'ID numerico grezzo del gioco per una task dato il suo nome,
        scorrendo le definizioni caricate da tasks.json.
        """
        # Prima prova nei task_def del reader (da tasks.json)
        for tid, info in self.task_reader.skeld_tasks.items():
            if info.get("n", "") == nome_task:
                return tid
        # Fallback: cerca nel TaskManager def
        for tid, info in self.task_mgr.tasks_def.items():
            if info.get("n", "") == nome_task:
                return tid
        return None

    def _naviga_a_task_registrata(self):
        t = self._get_selected_reg_task()
        if t is None:
            self.auto_status_msg = "Seleziona una task registrata"
            return
        if not self.auto_enabled:
            self.auto_enabled = True
            if dpg.does_item_exist("auto_checkbox"):
                dpg.set_value("auto_checkbox", True)
                
        target_2p, step_2p = self._imposta_navigazione_2p(t)
        if target_2p:
            self._plan_path(target_2p)
            label_loc = 'A' if target_2p == getattr(self, 'auto_2p_loc_A', None) else 'B'
            self.auto_status_msg = f"Navigo verso '{t['nome']}' (2P - Loc {label_loc})"
        else:
            self._plan_path((t['x'], t['y']))
            self.auto_status_msg = f"Navigo verso '{t['nome']}'"

    def _elimina_task_registrata(self):
        t = self._get_selected_reg_task()
        if t is None:
            self.auto_status_msg = "Seleziona una task da eliminare"
            return
        nome = t['nome']
        id_t = t['id']
        def on_confirm(yes):
            if yes:
                self.task_mgr.rimuovi(id_t)
                # Sia la lista registrate (sparisce la task) sia la lista memoria
                # (la voce collegata diventa "non registrata") devono aggiornarsi.
                self._refresh_reg_task_listbox()
                self._refresh_mem_task_listbox()
                self.auto_status_msg = f"Task '{nome}' eliminata"
        self._show_confirm(f"Eliminare la task '{nome}' ?", on_confirm)

    def _esegui_generazione_py(self, t):
        filepath = self.task_mgr.crea_file_esecuzione(t['id'])

        if filepath:
            filename = os.path.basename(filepath)
            self.auto_status_msg = f"File creato: {filename}"
            if dpg.does_item_exist("genera_py_status"):
                dpg.configure_item("genera_py_status", color=(0, 220, 120, 255))
                dpg.set_value("genera_py_status", f"✓ {filename}")
            # Aggiorna anche il riferimento nel JSON (exec_info['file'])
            exec_info = t.setdefault('esecuzione', {
                'file': None, 'stato': 'idle', 'params': {}
            })
            exec_info['file'] = filepath
            self.task_mgr.salva()
        else:
            self.auto_status_msg = "Errore creazione file .py"
            if dpg.does_item_exist("genera_py_status"):
                dpg.configure_item("genera_py_status", color=(255, 80, 80, 255))
                dpg.set_value("genera_py_status", "✗ errore")

    def _genera_file_esecuzione(self):
        """
        Genera (o rigenera) il file .py di esecuzione per la task registrata
        selezionata nella listbox. Mostra feedback inline accanto al pulsante.
        """
        t = self._get_selected_reg_task()
        if t is None:
            self.auto_status_msg = "Seleziona una task registrata"
            if dpg.does_item_exist("genera_py_status"):
                dpg.configure_item("genera_py_status", color=(255, 100, 80, 255))
                dpg.set_value("genera_py_status", "← seleziona prima")
            return

        azioni_eff, src_id = self.task_mgr.get_azioni_effettive(t['id'])
        if src_id is not None and src_id != t['id']:
            self.auto_status_msg = f"La task eredita il file dal padre [{src_id}]"
            if dpg.does_item_exist("genera_py_status"):
                dpg.configure_item("genera_py_status", color=(255, 180, 100, 255))
                dpg.set_value("genera_py_status", f"Eredita dal padre [{src_id}]")
            return

        if t.get('codice_custom', False):
            def on_confirm(yes):
                if yes:
                    self._esegui_generazione_py(t)
            self._show_confirm(f"La task '{t['nome']}' usa 'Codice Custom'.\nSovrascrivere il suo file .py?", on_confirm)
        else:
            self._esegui_generazione_py(t)

    # ---- Popup Relazioni Padre ↔ Figlia ----
    def _apri_popup_relazioni_task(self):
        """
        Finestra non-modale che mostra tutte le task registrate come card,
        raggruppate in FAMIGLIE (padre + figlie) e TASK LIBERE.
        Permette di collegare/scollegare relazioni padre-figlia con due click:
          1. Clicca "Imposta come PADRE" su una task
          2. Clicca "← Collega come figlia" su un'altra
        """
        TAG_WIN    = "popup_relazioni_task"
        TAG_SCROLL = "rel_cards_scroll"
        TAG_STATUS = "rel_status_txt"
        WIN_W, WIN_H = 860, 700

        if dpg.does_item_exist(TAG_WIN):
            dpg.delete_item(TAG_WIN)

        vp_w = dpg.get_viewport_client_width()
        vp_h = dpg.get_viewport_client_height()

        # Stato condiviso tra i callback: quale task è "padre pending"
        state = {'pending': None}   # None oppure id_task

        # ── Helper stato / refresh ─────────────────────────────────────────

        def _status(msg, col=None):
            if dpg.does_item_exist(TAG_STATUS):
                dpg.set_value(TAG_STATUS, msg)
                if col:
                    dpg.configure_item(TAG_STATUS, color=col)

        def _refresh(*_):
            if not dpg.does_item_exist(TAG_SCROLL):
                return
            dpg.delete_item(TAG_SCROLL, children_only=True)
            _build_cards()

        # ── Callback bottoni ──────────────────────────────────────────────

        def _cb_imposta_padre(sender, app_data, tid):
            t = self.task_mgr.get_by_id(tid)
            state['pending'] = tid
            _status(
                f"PADRE selezionato: [{tid:02d}] {t['nome']}  "
                f"→  clicca '← Collega come figlia' sulla task da collegare",
                (255, 200, 0))
            _refresh()

        def _cb_collega_figlia(sender, app_data, id_figlia):
            id_padre = state['pending']
            if id_padre is None:
                return
            ok = self.task_mgr.imposta_parent(id_figlia, id_padre)
            if ok:
                state['pending'] = None
                p = self.task_mgr.get_by_id(id_padre)
                f = self.task_mgr.get_by_id(id_figlia)
                _status(
                    f"✓  [{id_figlia:02d}] {f['nome']}  "
                    f"collegata come figlia di  [{id_padre:02d}] {p['nome']}",
                    (0, 220, 120))
                self._refresh_reg_task_listbox()
                self._refresh_mem_task_listbox()
            else:
                _status(
                    "✗  Collegamento non valido: self-loop, "
                    "catena multi-livello, o padre già figlia di qualcuno",
                    (255, 100, 80))
            _refresh()

        def _cb_scollega(sender, app_data, tid):
            self.task_mgr.imposta_parent(tid, None)
            state['pending'] = None
            t = self.task_mgr.get_by_id(tid)
            _status(f"[{tid:02d}] {t['nome']} scollegata dal padre",
                    Colors.TEXT_DIM)
            self._refresh_reg_task_listbox()
            self._refresh_mem_task_listbox()
            _refresh()

        def _cb_annulla(*_):
            state['pending'] = None
            _status(
                "Seleziona una task come PADRE per iniziare il collegamento",
                Colors.TEXT_DIM)
            _refresh()

        def _cb_modifica(sender, app_data, tid):
            self._apri_popup_modifica_task(task=self.task_mgr.get_by_id(tid))

        # ── Costruzione card singola ───────────────────────────────────────

        def _card(t, indented=False, padre_nome=None):
            tid    = t['id']
            nome   = t['nome']
            zona   = t.get('zone_nome') or '—'
            n_az   = len(t.get('azioni', []))
            _, src = self.task_mgr.get_azioni_effettive(tid)
            figli  = self.task_mgr.get_figli(tid)
            pid    = state['pending']

            # Colore della card
            if tid == pid:
                col_id = (255, 200, 0)    # giallo: padre selezionato
            elif figli:
                col_id = (80, 180, 255)   # azzurro: è padre
            elif t.get('parent_id'):
                col_id = (120, 220, 120)  # verde: è figlia
            else:
                col_id = (190, 190, 190)  # grigio: libera

            # Stringa azioni
            if n_az > 0:
                az_str = f"A:{n_az}"
            elif src and src != tid:
                az_str = f"A:0←P{src:02d}"
            else:
                az_str = "A:0"

            indent_txt = "    ↳  " if indented else ""

            with dpg.group(horizontal=False, parent=TAG_SCROLL):
                # ── Riga 1: id + nome + badge ──
                with dpg.group(horizontal=True):
                    dpg.add_text(f"{indent_txt}[{tid:02d}]", color=col_id)
                    dpg.add_text(f"  {nome}")
                    dpg.add_text(f"   {az_str}", color=(100, 200, 255))
                    if t.get('vitale'):
                        dpg.add_text("  [!]",  color=(255, 80, 80))
                    if t.get('due_giocatori'):
                        dpg.add_text("  [2P]", color=(255, 200, 80))

                # ── Riga 2: dettagli ──
                dettagli = f"      Zona: {zona}"
                if padre_nome:
                    dettagli += f"   |   Padre: {padre_nome}"
                if figli:
                    nomi_f = ", ".join(f"[{f['id']:02d}] {f['nome']}"
                                       for f in figli[:4])
                    if len(figli) > 4:
                        nomi_f += f"  (+{len(figli)-4})"
                    dettagli += f"   |   Figli: {nomi_f}"
                dpg.add_text(dettagli, color=Colors.TEXT_DIM)

                # ── Riga 3: bottoni ──
                with dpg.group(horizontal=True):
                    if pid is None:
                        # Nessun padre in selezione
                        if not t.get('parent_id'):
                            # Può diventare padre (non è già figlia di nessuno)
                            dpg.add_button(
                                label="Imposta come PADRE",
                                user_data=tid,
                                callback=_cb_imposta_padre,
                                width=155, height=22)
                        if t.get('parent_id'):
                            # È già figlia: offri di scollegarla
                            dpg.add_button(
                                label="Scollega dal padre",
                                user_data=tid,
                                callback=_cb_scollega,
                                width=140, height=22)
                    else:
                        # Un padre è selezionato
                        if tid == pid:
                            dpg.add_text("[PADRE SELEZIONATO]",
                                         color=(255, 200, 0))
                            dpg.add_button(
                                label="Annulla",
                                callback=_cb_annulla,
                                width=70, height=22)
                        elif not t.get('parent_id') and not figli:
                            # Task libera: può diventare figlia
                            dpg.add_button(
                                label=f"← Collega come figlia di [{pid:02d}]",
                                user_data=tid,
                                callback=_cb_collega_figlia,
                                width=230, height=22)
                        elif t.get('parent_id'):
                            dpg.add_text("(ha già un padre)",
                                         color=Colors.TEXT_DIM)
                        elif figli:
                            dpg.add_text("(è padre: non può diventare figlia)",
                                         color=Colors.TEXT_DIM)

                    # Modifica sempre disponibile
                    dpg.add_button(
                        label="Modifica",
                        user_data=tid,
                        callback=_cb_modifica,
                        width=75, height=22)

                dpg.add_separator()

        # ── Costruzione completa lista card ───────────────────────────────

        def _build_cards():
            tasks  = self.task_mgr.task_list
            padri  = [t for t in tasks
                      if self.task_mgr.get_figli(t['id']) and not t.get('parent_id')]
            orfane = [t for t in tasks
                      if not self.task_mgr.get_figli(t['id']) and not t.get('parent_id')]

            if not tasks:
                with dpg.group(parent=TAG_SCROLL):
                    dpg.add_text("Nessuna task registrata ancora.",
                                 color=Colors.TEXT_DIM)
                return

            # Riepilogo numerico
            n_famiglie = len(padri)
            n_figli    = sum(len(self.task_mgr.get_figli(p['id'])) for p in padri)
            n_libere   = len(orfane)
            with dpg.group(horizontal=True, parent=TAG_SCROLL):
                dpg.add_text(
                    f"Totale: {len(tasks)} task   |   "
                    f"{n_famiglie} famiglie ({n_figli} figlie)   |   "
                    f"{n_libere} libere",
                    color=Colors.TEXT_DIM)
            with dpg.group(parent=TAG_SCROLL):
                dpg.add_spacer(height=6)

            # ─── Sezione FAMIGLIE ───────────────────────────────────────
            if padri:
                with dpg.group(parent=TAG_SCROLL):
                    dpg.add_text("FAMIGLIE  —  padre con le sue figlie",
                                 color=(80, 180, 255))
                    dpg.add_separator()
                    dpg.add_spacer(height=4)

                for padre in padri:
                    _card(padre)
                    for figlia in self.task_mgr.get_figli(padre['id']):
                        _card(figlia, indented=True, padre_nome=padre['nome'])
                    with dpg.group(parent=TAG_SCROLL):
                        dpg.add_spacer(height=8)

            # ─── Sezione TASK LIBERE ────────────────────────────────────
            if orfane:
                with dpg.group(parent=TAG_SCROLL):
                    dpg.add_spacer(height=4)
                    dpg.add_text("TASK LIBERE  —  senza relazioni",
                                 color=(190, 190, 190))
                    dpg.add_separator()
                    dpg.add_spacer(height=4)
                for t in orfane:
                    _card(t)

        # ── Finestra ──────────────────────────────────────────────────────

        with dpg.window(
                label="Relazioni Task  —  Padre ↔ Figlia",
                tag=TAG_WIN,
                width=WIN_W, height=WIN_H,
                pos=(max(0, vp_w // 2 - WIN_W // 2),
                     max(0, vp_h // 2 - WIN_H // 2)),
                no_collapse=True,
                on_close=lambda *a: (dpg.delete_item(TAG_WIN)
                                     if dpg.does_item_exist(TAG_WIN) else None)):

            dpg.add_text("GESTIONE RELAZIONI  PADRE ↔ FIGLIA",
                         color=Colors.ACCENT)
            dpg.add_separator()

            # Barra di stato / istruzioni
            dpg.add_text(
                "Seleziona una task come PADRE per iniziare il collegamento",
                tag=TAG_STATUS, color=Colors.TEXT_DIM, wrap=WIN_W - 30)

            dpg.add_spacer(height=4)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Annulla selezione",
                               callback=_cb_annulla,
                               width=150, height=26)
                dpg.add_button(label="Aggiorna vista",
                               callback=_refresh,
                               width=120, height=26)
                dpg.add_button(
                    label="Chiudi",
                    callback=lambda *a: (dpg.delete_item(TAG_WIN)
                                         if dpg.does_item_exist(TAG_WIN) else None),
                    width=90, height=26)
            dpg.add_separator()
            dpg.add_spacer(height=4)

            # Area scrollabile con le card
            with dpg.child_window(tag=TAG_SCROLL, width=-1, height=-1):
                pass

            _build_cards()

    # ---- Popup Nuova Task ----
    def _zona_alla_posizione(self, x, y):
        """
        Ritorna la zona (dict) in cui cade il punto (x, y).
        Se il punto è fuori dai confini, calcola e restituisce la zona più vicina.
        """
        if not self.zone_mgr.zone:
            return None

        # 1. Controllo geometrico: il punto è esattamente dentro un poligono?
        for z in self.zone_mgr.zone:
            if self._is_point_in_polygon(x, y, z['punti']):
                return z

        # 2. Fallback: se sei fuori dai poligoni, trova la zona più vicina tramite centroide
        zona_piu_vicina = None
        dist_minima = float('inf')

        for z in self.zone_mgr.zone:
            cx, cy = ZoneManager.centroide(z)
            dist = math.hypot(x - cx, y - cy)
            if dist < dist_minima:
                dist_minima = dist
                zona_piu_vicina = z

        return zona_piu_vicina

    def _apri_popup_nuova_task(self):
        tag = "popup_nuova_task"
        if dpg.does_item_exist(tag):
            dpg.delete_item(tag)
        px, py = self.pos_target
        vp_w = dpg.get_viewport_client_width()
        vp_h = dpg.get_viewport_client_height()

        # --- Rileva zona corrente ---
        zona_corrente = self._zona_alla_posizione(px, py)
        nome_zona     = zona_corrente['nome']       if zona_corrente else None
        game_zone_id  = zona_corrente.get('game_zone_id') if zona_corrente else None
        zone_local_id = zona_corrente['id']         if zona_corrente else None

        # Nome vuoto — l'utente lo inserisce manualmente
        nome_default = ""

        # Info zona per mostrare nel popup
        zona_info = ""
        if zona_corrente:
            gzid_str  = f"  game_zone_id={game_zone_id}" if game_zone_id is not None else "  (nessun game_zone_id)"
            zona_info = f"Zona rilevata: [{zone_local_id:02d}] {nome_zona}{gzid_str}"
        else:
            zona_info = "Posizione fuori da qualsiasi zona registrata"

        def do_salva(*_):
            nome_v      = dpg.get_value("nt_nome").strip()
            x_v         = dpg.get_value("nt_x")
            y_v         = dpg.get_value("nt_y")
            vitale_v    = dpg.get_value("nt_vitale")
            due_p_v     = dpg.get_value("nt_due_p")
            if not nome_v:
                return

            # 1. Ricava zona e ID locali in base alle coordinate
            zona_s  = self._zona_alla_posizione(x_v, y_v)
            gz_id_s = zona_s.get('game_zone_id') if zona_s else None
            zl_id_s = zona_s['id']               if zona_s else None

            # 2. Ricava tipo e room_id dalla RAM (identificatori univoci).
            # NB: le memory_tasks non hanno un 'raw_game_id' (vedi
            # AmongUsTaskReader.get_tasks): la chiave univoca è (tipo, room_id).
            matched_mem = None
            nome_bare   = nome_v.split(": ", 1)[-1].lower()

            # Cerca per nome esatto
            for mt in self.memory_tasks:
                if mt['nome'].lower() == nome_bare or mt['nome'].lower() == nome_v.lower():
                    matched_mem = mt
                    break

            # Fallback: prendi una task non ancora registrata che si trova
            # nella stessa stanza di gioco del punto cliccato
            if matched_mem is None and gz_id_s is not None:
                enriched = self.task_mgr.get_memory_tasks_info(self.memory_tasks)
                for mt in enriched:
                    if mt.get('room_id') == gz_id_s and not mt.get('registrata'):
                        matched_mem = mt
                        break

            # 3. Costruisce e salva il JSON
            self.task_mgr.aggiungi(
                nome_v, x_v, y_v,
                room_id       = matched_mem['room_id']  if matched_mem else None,
                tipo          = matched_mem.get('tipo') if matched_mem else None,
                zone_id       = gz_id_s,
                zone_local_id = zl_id_s,
                zone_nome     = zona_s['nome'] if zona_s else None,
                vitale        = vitale_v,
                due_giocatori = due_p_v,
            )
            self._refresh_reg_task_listbox()
            self._refresh_mem_task_listbox()

            msg = f"Task '{nome_v}' registrata"
            if zona_s:      msg += f" in '{zona_s['nome']}'"
            if matched_mem: msg += f" (tipo={matched_mem.get('tipo')} room={matched_mem.get('room_id')})"
            self.auto_status_msg = msg
            
            if dpg.does_item_exist(tag):
                dpg.delete_item(tag)

        def do_usa_pos(*_):
            nx = round(self.pos_target[0], 3)
            ny = round(self.pos_target[1], 3)
            dpg.set_value("nt_x", nx)
            dpg.set_value("nt_y", ny)
            # Aggiorna label zona in tempo reale
            z2 = self._zona_alla_posizione(nx, ny)
            if z2:
                gz2   = z2.get('game_zone_id')
                info2 = f"Zona: [{z2['id']:02d}] {z2['nome']}" + (f"  GZ:{gz2}" if gz2 is not None else "")
            else:
                info2 = "Posizione fuori da qualsiasi zona"
            if dpg.does_item_exist("nt_zona_info"):
                dpg.set_value("nt_zona_info", info2)

        col_zona = Colors.ACCENT if zona_corrente else (200, 120, 30, 255)
        with dpg.window(label="Nuova Task", tag=tag, modal=True, no_resize=True,
                        no_collapse=True, width=400, height=275,
                        pos=(max(0, vp_w // 2 - 200), max(0, vp_h // 2 - 147))):
            dpg.add_text(zona_info, tag="nt_zona_info", color=col_zona, wrap=390)
            dpg.add_spacer(height=4)
            dpg.add_text("Nome task  (pre-compilato con zona):")
            dpg.add_input_text(tag="nt_nome", default_value=nome_default, width=-1)
            dpg.add_spacer(height=4)
            dpg.add_text("Coordinate posizione principale:")
            with dpg.group(horizontal=True):
                dpg.add_text("X:")
                dpg.add_input_float(tag="nt_x", default_value=round(px, 3), width=155, step=0)
                dpg.add_text("Y:")
                dpg.add_input_float(tag="nt_y", default_value=round(py, 3), width=155, step=0)
            dpg.add_button(label="Usa posizione attuale  (aggiorna zona)", width=-1,
                           callback=do_usa_pos)
            dpg.add_spacer(height=6)
            dpg.add_checkbox(tag="nt_vitale", label=" Task di VITALE importanza  [!]",
                             default_value=False)
            dpg.add_checkbox(tag="nt_due_p", label=" Richiede due giocatori  [2P]",
                             default_value=False)
            dpg.add_spacer(height=6)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Salva", width=190, callback=do_salva)
                dpg.add_button(label="Annulla", width=190,
                               callback=lambda *a: dpg.delete_item(tag)
                               if dpg.does_item_exist(tag) else None)

    # ---- Popup Modifica Task ----
    def _apri_popup_modifica_task(self, task=None):
        # task può essere passato direttamente (es. aperto da lista memoria)
        # oppure viene risolto dalla listbox delle task registrate.
        t = task if task is not None else self._get_selected_reg_task()
        if t is None:
            self.auto_status_msg = "Seleziona una task da modificare"
            return
        tag = "popup_modifica_task"
        if dpg.does_item_exist(tag):
            dpg.delete_item(tag)
        vp_w = dpg.get_viewport_client_width()
        vp_h = dpg.get_viewport_client_height()
        id_t = t['id']

        def do_salva(*_):
            nome_v   = dpg.get_value("mt_nome").strip()
            x_v      = dpg.get_value("mt_x")
            y_v      = dpg.get_value("mt_y")
            vitale_v = dpg.get_value("mt_vitale")
            due_p_v  = dpg.get_value("mt_due_p")
            custom_v = dpg.get_value("mt_custom")
            lung_v   = dpg.get_value("mt_lunghezza")
            parent_v = dpg.get_value("mt_parent") if dpg.does_item_exist("mt_parent") else "— (nessuno)"
            if not nome_v:
                return
            self.task_mgr.aggiorna(id_t, nome_v, x_v, y_v, vitale=vitale_v, due_giocatori=due_p_v, codice_custom=custom_v, lunghezza=lung_v)
            # Estrai id del padre dal combo (formato "[ID] nome" o "— (nessuno)")
            new_parent = None
            if parent_v and parent_v.startswith("["):
                try:
                    new_parent = int(parent_v[1:parent_v.index("]")])
                except Exception:
                    new_parent = None
            if not self.task_mgr.imposta_parent(id_t, new_parent):
                self.auto_status_msg = f"Parent invalido (self-loop o padre già figlio): ignorato"
            # Refresh di ENTRAMBE le liste: la modifica di una task registrata
            # (nome, coordinate, parent) si riflette in qualunque voce della
            # lista-memoria che la referenzia via (tipo, room_id).
            self._refresh_reg_task_listbox()
            self._refresh_mem_task_listbox()
            self.auto_status_msg = f"Task [{id_t}] aggiornata"
            if dpg.does_item_exist(tag):
                dpg.delete_item(tag)

        def do_usa_pos(*_):
            dpg.set_value("mt_x", round(self.pos_target[0], 3))
            dpg.set_value("mt_y", round(self.pos_target[1], 3))

        def do_apri_editor(*_):
            # Chiudi il popup modale: l'editor è una finestra DPG autonoma
            # e la dashboard deve continuare a renderizzare normalmente.
            if dpg.does_item_exist(tag):
                dpg.delete_item(tag)

            def _on_save(id_salvata):
                # Rigenera il file .py con le nuove azioni
                self.task_mgr.crea_file_esecuzione(id_salvata)
                # Il numero di azioni è mostrato sia nella lista registrate sia
                # (indirettamente, come stato) nella lista memoria: refresh di entrambe.
                self._refresh_reg_task_listbox()
                self._refresh_mem_task_listbox()
                self.auto_status_msg = f"Azioni task [{id_salvata}] salvate + file .py rigenerato"

            self.action_editor.apri(id_t, on_save=_on_save)

        with dpg.window(label=f"Modifica Task [{id_t}]", tag=tag, modal=True,
                        no_resize=True, no_collapse=True, width=460, height=670,
                        pos=(max(0, vp_w // 2 - 230), max(0, vp_h // 2 - 335))):

            # ========== SEZIONE 1: IDENTITÀ ==========
            dpg.add_text("IDENTITÀ", color=Colors.ACCENT)
            dpg.add_separator()
            dpg.add_text("Nome task:")
            dpg.add_input_text(tag="mt_nome", default_value=t['nome'], width=-1)

            dpg.add_spacer(height=4)
            dpg.add_text("Coordinate posizione principale:")
            with dpg.group(horizontal=True):
                dpg.add_text("X:")
                dpg.add_input_float(tag="mt_x", default_value=t['x'],
                                    width=150, step=0, format="%.3f")
                dpg.add_text("Y:")
                dpg.add_input_float(tag="mt_y", default_value=t['y'],
                                    width=150, step=0, format="%.3f")
            dpg.add_button(label="Usa posizione attuale", width=-1, callback=do_usa_pos)

            # Flag vitale / due giocatori
            dpg.add_spacer(height=4)
            with dpg.group(horizontal=True):
                dpg.add_checkbox(tag="mt_vitale", label=" VITALE [!]",
                                 default_value=bool(t.get('vitale', False)))
                dpg.add_checkbox(tag="mt_due_p", label=" 2 giocatori [2P]",
                                 default_value=bool(t.get('due_giocatori', False)))
            
            with dpg.group(horizontal=True):
                dpg.add_text("Lunghezza:")
                dpg.add_combo(items=["N/A", "Short", "Long", "Common"], tag="mt_lunghezza", default_value=t.get('lunghezza', 'N/A'), width=120)
            
            dpg.add_checkbox(tag="mt_custom", label=" Codice Custom (non sovrascrivere il .py)",
                             default_value=bool(t.get('codice_custom', False)))

            # ========== SEZIONE 2: FASI E FRATELLI ==========
            dpg.add_spacer(height=8)
            dpg.add_text("FASI E FRATELLI", color=Colors.ACCENT)
            dpg.add_separator()
            
            def delete_fase(s, a, u):
                self.task_mgr.aggiorna(id_t, dpg.get_value("mt_nome").strip() or t['nome'], dpg.get_value("mt_x"), dpg.get_value("mt_y"), dpg.get_value("mt_vitale"), dpg.get_value("mt_due_p"), dpg.get_value("mt_custom"), lunghezza=dpg.get_value("mt_lunghezza"))
                self.task_mgr.rimuovi_fase(id_t, u)
                self._apri_popup_modifica_task(task=self.task_mgr.get_by_id(id_t))
                
            def delete_fratello(s, a, u):
                self.task_mgr.aggiorna(id_t, dpg.get_value("mt_nome").strip() or t['nome'], dpg.get_value("mt_x"), dpg.get_value("mt_y"), dpg.get_value("mt_vitale"), dpg.get_value("mt_due_p"), dpg.get_value("mt_custom"), lunghezza=dpg.get_value("mt_lunghezza"))
                self.task_mgr.rimuovi_fratello(id_t, u)
                self._apri_popup_modifica_task(task=self.task_mgr.get_by_id(id_t))

            with dpg.group(horizontal=True):
                with dpg.child_window(width=210, height=110):
                    fasi = t.get('fasi', [])
                    dpg.add_text(f"Fasi ({len(fasi)}):", color=Colors.TEXT_DIM)
                    for i, f in enumerate(fasi):
                        with dpg.group(horizontal=True):
                            dpg.add_button(label="X", user_data=i, callback=delete_fase)
                            dpg.add_text(f"[{i}] {f['nome'][:12]}..")
                with dpg.child_window(width=210, height=110):
                    fratelli = t.get('fratelli', [])
                    dpg.add_text(f"Fratelli ({len(fratelli)}):", color=Colors.TEXT_DIM)
                    for i, fr in enumerate(fratelli):
                        with dpg.group(horizontal=True):
                            dpg.add_button(label="X", user_data=i, callback=delete_fratello)
                            dpg.add_text(f"[{i}] ({fr['x']:.1f}, {fr['y']:.1f})")

            # ========== SEZIONE 3: EREDITARIETÀ AZIONI (padre/figlia) ==========
            dpg.add_spacer(height=8)
            dpg.add_text("AZIONI E EREDITARIETÀ", color=Colors.ACCENT)
            dpg.add_separator()

            azioni_proprie      = len(t.get('azioni', []))
            azioni_eff, src_id  = self.task_mgr.get_azioni_effettive(id_t)

            # Riga riepilogo origine azioni
            if src_id is not None and src_id != id_t:
                p_src = self.task_mgr.get_by_id(src_id)
                p_src_nome = p_src['nome'] if p_src else '?'
                dpg.add_text(
                    f"Azioni proprie: {azioni_proprie}  →  in uso: {len(azioni_eff)} EREDITATE "
                    f"dal padre [{src_id}] {p_src_nome}",
                    color=(100, 220, 255), wrap=440)
            elif azioni_proprie > 0:
                dpg.add_text(
                    f"Azioni proprie: {azioni_proprie}  →  in uso: {azioni_proprie} (nessuna ereditarietà)",
                    color=Colors.TEXT_DIM, wrap=440)
            else:
                dpg.add_text(
                    "Nessuna azione (né proprie né ereditate). "
                    "Registra azioni con l'editor o scegli un padre qui sotto.",
                    color=(255, 180, 100), wrap=440)

            # Eventuali figli di questa task (info utile: non saranno scelti come padre)
            figli = self.task_mgr.get_figli(id_t)
            if figli:
                nomi_figli = ", ".join(f"[{f['id']}] {f['nome']}" for f in figli[:3])
                suffix = "" if len(figli) <= 3 else f" (+{len(figli)-3})"
                dpg.add_text(f"Questa task è PADRE di {len(figli)} figli: {nomi_figli}{suffix}",
                             color=Colors.TEXT_DIM, wrap=440)

            dpg.add_spacer(height=4)
            dpg.add_text("Scegli task padre (se vuota, le azioni locali hanno priorità):",
                         color=Colors.TEXT_DIM, wrap=440)

            # Costruzione candidati (vedi logica sopra)
            candidati = ["— (nessuno)"]
            for altro in self.task_mgr.task_list:
                if altro['id'] == id_t:
                    continue
                if altro.get('parent_id') is not None:
                    continue
                n_az   = len(altro.get('azioni', []))
                zona_a = altro.get('zone_nome') or "—"
                candidati.append(f"[{altro['id']}] {altro['nome']} — A:{n_az} ({zona_a})")

            default_parent = "— (nessuno)"
            cur_parent = t.get('parent_id')
            if cur_parent is not None:
                p = self.task_mgr.get_by_id(cur_parent)
                if p is not None:
                    n_az   = len(p.get('azioni', []))
                    zona_a = p.get('zone_nome') or "—"
                    default_parent = f"[{p['id']}] {p['nome']} — A:{n_az} ({zona_a})"
            dpg.add_combo(items=candidati, tag="mt_parent",
                          default_value=default_parent, width=-1)

            dpg.add_spacer(height=4)
            dpg.add_button(label="APRI EDITOR AZIONI  (click / drag / zone / tempi)",
                           width=-1, height=36, callback=do_apri_editor)

            # ========== AZIONI FINALI ==========
            dpg.add_spacer(height=10)
            dpg.add_separator()
            with dpg.group(horizontal=True):
                dpg.add_button(label="Salva", width=220, height=32, callback=do_salva)
                dpg.add_button(label="Annulla", width=220, height=32,
                               callback=lambda *a: dpg.delete_item(tag) if dpg.does_item_exist(tag) else None)

    # ---- Popup Nuova Fase ----
    def _apri_popup_nuova_fase(self):
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
            nome_v = dpg.get_value("nf_nome").strip()
            x_v = dpg.get_value("nf_x")
            y_v = dpg.get_value("nf_y")
            if not nome_v:
                return
            self.task_mgr.aggiungi_fase(id_t, nome_v, x_v, y_v)
            self._refresh_reg_task_listbox()
            self.auto_status_msg = f"Fase '{nome_v}' aggiunta a [{id_t}]"
            if dpg.does_item_exist(tag):
                dpg.delete_item(tag)

        def do_usa_pos(*_):
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
                dpg.add_button(label="Aggiungi Fase", width=170, callback=do_salva)
                dpg.add_button(label="Annulla", width=170,
                               callback=lambda *a: dpg.delete_item(tag) if dpg.does_item_exist(tag) else None)

    # ---- Popup Nuovo Fratello ----
    def _apri_popup_nuovo_fratello(self):
        t = self._get_selected_reg_task()
        if t is None:
            self.auto_status_msg = "Seleziona una task a cui aggiungere un fratello"
            return
        tag = "popup_nuovo_fratello"
        if dpg.does_item_exist(tag):
            dpg.delete_item(tag)
        px, py = self.pos_target
        vp_w = dpg.get_viewport_client_width()
        vp_h = dpg.get_viewport_client_height()
        id_t = t['id']

        def do_salva(*_):
            x_v = dpg.get_value("nfr_x")
            y_v = dpg.get_value("nfr_y")
            self.task_mgr.aggiungi_fratello(id_t, x_v, y_v)
            self._refresh_reg_task_listbox()
            self.auto_status_msg = f"Fratello aggiunto a [{id_t}]"
            if dpg.does_item_exist(tag):
                dpg.delete_item(tag)

        def do_usa_pos(*_):
            dpg.set_value("nfr_x", round(self.pos_target[0], 3))
            dpg.set_value("nfr_y", round(self.pos_target[1], 3))

        with dpg.window(label=f"Nuovo Fratello per [{id_t}] {t['nome']}", tag=tag,
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
                dpg.add_button(label="Aggiungi Fratello", width=170, callback=do_salva)
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
            raw = dpg.get_value("gzid_input").strip()
            if raw == "":
                self.zone_mgr.set_game_zone_id(id_zona, None)
                self.auto_status_msg = f"ID rimosso da '{nome_zona}'"
            else:
                try:
                    gzid = int(raw)
                    # Controlla unicità
                    esistente = self.zone_mgr.get_by_game_zone_id(gzid)
                    if esistente and esistente['id'] != id_zona:
                        self.auto_status_msg = (f"GZ:{gzid} già usato da "
                                                f"'{esistente['nome']}' — scegli un altro")
                        return
                    self.zone_mgr.set_game_zone_id(id_zona, gzid)
                    self._refresh_zone_list()
                    self._refresh_reg_task_listbox()   # aggiorna label zone nei task
                    self.auto_status_msg = f"'{nome_zona}' → GZ:{gzid}"
                except ValueError:
                    self.auto_status_msg = "Inserisci un numero intero"
                    return
            self._refresh_zone_list()
            self._refresh_reg_task_listbox()
            if dpg.does_item_exist(tag):
                dpg.delete_item(tag)

        default_txt = str(curr_gzid) if curr_gzid is not None else ""
        hint_txt    = f"Attuale: GZ:{curr_gzid}" if curr_gzid is not None else "Nessun ID impostato"

        with dpg.window(label=f"ID Zona Gioco — {nome_zona}", tag=tag,
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

    def _apri_popup_link_zona(self):
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
        curr_zid = t.get('zone_id', None)

        # Costruisce la lista delle zone che hanno un game_zone_id
        zone_con_id = [(z['nome'], z.get('game_zone_id'))
                       for z in self.zone_mgr.zone if z.get('game_zone_id') is not None]
        zone_con_id.sort(key=lambda x: x[1])

        def do_salva(*_):
            raw = dpg.get_value("lz_input").strip()
            if raw == "" or raw.lower() == "nessuna":
                self.task_mgr.set_zone_link(id_task, None)
                self.auto_status_msg = f"Link zona rimosso da '{nome_t}'"
            else:
                try:
                    gzid = int(raw)
                    self.task_mgr.set_zone_link(id_task, gzid)
                    z = self.zone_mgr.get_by_game_zone_id(gzid)
                    z_nome = z['nome'] if z else "?"
                    self.auto_status_msg = f"'{nome_t}' → zona '{z_nome}' (GZ:{gzid})"
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
        with dpg.window(label=f"Link Zona ↔ '{nome_t}'", tag=tag,
                        modal=True, no_resize=True, no_collapse=True,
                        width=380, height=win_h,
                        pos=(max(0, vp_w // 2 - 190), max(0, vp_h // 2 - win_h // 2))):
            dpg.add_text(f"Link attuale: {curr_str}{curr_desc}", color=Colors.TEXT_DIM)
            dpg.add_spacer(height=4)

            if zone_con_id:
                dpg.add_text("Zone disponibili (GZ:ID — Nome):", color=Colors.TEXT_DIM)
                for z_nome, z_gzid in zone_con_id:
                    marker = " ◄ attuale" if z_gzid == curr_zid else ""
                    dpg.add_text(f"  GZ:{z_gzid} — {z_nome}{marker}",
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

    # ================= DIALOGHI MODALI =================
    def _show_text_input(self, title, default_text, callback):
        """Mostra un popup modale per inserimento testo. callback(str|None)."""
        tag = "text_input_popup"
        if dpg.does_item_exist(tag):
            dpg.delete_item(tag)

        def do_ok(*_):
            if not dpg.does_item_exist(f"{tag}_input"):
                callback(None)
                return
            value = dpg.get_value(f"{tag}_input")
            if dpg.does_item_exist(tag):
                dpg.delete_item(tag)
            if value and value.strip():
                callback(value.strip())
            else:
                callback(None)

        def do_cancel(*_):
            if dpg.does_item_exist(tag):
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
        if dpg.does_item_exist(tag):
            dpg.delete_item(tag)

        def do_yes(*_):
            if dpg.does_item_exist(tag):
                dpg.delete_item(tag)
            callback(True)

        def do_no(*_):
            if dpg.does_item_exist(tag):
                dpg.delete_item(tag)
            callback(False)

        vp_w = dpg.get_viewport_client_width()
        vp_h = dpg.get_viewport_client_height()
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
        if dpg.does_item_exist(tag):
            dpg.delete_item(tag)

        def pick(col_hex):
            self.zone_mgr.cambia_colore(zona['id'], col_hex)
            self._refresh_zone_list()
            self.auto_status_msg = f"Colore di '{zona['nome']}' aggiornato"
            if dpg.does_item_exist(tag):
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
                           callback=lambda *a: dpg.delete_item(tag)
                                                if dpg.does_item_exist(tag) else None)

    # ================= LOOP AUTO-MOVE =================
    def _update_auto_move(self, dt):
        # --- Aggiornamento ostacoli dinamici (Porte) ---
        if hasattr(self, 'pathfinder'):
            self.pathfinder.dynamic_obstacles.clear()
            current_time = time.time()
            for d in getattr(self, 'detected_doors', []):
                if current_time - d['time'] < 1.0:
                    door_key = self.pathfinder._key(d['x'], d['y'])
                    r = int(1.2 / self.pathfinder.step) # Raggio blocco porta
                    for dx in range(-r, r+1):
                        for dy in range(-r, r+1):
                            if math.hypot(dx, dy) <= r:
                                self.pathfinder.dynamic_obstacles.add((door_key[0]+dx, door_key[1]+dy))

        if (not self.auto_enabled) or (not self.auto_path):
            if self.key_ctrl.pressed:
                self.key_ctrl.release_all()
            
            # Replan periodico se in attesa (es. percorso bloccato)
            if self.auto_enabled and getattr(self, 'auto_final_target', None):
                self.auto_stuck_timer += dt
                if self.auto_stuck_timer > 1.0:
                    self._plan_path(self.auto_final_target)
                    self.auto_stuck_timer = 0.0
            return

        # --- Controllo Finestra in Primo Piano ---
        if _WIN_OK:
            hwnd_au = win32gui.FindWindow(None, "Among Us")
            if hwnd_au and win32gui.GetForegroundWindow() != hwnd_au:
                if self.key_ctrl.pressed:
                    self.key_ctrl.release_all()
                self.auto_status_msg = "In pausa (Focus su altra finestra)"
                return

        cx, cy = self.pos_target
        
        # Replan if current path hits a door
        if self.auto_path:
            path_blocked = False
            start_point = (cx, cy)
            for i in range(self.auto_path_index, len(self.auto_path)):
                wp = self.auto_path[i]
                if self.pathfinder.line_has_dynamic_obstacle(start_point, wp):
                    path_blocked = True
                    break
                start_point = wp
            
            if path_blocked:
                self.auto_status_msg = "Percorso bloccato da porta, ricalcolo..."
                self._plan_path(self.auto_final_target)
                if not self.auto_path:
                    if getattr(self, 'auto_execute_all', False) and getattr(self, '_current_auto_all_task_id', None):
                        tid = self._current_auto_all_task_id
                        self.task_cooldowns[tid] = time.time() + 15.0
                        self.auto_status_msg = "Task isolata da porte chiuse, cambio task..."
                        self._cancel_auto_move(silent=True, stop_auto_all=False)
                        if dpg.does_item_exist("task_launch_popup"):
                            dpg.delete_item("task_launch_popup")
                    return

        # --- Controllo Radar per task 2P ---
        if getattr(self, 'auto_is_2p_task', False):
            target_x, target_y = self.auto_2p_current_target
            dist_to_target = math.hypot(cx - target_x, cy - target_y)
            
            # Controlliamo solo se siamo nel raggio visivo (circa 5 mattonelle) e switch in cooldown
            if dist_to_target < 5.0 and (time.time() - getattr(self, '_2p_last_switch_time', 0) > 3.0):
                occupato = False
                current_time = time.time()
                for p in self.detected_players:
                    # Ignora cadaveri
                    if p.get('is_dead', False): 
                        continue
                    # Considera SOLO avvistamenti in tempo reale (max 0.5 secondi fa)
                    if current_time - p['time'] > 0.5: 
                        continue
                    # Se un giocatore vivo è a meno di 1.2 unità dalla postazione della task
                    if math.hypot(p['x'] - target_x, p['y'] - target_y) < 1.2:
                        occupato = True
                        break
                
                if occupato:
                    pending = getattr(self, 'auto_2p_pending_locs', [])
                    if len(pending) > 1:
                        for step, loc in pending:
                            if loc != self.auto_2p_current_target:
                                self.auto_2p_current_target = loc
                                self.auto_2p_current_step = step
                                self._2p_last_switch_time = time.time()
                                self._plan_path(loc)
                                self.auto_status_msg = f"Player al pannello! Cambio a tappa {step}."
                                return

        # --- Controllo Visuale Dinamico per i Fratelli ---
        pendenti = getattr(self, '_task_fratelli_pendenti', None)
        if pendenti and len(pendenti) > 1:
            lock_target = self._cerca_glow_fratelli(pendenti)
            if lock_target:
                self.auto_status_msg = "Task individuata visivamente! Lock acquisito."
                print(f"[Visual Lock] Alone giallo rilevato a {lock_target}! Aggiorno il path.")
                self._current_nav_target = lock_target
                self._task_fratelli_pendenti = None # Lock acquisito
                self.auto_final_target = lock_target
                self._plan_path(lock_target)
                return

        # Waypoint corrente
        wx, wy = self.auto_path[self.auto_path_index]
        dx = wx - cx
        dy = wy - cy
        dist = math.hypot(dx, dy)

        is_last = (self.auto_path_index == len(self.auto_path) - 1)
        advance_th = (GPSConfig.AUTO_ARRIVAL_THRESHOLD
                      if is_last else GPSConfig.WAYPOINT_ADVANCE)

        # ================= 1. ANTICIPAZIONE DELLA CURVA (Lookahead Umano) =================
        # Se non è l'ultimo waypoint e ci stiamo avvicinando all'angolo
        if not is_last and dist < 0.75:
            next_wx, next_wy = self.auto_path[self.auto_path_index + 1]
            if self.pathfinder.line_walkable_coords((cx, cy), (next_wx, next_wy)):
                self.auto_path_index += 1
                return  # Salta al prossimo ciclo per ricalcolare la curva fluida

        # Avanzamento waypoint standard
        if dist < advance_th:
            if is_last:
                self.auto_status_msg = "Arrivato ✓"
                self._cancel_auto_move(silent=True, stop_auto_all=False)
                # Esegui callback di arrivo (es. avvio subprocess task)
                if self._on_arrival_callback is not None:
                    cb = self._on_arrival_callback
                    self._on_arrival_callback = None
                    cb()
                return
            self.auto_path_index += 1
            self.auto_stuck_pos = (cx, cy)
            self.auto_stuck_timer = 0.0
            return

        # Stuck detection
        if self.auto_stuck_pos is None:
            self.auto_stuck_pos = (cx, cy)
        moved = math.hypot(cx - self.auto_stuck_pos[0],
                           cy - self.auto_stuck_pos[1])
        if moved > GPSConfig.AUTO_STUCK_DELTA:
            self.auto_stuck_pos = (cx, cy)
            self.auto_stuck_timer = 0.0
        else:
            self.auto_stuck_timer += dt
            if self.auto_stuck_timer > GPSConfig.AUTO_STUCK_TIME:
                if GPSConfig.AUTO_REPLAN_ON_STUCK and self.auto_final_target:
                    self.auto_status_msg = "Bloccato — replan"
                    self.key_ctrl.release_all()
                    self._plan_path(self.auto_final_target)
                    return
                self.auto_status_msg = "Bloccato — stop"
                self._cancel_auto_move(silent=True)
                return

        move_x = 0
        move_y = 0

        # ================= 2. MOVIMENTO FLUIDO (PWM Direzionale) =================
        # Per evitare l'effetto "onde" (zig-zag) sulle diagonali, premiamo 
        # sempre l'asse principale al 100% e "tappiamo" l'asse secondario in 
        # proporzione all'angolo (Pulse Width Modulation).
        
        if dist > 0:
            vx = dx / dist
            vy = dy / dist
            
            # Normalizziamo affinché l'asse maggiore sia esattamente 1.0
            max_v = max(abs(vx), abs(vy))
            if max_v > 0:
                vx /= max_v
                vy /= max_v
                
            freq = 25.0  # Frequenza del tap (25 Hz = micro-correzioni fluide)
            phase = (time.time() * freq) % 1.0
            
            stop_th = 0.03  # Tolleranza finale per fermarsi perfettamente
            
            if abs(dx) > stop_th:
                if abs(vx) >= 1.0 or abs(vx) > phase:
                    move_x = 1 if dx > 0 else -1
                    
            if abs(dy) > stop_th:
                if abs(vy) >= 1.0 or abs(vy) > phase:
                    move_y = 1 if dy > 0 else -1

        # Wiggle anti-incastro
        if self.auto_stuck_timer > 0.3:
            if int(self.auto_stuck_timer * 15) % 2 == 0:
                # Forza movimento trasversale casuale per sbloccarsi dall'angolo
                if move_x != 0 and move_y == 0:
                    move_y = 1 if random.random() < 0.5 else -1
                elif move_y != 0 and move_x == 0:
                    move_x = 1 if random.random() < 0.5 else -1
                else:
                    move_x = -move_x if random.random() < 0.5 else move_x
                    move_y = -move_y if random.random() < 0.5 else move_y

        # ================= 3. SCIVOLAMENTO SUI MURI =================
        def is_safe(offset_x, offset_y):
            test_x = cx + offset_x
            test_y = cy + offset_y
            key = self.pathfinder._key(test_x, test_y)
            # Aggiungiamo spessore per non tagliare troppo i muri (hitbox)
            ox_range = (0, 1) if offset_x > 0 else ((0, -1) if offset_x < 0 else (0,))
            oy_range = (0, 1) if offset_y > 0 else ((0, -1) if offset_y < 0 else (0,))
            for ox in ox_range:
                for oy in oy_range:
                    if (key[0]+ox, key[1]+oy) not in self.pathfinder.walkable:
                        return False
            return True

        # Se la mossa calcolata ci manda a sbattere, proviamo a muoverci solo su un asse (sliding)
        if move_x != 0 or move_y != 0:
            step_check = 0.25 # Aumentato da 0.15 per rilevare i muri prima
            if not is_safe(move_x * step_check, move_y * step_check):
                if move_x != 0 and is_safe(move_x * step_check, 0):
                    move_y = 0
                elif move_y != 0 and is_safe(0, move_y * step_check):
                    move_x = 0
                else:
                    self.auto_stuck_timer += dt * 1.5 
            
        # Assegna i tasti finali
        want = set()
        if move_x == 1: want.add('D')
        elif move_x == -1: want.add('A')
        if move_y == 1: want.add('W')
        elif move_y == -1: want.add('S')

        current = set(self.key_ctrl.pressed)
        for k in want - current:  self.key_ctrl.press(k)
        for k in current - want:  self.key_ctrl.release(k)

        total_wp = len(self.auto_path)
        self.auto_status_msg = (f"wp {self.auto_path_index+1}/{total_wp}  "
                                f"d={dist:.2f}")

    # ================= VARIE =================
    def _clear_trail(self):
        self.trail = []

    def _reset_distance(self):
        self.total_distance = 0.0
        self.last_pos_for_dist = None
        self.session_start = time.time()

    def _ricarica_mappa(self):
        self.visitati_coords = []
        self.carica_mappa()
        self._calcola_bounds_mappa()
        self.pathfinder.rebuild(self.visitati_coords)
        dpg.delete_item("map_node", children_only=True)
        dpg.push_container_stack("map_node")
        step_u = GPSConfig.CELL_STEP
        for kx, ky in self.visitati_coords:
            dpg.draw_rectangle((kx, -ky), (kx + step_u, -ky + step_u),
                               color=Colors.VISITED, fill=Colors.VISITED)
        dpg.pop_container_stack()
        dpg.set_value("stat_visited", f"{len(self.visitati_coords)}")
        dpg.set_value("stat_walkable", f"{len(self.pathfinder.walkable)}")

    def _esporta_trail(self):
        try:
            with open("trail_export.json", "w") as f:
                json.dump({"trail": [[p[0], p[1]] for p in self.trail]}, f)
            print("Trail esportato in trail_export.json")
        except Exception as e:
            print(f"Errore export: {e}")

    def _esporta_tutto(self):
        """
        Esporta in un'unica cartella con timestamp:
          - mappa_skeld.json
          - task_registrate.json
          - zone_skeld.json
          - mappa_preview.png  (rendering vettoriale dall'alto)
          - export.zip         (tutti i file sopra)
        """
        import zipfile, shutil
        from datetime import datetime

        # --- 1. Cartella di destinazione con timestamp ---
        ts        = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir   = f"export_{ts}"
        os.makedirs(out_dir, exist_ok=True)

        # --- 2. Copia JSON ---
        copiati = []
        for src in (GPSConfig.MAP_FILE, GPSConfig.TASK_FILE,
                    GPSConfig.ZONE_FILE, GPSConfig.POI_FILE):
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(out_dir, os.path.basename(src)))
                copiati.append(os.path.basename(src))

        # --- 3. Genera PNG mappa in 5 risoluzioni ---
        RISOLUZIONI = [512, 1024, 2048, 4096, 8192]
        ok_png = False
        for res in RISOLUZIONI:
            png_nome = f"mappa_{res}px.png"
            png_path = os.path.join(out_dir, png_nome)
            ok = self._genera_png_mappa(png_path, img_size=res)
            if ok:
                ok_png = True
        # --- 4. Crea ZIP ---
        zip_path = f"export_{ts}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(out_dir):
                for fname in files:
                    fpath = os.path.join(root, fname)
                    zf.write(fpath, arcname=fname)

        # --- 5. Feedback ---
        png_msg = "+ 5x PNG (512→8192px)" if ok_png else "(Pillow non installato: PNG saltati)"
        self.auto_status_msg = f"Esportato → {zip_path}  ({', '.join(copiati)} {png_msg})"
        print(f"[EXPORT] {zip_path}  |  cartella: {out_dir}")

    def _genera_png_mappa(self, output_path, img_size=1200):
        """
        Disegna la mappa su un'immagine PIL e la salva come PNG.
        Colori:
          - sfondo scuro
          - celle visitate = grigio scuro
          - zone = colore zona semi-trasparente
          - task normale = arancione  |  vitale = rosso  |  fatta = (non disponibile offline)
          - fasi task = ciano, collegate da linea
          - trail = giallo (se presente)
        """
        try:
            from PIL import Image, ImageDraw, ImageFont
        except ImportError:
            print("[EXPORT] Pillow non installato. Installa con: pip install Pillow")
            return False

        import math as _m

        # ---- bounds ----
        if not self.visitati_coords:
            return False
        xs = [p[0] for p in self.visitati_coords]
        ys = [p[1] for p in self.visitati_coords]
        pad = 2.0
        min_x, max_x = min(xs) - pad, max(xs) + pad
        min_y, max_y = min(ys) - pad, max(ys) + pad
        span_x = max_x - min_x
        span_y = max_y - min_y
        scale  = img_size / max(span_x, span_y)

        img_w = int(span_x * scale) + 1
        img_h = int(span_y * scale) + 1

        def to_px(gx, gy):
            """Game coords → pixel (Y invertita: gioco ha Y verso l'alto)."""
            px = int((gx - min_x) * scale)
            py = int((max_y - gy) * scale)   # flip Y
            return (px, py)

        # ---- immagine base ----
        img  = Image.new("RGB", (img_w, img_h), color=(12, 12, 15))
        draw = ImageDraw.Draw(img, "RGBA")

        # ---- celle visitate ----
        cell_px = max(2, int(GPSConfig.CELL_STEP * scale))
        for gx, gy in self.visitati_coords:
            px, py = to_px(gx, gy)
            draw.rectangle([px, py - cell_px, px + cell_px, py], fill=(50, 50, 58))

        # ---- zone (poligoni semi-trasparenti) ----
        for zona in self.zone_mgr.zone:
            punti = zona.get('punti', [])
            if len(punti) < 3:
                continue
            hex_col = zona.get('colore', '#3498DB')
            h = hex_col.lstrip('#')
            r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
            poly_px = [to_px(p[0], p[1]) for p in punti]
            draw.polygon(poly_px, fill=(r, g, b, 45), outline=(r, g, b, 180))
            # Nome zona al centroide
            cx = sum(p[0] for p in punti) / len(punti)
            cy = sum(p[1] for p in punti) / len(punti)
            tx, ty = to_px(cx, cy)
            draw.text((tx, ty), zona['nome'], fill=(r, g, b, 220))

        # ---- trail ----
        if len(self.trail) >= 2:
            trail_px = [to_px(p[0], p[1]) for p in self.trail]
            for i in range(len(trail_px) - 1):
                alpha = int(60 + 160 * (i / max(1, len(trail_px) - 1)))
                draw.line([trail_px[i], trail_px[i + 1]],
                          fill=(255, 200, 0, alpha), width=2)

        # ---- task ----
        R_task = max(5, int(8 * scale / 60))   # raggio proporzionale allo zoom
        for t in self.task_mgr.task_list:
            is_vitale = bool(t.get('vitale', False))
            is_due_p  = bool(t.get('due_giocatori', False))

            col = (255, 40, 40) if is_vitale else (255, 140, 0)

            mx, my = to_px(t['x'], t['y'])

            # Glow esterno per task vitali
            if is_vitale:
                draw.ellipse([mx - R_task - 5, my - R_task - 5,
                              mx + R_task + 5, my + R_task + 5],
                             fill=(255, 40, 40, 60), outline=None)

            draw.ellipse([mx - R_task - 3, my - R_task - 3,
                          mx + R_task + 3, my + R_task + 3],
                         fill=(*col, 50), outline=(*col, 200), width=2)
            draw.ellipse([mx - R_task, my - R_task,
                          mx + R_task, my + R_task],
                         fill=(*col, 220))

            # Etichetta task
            tag_str  = ("[!] " if is_vitale else "") + ("[2P] " if is_due_p else "")
            label    = f"{tag_str}{t['nome']}"
            draw.text((mx - len(label) * 3, my - R_task - 14), label,
                      fill=(255, 255, 255, 220))

            # Fasi: linea + cerchio ciano numerato
            fasi = t.get('fasi', [])
            prev_px = (mx, my)
            for i, fase in enumerate(fasi, start=1):
                fsx, fsy = to_px(fase['x'], fase['y'])
                # linea di collegamento con freccia a metà
                draw.line([prev_px, (fsx, fsy)], fill=(*col, 160), width=2)
                # freccia a metà
                hx = (prev_px[0] + fsx) // 2
                hy = (prev_px[1] + fsy) // 2
                ang = _m.atan2(fsy - prev_px[1], fsx - prev_px[0])
                al  = 8
                draw.line([(hx, hy),
                            (int(hx - al * _m.cos(ang - 0.4)),
                             int(hy - al * _m.sin(ang - 0.4)))],
                          fill=(*col, 200), width=2)
                draw.line([(hx, hy),
                            (int(hx - al * _m.cos(ang + 0.4)),
                             int(hy - al * _m.sin(ang + 0.4)))],
                          fill=(*col, 200), width=2)
                # cerchio fase
                draw.ellipse([fsx - R_task, fsy - R_task,
                               fsx + R_task, fsy + R_task],
                             fill=(100, 200, 255, 220),
                             outline=(*col, 180), width=2)
                draw.text((fsx - 4, fsy - 7), str(i), fill=(10, 10, 10, 255))
                draw.text((fsx - len(fase['nome']) * 3, fsy - R_task - 14),
                          fase['nome'], fill=(200, 230, 255, 210))
                prev_px = (fsx, fsy)

        # ---- punti di interesse ----
        COL_POI = (80, 200, 255)
        for p in self.poi_mgr.poi_list:
            ppx, ppy = to_px(p['x'], p['y'])
            r_poi = max(6, int(10 * scale / 60))
            draw.ellipse([ppx - r_poi - 3, ppy - r_poi - 3,
                          ppx + r_poi + 3, ppy + r_poi + 3],
                         fill=(*COL_POI, 40), outline=(*COL_POI, 200), width=2)
            draw.ellipse([ppx - r_poi, ppy - r_poi,
                          ppx + r_poi, ppy + r_poi],
                         fill=(*COL_POI, 200))
            draw.text((ppx - 4, ppy - 7), "★", fill=(15, 15, 15, 255))
            zona_sfx  = f"  [{p['zone_nome']}]" if p.get('zone_nome') else ""
            poi_label = f"{p['nome']}{zona_sfx}"
            draw.text((ppx - len(poi_label) * 3, ppy - r_poi - 14),
                      poi_label, fill=(*COL_POI, 230))

        # ---- giocatore (posizione attuale) ----
        if self.pos_target != [0.0, 0.0]:
            ppx, ppy = to_px(self.pos_target[0], self.pos_target[1])
            draw.ellipse([ppx - 10, ppy - 10, ppx + 10, ppy + 10],
                         fill=(0, 255, 100, 60))
            draw.ellipse([ppx - 6, ppy - 6, ppx + 6, ppy + 6],
                         fill=(0, 255, 100, 230))
            draw.text((ppx + 10, ppy - 8), "YOU", fill=(0, 255, 100, 255))

        # ---- legenda ----
        lx, ly = 10, img_h - 90
        draw.rectangle([lx - 4, ly - 4, lx + 220, ly + 82],
                       fill=(20, 20, 25, 200))
        items_leg = [
            ((255, 140,  0), "Task da fare"),
            ((255,  40, 40), "[!] Task vitale"),
            ((100, 200, 255), "Fase secondaria"),
            ((0,  255, 100), "Posizione giocatore"),
        ]
        for i, (col_l, txt_l) in enumerate(items_leg):
            draw.ellipse([lx, ly + i*18, lx+10, ly + i*18 + 10], fill=col_l)
            draw.text((lx + 16, ly + i*18 - 1), txt_l, fill=(220, 220, 220))

        img.save(output_path, "PNG")
        return True


    def _show_help(self):
        if dpg.does_item_exist("help_win"):
            dpg.show_item("help_win"); return
        with dpg.window(label="Informazioni", tag="help_win",
                        width=520, height=470, pos=(180, 130)):
            dpg.add_text("Among Us — Among Us AI Bot", color=Colors.ACCENT)
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
            dpg.add_text("A* lavora sulle celle già visitate del mapper.",
                         color=Colors.TEXT_DIM)
            dpg.add_text("Più la mappa è completa, più il percorso è ottimale.",
                         color=Colors.TEXT_DIM)
            dpg.add_text("Il path viene semplificato con 'string-pulling'.",
                         color=Colors.TEXT_DIM)
            dpg.add_text("Se il player resta fermo >0.8s, si fa replan.",
                         color=Colors.TEXT_DIM)
            dpg.add_text("Se la mappa ha buchi, dilate +1 cella li tappa.",
                         color=Colors.TEXT_DIM)

    # ================= FRAME =================
    def _update_trail_and_distance(self):
        now = time.time()
        if now - self.last_trail_time >= GPSConfig.TRAIL_INTERVAL:
            self.trail.append((self.pos_target[0], self.pos_target[1]))
            if len(self.trail) > GPSConfig.TRAIL_MAX:
                self.trail.pop(0)
            self.last_trail_time = now
        if self.last_pos_for_dist is not None:
            dx = self.pos_target[0] - self.last_pos_for_dist[0]
            dy = self.pos_target[1] - self.last_pos_for_dist[1]
            d = math.hypot(dx, dy)
            if 0.0005 < d < 5.0:
                self.total_distance += d
        self.last_pos_for_dist = list(self.pos_target)

    def _controlla_task_attiva(self, task_x, task_y):
        """
        Controlla a schermo se c'è il pulsante USE acceso o l'alone giallo
        sulla task a coordinate di gioco (task_x, task_y).
        Ritorna True se la task sembra attiva qui, False altrimenti.
        """
        if not _WIN_OK:
            return True
            
        try:
            import mss
            import numpy as np
        except ImportError:
            return True

        hwnd = win32gui.FindWindow(None, "Among Us")
        if not hwnd:
            return True 

        rect = get_client_rect(hwnd)
        if not rect:
            return True
        cx, cy, cw, ch = rect

        with mss.mss() as sct:
            monitor = {"top": cy, "left": cx, "width": cw, "height": ch}
            try:
                img = np.array(sct.grab(monitor))[:, :, :3] # BGR
            except Exception:
                return True

        # 1. Controlla il pulsante USE in basso a destra (16:9 / 16:10)
        use_roi_x1 = int(cw * 0.82)
        use_roi_x2 = int(cw * 0.98)
        use_roi_y1 = int(ch * 0.80)
        use_roi_y2 = int(ch * 0.96)
        use_region = img[use_roi_y1:use_roi_y2, use_roi_x1:use_roi_x2]
        
        use_active = False
        if use_region.size > 0:
            # Cerca densità di pixel molto luminosi (testo bianco o colori accesi)
            bright_pixels = np.sum(np.all(use_region > 220, axis=2))
            if bright_pixels > 100:
                use_active = True
                
        # 2. Controlla alone giallo sulla task
        cam_x, cam_y = self.pos_target
        cam_h = getattr(self, 'yolo_camera_height', 6.0)
        ppu = ch / cam_h
        
        dx = task_x - cam_x
        dy = task_y - (cam_y + 0.36) # Offset altezza camera
        
        screen_x = int(cw / 2 + dx * ppu)
        screen_y = int(ch / 2 - dy * ppu)
        
        glow_active = False
        if 0 <= screen_x < cw and 0 <= screen_y < ch:
            r_sz = int(ppu * 0.6) 
            y1 = max(0, screen_y - r_sz)
            y2 = min(ch, screen_y + r_sz)
            x1 = max(0, screen_x - r_sz)
            x2 = min(cw, screen_x + r_sz)
            
            target_region = img[y1:y2, x1:x2]
            if target_region.size > 0:
                # Giallo in BGR: B < 150, G > 200, R > 200
                yellow_pixels = np.sum((target_region[:,:,0] < 150) & (target_region[:,:,1] > 200) & (target_region[:,:,2] > 200))
                if yellow_pixels > 20:
                    glow_active = True
                    
        return use_active or glow_active

    def _cerca_glow_fratelli(self, lista_punti):
        """Scansiona lo schermo per cercare l'alone giallo su una lista di coordinate di gioco."""
        if not _WIN_OK: return None
        try:
            import mss
            import numpy as np
        except ImportError:
            return None

        hwnd = win32gui.FindWindow(None, "Among Us")
        if not hwnd: return None
        rect = get_client_rect(hwnd)
        if not rect: return None
        cx_w, cy_w, cw, ch = rect

        with mss.mss() as sct:
            monitor = {"top": cy_w, "left": cx_w, "width": cw, "height": ch}
            try:
                img = np.array(sct.grab(monitor))[:, :, :3] # BGR
            except Exception:
                return None
                
        cam_x, cam_y = self.pos_target
        cam_h = getattr(self, 'yolo_camera_height', 6.0)
        ppu = ch / cam_h
        
        for px, py in lista_punti:
            dx = px - cam_x
            dy = py - (cam_y + 0.36) # Offset altezza camera
            screen_x = int(cw / 2 + dx * ppu)
            screen_y = int(ch / 2 - dy * ppu)
            if 0 <= screen_x < cw and 0 <= screen_y < ch:
                r_sz = int(ppu * 0.6) 
                y1 = max(0, screen_y - r_sz); y2 = min(ch, screen_y + r_sz)
                x1 = max(0, screen_x - r_sz); x2 = min(cw, screen_x + r_sz)
                target_region = img[y1:y2, x1:x2]
                if target_region.size > 0:
                    yellow_pixels = np.sum((target_region[:,:,0] < 150) & (target_region[:,:,1] > 200) & (target_region[:,:,2] > 200))
                    if yellow_pixels > 20: return (px, py)
        return None

    def aggiorna_frame(self):
        dt = dpg.get_delta_time()
        if dt > 0.1: dt = 0.1

        # --- HOTKEY GLOBALE PER STOP TASK (F4 o END/FINE) ---
        if _WIN_OK:
            f4_pressed = (win32api.GetAsyncKeyState(0x73) & 0x8000) != 0
            end_pressed = (win32api.GetAsyncKeyState(0x23) & 0x8000) != 0
            if (f4_pressed or end_pressed) and not getattr(self, '_prev_stop_key', False):
                stop_flag.requested = True
                self._cancel_auto_move()
                self._ferma_processo_task()
                self._task_launch_arrivo = False
                try:
                    pyautogui.mouseUp(button='left')
                except Exception:
                    pass
                if dpg.does_item_exist("task_launch_popup"):
                    dpg.delete_item("task_launch_popup")
                self.auto_status_msg = "⏹ Esecuzione annullata (Stop)"
            self._prev_stop_key = (f4_pressed or end_pressed)

        self._update_trail_and_distance()
        self._update_auto_move(dt)
        self._update_task_launch(dt)
        self._controlla_processo_task()
        self._update_auto_all(dt)
        
        pending_2p = getattr(self, '_pending_next_2p_task', None)
        if pending_2p is not None:
            self._pending_next_2p_task = None
            if self.auto_enabled:
                task_reg = self.task_mgr.get_by_id(pending_2p)
                if task_reg:
                    t_mem = None
                    for enriched in self.task_mgr.get_memory_tasks_info(self.memory_tasks):
                        if enriched.get('reg_task') and enriched['reg_task']['id'] == pending_2p:
                            t_mem = enriched
                            break
                    if t_mem:
                        self._naviga_a_task_memoria(task_to_nav=t_mem)
                    else:
                        self.auto_enabled = True
                        target_2p, step_2p = self._imposta_navigazione_2p(task_reg)
                        if target_2p:
                            self._plan_path(target_2p)
                            self.auto_status_msg = f"Navigo verso '{task_reg['nome']}' (Tappa {step_2p})"

        # Editor azioni (se aperto): aggiorna preview + gestisci Ctrl+Click
        if self.action_editor.e_aperto():
            self.action_editor.tick()

        # Aggiorna label stato processo accanto al pulsante Stop
        if dpg.does_item_exist("processo_status"):
            if self._task_process is not None and self._task_process.poll() is None:
                task_att = self.task_mgr.get_by_id(self._task_process_task_id)
                nome_att = task_att['nome'] if task_att else "?"
                dpg.configure_item("processo_status", color=(0, 220, 120, 255))
                dpg.set_value("processo_status", f"▶ {nome_att}")
            else:
                dpg.configure_item("processo_status", color=(120, 120, 120, 200))
                dpg.set_value("processo_status", "nessun processo")

        # Aggiorna listbox task memoria con timer fisso (ogni 0.3s)
        self._mem_task_refresh_acc = getattr(self, '_mem_task_refresh_acc', 0.0) + dt
        if self._mem_task_refresh_acc >= 0.3:
            self._mem_task_refresh_acc = 0.0
            self._refresh_mem_task_listbox()

        # Refresh listbox task registrate se il thread ha aggiornato i nomi
        if self._pending_refresh_task_list:
            self._pending_refresh_task_list = False
            self._refresh_reg_task_listbox()

        factor = 1.0 - math.exp(-GPSConfig.SMOOTHING * dt)
        self.pos_visuale[0] += (self.pos_target[0] - self.pos_visuale[0]) * factor
        self.pos_visuale[1] += (self.pos_target[1] - self.pos_visuale[1]) * factor

        cam_x, cam_y = self._camera_center()
        half_w = self.canvas_w / 2
        half_h = self.canvas_h / 2
        scale = self.scale

        trans_x = half_w - scale * cam_x
        trans_y = half_h + scale * cam_y
        scale_mat = dpg.create_scale_matrix([scale, scale])
        trans_mat = dpg.create_translation_matrix([trans_x, trans_y])
        dpg.apply_transform("map_node", trans_mat * scale_mat)

        self._render_grid(cam_x, cam_y, half_w, half_h, scale)
        self._render_zones(cam_x, cam_y, half_w, half_h, scale)
        self._render_tasks(cam_x, cam_y, half_w, half_h, scale)
        self._render_poi(cam_x, cam_y, half_w, half_h, scale)
        self._render_trail(cam_x, cam_y, half_w, half_h, scale)
        self._render_path(cam_x, cam_y, half_w, half_h, scale)
        self._render_target(cam_x, cam_y, half_w, half_h, scale)
        self._render_doors(cam_x, cam_y, half_w, half_h, scale)
        self._render_other_players(cam_x, cam_y, half_w, half_h, scale)
        self._render_player(cam_x, cam_y, half_w, half_h, scale)
        self._render_hud()

    def _render_grid(self, cam_x, cam_y, half_w, half_h, scale):
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

    def _render_tasks(self, cam_x, cam_y, half_w, half_h, scale):
        """Disegna le task con colori dinamici: Arancione (da fare), Verde (completata), Rosso (vitale)."""
        dpg.delete_item("task_node", children_only=True)
        if not self.task_mgr.task_list:
            return
        dpg.push_container_stack("task_node")

        # Palette colori richiesta
        COL_DA_FARE      = (255, 140,   0, 230) # Arancione acceso
        COL_DA_FARE_FILL = (255, 140,   0,  60)
        COL_FATTA        = (  0, 255,   0, 230) # Verde acceso
        COL_FATTA_FILL   = (  0, 255,   0,  60)
        COL_VITALE       = (255,  30,  30, 240) # Rosso intenso
        COL_VITALE_FILL  = (255,  30,  30,  70)
        
        COL_FASE         = (100, 200, 255, 200)
        COL_TESTO        = (255, 255, 255, 255)
        COL_BG_LBL       = ( 20,  20,  25, 200)
        R = GPSConfig.TASK_ICON_RADIUS

        # 1. Mappatura stato dalla memoria
        active_keys = set()
        completed_keys = set()
        for mt in getattr(self, 'memory_tasks', []):
            chiave_mem = (mt.get('tipo'), mt.get('room_id'))
            active_keys.add(chiave_mem)
            if mt.get('done', False):
                completed_keys.add(chiave_mem)

        for t in self.task_mgr.task_list:
            chiave_task = (t.get('tipo'), t.get('room_id'))
            is_vitale      = bool(t.get('vitale', False))
            is_due_p       = bool(t.get('due_giocatori', False))

            # Filtro opzionale: mostra solo se attiva in memoria
            if getattr(self, 'show_only_active_tasks', False) and chiave_task not in active_keys:
                continue

            # 2. Determinazione colore in base allo stato
            if chiave_task in completed_keys:
                # Task FATTA -> Verde (anche se vitale, ormai è completata)
                col_bordo = COL_FATTA
                col_fill  = COL_FATTA_FILL
                stato_testo = "[FATTA]"
            elif is_vitale:
                # Task VITALE DA FARE -> Rosso
                col_bordo = COL_VITALE
                col_fill  = COL_VITALE_FILL
                stato_testo = "[!] VITALE"
            elif chiave_task in active_keys:
                # Task DA FARE -> Arancione
                col_bordo = COL_DA_FARE
                col_fill  = COL_DA_FARE_FILL
                stato_testo = "[DA FARE]"
            else:
                # Task registrata ma non presente in questa partita
                col_bordo = (150, 150, 150, 150) # Grigio neutro
                col_fill  = (150, 150, 150,  40)
                stato_testo = "[NON IN LISTA]"

            # Calcolo coordinate schermo
            tx, ty = t['x'], t['y']
            sx = half_w + scale * (tx - cam_x)
            sy = half_h - scale * (ty - cam_y)

            # Culling per prestazioni
            if sx < -50 or sx > self.canvas_w + 50 or sy < -50 or sy > self.canvas_h + 50:
                continue

            # Disegno Marcatore
            # Per le task vitali aggiungiamo un anello esterno extra per farle risaltare
            if is_vitale and chiave_task not in completed_keys:
                pulse = 0.5 + 0.5 * __import__('math').sin(__import__('time').time() * 4)
                r_glow = int(R + 8 + pulse * 5)
                glow_alpha = int(80 + pulse * 80)
                dpg.draw_circle((sx, sy), r_glow,
                                color=(255, 30, 30, glow_alpha),
                                fill=(255, 30, 30, int(glow_alpha * 0.3)),
                                thickness=2)

            dpg.draw_circle((sx, sy), R + 4, color=col_bordo, fill=col_fill, thickness=2)
            dpg.draw_circle((sx, sy), R, color=col_bordo, fill=col_bordo, thickness=1)

            # Etichetta informativa
            due_p_tag = " [2P]" if is_due_p else ""
            label = f"{stato_testo}{due_p_tag} {t['nome']}"
            txt_w = max(20, len(label) * 7)
            dpg.draw_rectangle(
                (sx - txt_w / 2 - 4, sy - R - 20),
                (sx + txt_w / 2 + 4, sy - R - 4),
                color=col_bordo, fill=COL_BG_LBL)
            dpg.draw_text((sx - txt_w / 2, sy - R - 18),
                          label, color=COL_TESTO, size=13)

            # Disegno Fasi (se presenti) — punti numerati collegati con linea tratteggiata
            fasi = t.get('fasi', [])
            if fasi:
                # Tutti i punti in sequenza: prima la task principale, poi le fasi
                tutti_punti = [(sx, sy)] + [
                    (half_w + scale * (f['x'] - cam_x),
                     half_h - scale * (f['y'] - cam_y))
                    for f in fasi
                ]
                nomi_fasi  = [t['nome']] + [f['nome'] for f in fasi]

                # Linee di collegamento tra i punti in sequenza
                for i in range(len(tutti_punti) - 1):
                    ax, ay = tutti_punti[i]
                    bx, by = tutti_punti[i + 1]
                    # Linea principale colorata
                    dpg.draw_line((ax, ay), (bx, by),
                                  color=(col_bordo[0], col_bordo[1], col_bordo[2], 160),
                                  thickness=2)
                    # Freccia a metà linea per indicare la direzione
                    mx, my = (ax + bx) / 2, (ay + by) / 2
                    import math as _m
                    ang = _m.atan2(by - ay, bx - ax)
                    arrow_len = 8
                    ax1 = mx - arrow_len * _m.cos(ang - 0.4)
                    ay1 = my - arrow_len * _m.sin(ang - 0.4)
                    ax2 = mx - arrow_len * _m.cos(ang + 0.4)
                    ay2 = my - arrow_len * _m.sin(ang + 0.4)
                    dpg.draw_line((mx, my), (ax1, ay1),
                                  color=(col_bordo[0], col_bordo[1], col_bordo[2], 200),
                                  thickness=2)
                    dpg.draw_line((mx, my), (ax2, ay2),
                                  color=(col_bordo[0], col_bordo[1], col_bordo[2], 200),
                                  thickness=2)

                # Punti fase (dal secondo in poi — il primo è già disegnato come task principale)
                for i, (fsx, fsy) in enumerate(tutti_punti[1:], start=1):
                    # Cerchio fase
                    dpg.draw_circle((fsx, fsy), R + 2,
                                    color=(col_bordo[0], col_bordo[1], col_bordo[2], 180),
                                    fill=(col_bordo[0], col_bordo[1], col_bordo[2], 50),
                                    thickness=2)
                    dpg.draw_circle((fsx, fsy), 6, color=COL_FASE, fill=COL_FASE)

                    # Numero della fase dentro al cerchio
                    num_str = str(i)
                    dpg.draw_text((fsx - 4, fsy - 7), num_str, color=(10, 10, 10, 255), size=13)

                    # Etichetta nome fase
                    flabel = nomi_fasi[i]
                    ftxt_w = max(20, len(flabel) * 7)
                    dpg.draw_rectangle(
                        (fsx - ftxt_w / 2 - 4, fsy - R - 20),
                        (fsx + ftxt_w / 2 + 4, fsy - R - 4),
                        color=(col_bordo[0], col_bordo[1], col_bordo[2], 160),
                        fill=COL_BG_LBL)
                    dpg.draw_text((fsx - ftxt_w / 2, fsy - R - 18),
                                  flabel, color=COL_TESTO, size=13)

                # Aggiunge "①" al marker principale per coerenza visiva
                dpg.draw_text((sx - 4, sy - 7), "0", color=(10, 10, 10, 255), size=13)

            # Punti fratello (simili a fasi ma senza collegamenti o con linea diversa)
            fratelli = t.get('fratelli', [])
            for i, frat in enumerate(fratelli, start=1):
                fsx = half_w + scale * (frat['x'] - cam_x)
                fsy = half_h - scale * (frat['y'] - cam_y)
                dpg.draw_line((sx, sy), (fsx, fsy),
                              color=(col_bordo[0], col_bordo[1], col_bordo[2], 100),
                              thickness=1)
                dpg.draw_circle((fsx, fsy), R,
                                color=(col_bordo[0], col_bordo[1], col_bordo[2], 180),
                                fill=(col_bordo[0], col_bordo[1], col_bordo[2], 50),
                                thickness=2)
                dpg.draw_text((fsx - 4, fsy - 7), f"F{i}", color=(200, 200, 200, 255), size=12)

        dpg.pop_container_stack()

    # ================= PUNTI DI INTERESSE =================

    def _refresh_poi_listbox(self):
        items = []
        for p in self.poi_mgr.poi_list:
            zona_str = f"  [{p['zone_nome']}]" if p.get('zone_nome') else ""
            items.append(f"[{p['id']:02d}] {p['nome']}{zona_str}")
        if dpg.does_item_exist("poi_listbox"):
            dpg.configure_item("poi_listbox", items=items)

    def _get_selected_poi(self):
        if not self.poi_mgr.poi_list:
            return None
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
        p = self._get_selected_poi()
        if p is None:
            self.auto_status_msg = "Seleziona un POI dalla lista"
            return
        if not self.auto_enabled:
            self.auto_enabled = True
            if dpg.does_item_exist("auto_checkbox"):
                dpg.set_value("auto_checkbox", True)
        self._plan_path((p['x'], p['y']))
        self.auto_status_msg = f"Navigo verso POI '{p['nome']}'"

    def _elimina_poi(self):
        p = self._get_selected_poi()
        if p is None:
            self.auto_status_msg = "Seleziona un POI da eliminare"
            return
        nome  = p['nome']
        id_p  = p['id']
        def on_confirm(yes):
            if yes:
                self.poi_mgr.rimuovi(id_p)
                self._refresh_poi_listbox()
                self.auto_status_msg = f"POI '{nome}' eliminato"
        self._show_confirm(f"Eliminare il POI '{nome}'?", on_confirm)

    def _apri_popup_nuovo_poi(self):
        tag = "popup_nuovo_poi"
        if dpg.does_item_exist(tag):
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
            nome_v = dpg.get_value("np_nome").strip()
            x_v    = dpg.get_value("np_x")
            y_v    = dpg.get_value("np_y")
            if not nome_v:
                return
            zona_s  = self._zona_alla_posizione(x_v, y_v) or zona_now
            gz_id_s = zona_s.get('game_zone_id') if zona_s else gz_id_now
            zl_id_s = zona_s['id']               if zona_s else zl_id_now
            self.poi_mgr.aggiungi(
                nome_v, x_v, y_v,
                zone_id       = gz_id_s,
                zone_local_id = zl_id_s,
                zone_nome     = zona_s['nome'] if zona_s else None,
            )
            self._refresh_poi_listbox()
            self.auto_status_msg = f"POI '{nome_v}' aggiunto"
            if dpg.does_item_exist(tag):
                dpg.delete_item(tag)

        def do_usa_pos(*_):
            nx = round(self.pos_target[0], 3)
            ny = round(self.pos_target[1], 3)
            dpg.set_value("np_x", nx)
            dpg.set_value("np_y", ny)
            z2 = self._zona_alla_posizione(nx, ny)
            if z2:
                gz2   = z2.get('game_zone_id')
                info2 = f"[{z2['id']:02d}] {z2['nome']}" + (f"  GZ:{gz2}" if gz2 is not None else "")
            else:
                info2 = "Fuori da qualsiasi zona"
            if dpg.does_item_exist("np_zona_info"):
                dpg.set_value("np_zona_info", info2)

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
                               callback=lambda *a: dpg.delete_item(tag)
                               if dpg.does_item_exist(tag) else None)

    def _apri_popup_modifica_poi(self):
        p = self._get_selected_poi()
        if p is None:
            self.auto_status_msg = "Seleziona un POI da modificare"
            return
        tag  = "popup_modifica_poi"
        if dpg.does_item_exist(tag):
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
            zona_info = p.get('zone_nome') or "Fuori da qualsiasi zona"
            col_zona  = (200, 120, 30, 255)

        def do_salva(*_):
            nome_v = dpg.get_value("mp_nome").strip()
            x_v    = dpg.get_value("mp_x")
            y_v    = dpg.get_value("mp_y")
            if not nome_v:
                return
            zona_s  = self._zona_alla_posizione(x_v, y_v) or zona_now
            gz_id_s = zona_s.get('game_zone_id') if zona_s else None
            zl_id_s = zona_s['id']               if zona_s else None
            self.poi_mgr.aggiorna(
                id_p, nome_v, x_v, y_v,
                zone_id       = gz_id_s,
                zone_local_id = zl_id_s,
                zone_nome     = zona_s['nome'] if zona_s else None,
            )
            self._refresh_poi_listbox()
            self.auto_status_msg = f"POI [{id_p}] aggiornato"
            if dpg.does_item_exist(tag):
                dpg.delete_item(tag)

        def do_usa_pos(*_):
            nx = round(self.pos_target[0], 3)
            ny = round(self.pos_target[1], 3)
            dpg.set_value("mp_x", nx)
            dpg.set_value("mp_y", ny)
            z2 = self._zona_alla_posizione(nx, ny)
            if z2:
                gz2   = z2.get('game_zone_id')
                info2 = f"[{z2['id']:02d}] {z2['nome']}" + (f"  GZ:{gz2}" if gz2 is not None else "")
            else:
                info2 = "Fuori da qualsiasi zona"
            if dpg.does_item_exist("mp_zona_info"):
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
                               callback=lambda *a: dpg.delete_item(tag)
                               if dpg.does_item_exist(tag) else None)

    def _render_poi(self, cam_x, cam_y, half_w, half_h, scale):
        dpg.delete_item("poi_node", children_only=True)
        if not self.show_poi or not self.poi_mgr.poi_list:
            return
        dpg.push_container_stack("poi_node")

        import math as _m, time as _t
        pulse   = 0.5 + 0.5 * _m.sin(_t.time() * 3)
        COL     = (80, 200, 255)   # ciano fisso per tutti i POI
        COL_LBL = (15, 15, 20, 210)
        R = 10

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

            # Rombo centrale (★ → segnalino POI)
            dpg.draw_text((sx - 4, sy - 7), "★", color=(15, 15, 15, 255), size=14)

            # Etichetta: nome  [zona]
            zona_sfx = f"  [{p['zone_nome']}]" if p.get('zone_nome') else ""
            label    = f"{p['nome']}{zona_sfx}"
            txt_w    = max(20, len(label) * 7)
            dpg.draw_rectangle(
                (sx - txt_w / 2 - 4, sy - R - 22),
                (sx + txt_w / 2 + 4, sy - R - 4),
                color=(*COL, 180), fill=COL_LBL)
            dpg.draw_text((sx - txt_w / 2, sy - R - 20),
                          label, color=(*COL, 255), size=13)

        dpg.pop_container_stack()

    def _render_trail(self, cam_x, cam_y, half_w, half_h, scale):
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
        dpg.delete_item("path_node", children_only=True)
        if not self.show_path or not self.auto_path: return
        dpg.push_container_stack("path_node")

        # Converto waypoint in pixel
        pts = []
        for wx, wy in self.auto_path:
            sx = half_w + scale * (wx - cam_x)
            sy = half_h - scale * (wy - cam_y)
            pts.append((sx, sy))

        # Segmenti "fatti" più spenti, segmenti "da fare" accesi
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

    def _render_doors(self, cam_x, cam_y, half_w, half_h, scale):
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

    def _render_other_players(self, cam_x, cam_y, half_w, half_h, scale):
        dpg.delete_item("other_players_node", children_only=True)
        if not self.show_other_players: 
            return
        dpg.push_container_stack("other_players_node")
        
        current_time = time.time()
        for p in self.detected_players:
            age = current_time - p['time']
                
            sx = half_w + scale * (p['x'] - cam_x)
            sy = half_h - scale * (p['y'] - cam_y)
            
            base_color = p.get('color', (255, 50, 50))
            is_dead = p.get('is_dead', False)
            
            display_name = p.get('name', 'Player')
            if display_name == 'Unknown': 
                display_name = 'Player'
            
            if is_dead:
                alpha = 255
                col_bordo = (base_color[0], base_color[1], base_color[2], alpha)
                dpg.draw_circle((sx, sy), 9, color=col_bordo, fill=(30, 30, 30, 200), thickness=2)
                dpg.draw_line((sx - 6, sy - 6), (sx + 6, sy + 6), color=col_bordo, thickness=2)
                dpg.draw_line((sx - 6, sy + 6), (sx + 6, sy - 6), color=col_bordo, thickness=2)
                
                time_str = f"{int(age // 60)}m {int(age % 60)}s" if age > 60 else f"{int(age)}s"
                dpg.draw_text((sx + 12, sy - 12), f"DEAD {display_name} ({time_str})", color=col_bordo, size=15)
                
            elif age <= 4.0:
                # Giocatore appena visto o visto da poco
                alpha = 255
                col_bordo = (base_color[0], base_color[1], base_color[2], alpha)
                col_fill  = (base_color[0], base_color[1], base_color[2], 180)
                dpg.draw_circle((sx, sy), 9, color=col_bordo, fill=col_fill, thickness=2)
                dpg.draw_text((sx + 12, sy - 12), display_name, color=col_bordo, size=15)
            else:
                # "Fantasma" / Ultima posizione nota (dopo i 4 secondi e fino a 30)
                alpha = 220
                col_bordo = (base_color[0], base_color[1], base_color[2], alpha)
                # Disegna una 'X' per indicare un punto nel passato
                dpg.draw_line((sx - 6, sy - 6), (sx + 6, sy + 6), color=col_bordo, thickness=3)
                dpg.draw_line((sx - 6, sy + 6), (sx + 6, sy - 6), color=col_bordo, thickness=3)
                
                time_str = f"{int(age // 60)}m {int(age % 60)}s" if age > 60 else f"{int(age)}s"
                dpg.draw_text((sx + 10, sy - 10), f"Last seen {display_name} ({time_str})", color=col_bordo, size=14)
            
        dpg.pop_container_stack()

    def _render_player(self, cam_x, cam_y, half_w, half_h, scale):
        dpg.delete_item("player_node", children_only=True)
        dpg.push_container_stack("player_node")

        px = half_w + scale * (self.pos_visuale[0] - cam_x)
        py = half_h - scale * (self.pos_visuale[1] - cam_y)

        margin = 20
        on_screen = (margin <= px <= self.canvas_w - margin and
                     margin <= py <= self.canvas_h - margin)

        if on_screen:
            dpg.draw_circle((px, py), 14,
                            color=Colors.PLAYER_GLOW, fill=Colors.PLAYER_GLOW)
            dpg.draw_circle((px, py), 7,
                            color=Colors.PLAYER, fill=Colors.PLAYER)
        else:
            dx = px - half_w; dy = py - half_h
            angle = math.atan2(dy, dx)
            rx = self.canvas_w / 2 - 25
            ry = self.canvas_h / 2 - 25
            bx = half_w + math.cos(angle) * rx
            by = half_h + math.sin(angle) * ry
            dpg.draw_circle((bx, by), 10,
                            color=Colors.PLAYER, fill=Colors.PLAYER)
            ax = bx + math.cos(angle) * 16
            ay = by + math.sin(angle) * 16
            dpg.draw_line((bx, by), (ax, ay),
                          color=Colors.PLAYER, thickness=3)

        if self.show_crosshair:
            dpg.draw_line((half_w - 14, half_h), (half_w + 14, half_h),
                          color=Colors.CROSSHAIR, thickness=1)
            dpg.draw_line((half_w, half_h - 14), (half_w, half_h + 14),
                          color=Colors.CROSSHAIR, thickness=1)

        dpg.pop_container_stack()

    def _render_hud(self):
        dpg.set_value("status_x",    f"X: {self.pos_target[0]:.3f}")
        dpg.set_value("status_y",    f"Y: {self.pos_target[1]:.3f}")
        dpg.set_value("status_fps",  f"FPS: {dpg.get_frame_rate()}")
        dpg.set_value("status_mode", f"Mode: {self.camera_mode}")
        dpg.set_value("status_zoom", f"Zoom: {self.scale:.0f}")

        if self.auto_enabled:
            if self.auto_path:
                dpg.configure_item("status_auto", color=Colors.TARGET)
                dpg.set_value("status_auto", f"Auto: ON ({self.auto_status_msg})")
            else:
                dpg.configure_item("status_auto", color=Colors.ACCENT)
                dpg.set_value("status_auto", "Auto: ARMATO (click mappa)")
        else:
            dpg.configure_item("status_auto", color=Colors.TEXT_DIM)
            dpg.set_value("status_auto", "Auto: OFF")

        dpg.set_value("stat_dist", f"{self.total_distance:.2f} u")
        elapsed = int(time.time() - self.session_start)
        m, s = divmod(elapsed, 60); h, m = divmod(m, 60)
        dpg.set_value("stat_time",
                      f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}")
        dpg.set_value("stat_trail", f"{len(self.trail)}")
        dpg.set_value("auto_state_label",
                      self.auto_status_msg if self.auto_status_msg else "inattivo")
        if self.auto_final_target is not None:
            dpg.set_value("auto_target_label",
                f"X={self.auto_final_target[0]:.2f}  Y={self.auto_final_target[1]:.2f}")
        else:
            dpg.set_value("auto_target_label", "—")
        if self.auto_path:
            dpg.set_value("auto_path_label",
                f"{self.auto_path_index+1} / {len(self.auto_path)} waypoint")
        else:
            dpg.set_value("auto_path_label", "0 waypoint")

        dpg.delete_item("hud_node", children_only=True)
        if self.show_hud:
            dpg.push_container_stack("hud_node")
            label = f"[{self.camera_mode.upper()}]  x{self.scale:.0f}"
            dpg.draw_text((11, 9),  label, color=(0, 0, 0, 220), size=18)
            dpg.draw_text((10, 8),  label, color=Colors.ACCENT, size=18)
            if self.auto_enabled and self.auto_path:
                keys_txt = "+".join(sorted(self.key_ctrl.pressed)) or "—"
                amsg = f"AUTO → {self.auto_status_msg}  |  {keys_txt}"
                dpg.draw_text((11, 33), amsg, color=(0, 0, 0, 220), size=16)
                dpg.draw_text((10, 32), amsg, color=Colors.TARGET, size=16)
            dpg.pop_container_stack()

    def _adatta_punti_alla_mappa(self, punti_originali):
        """Sposta i punti del poligono sulle celle calpestabili più vicine."""
        punti_adattati = []
        for px, py in punti_originali:
            # Cerca la cella calpestabile più vicina al punto disegnato a mano
            cella_vicina = self.pathfinder.nearest_walkable(px, py, radius=10)
            if cella_vicina:
                gx, gy = self.pathfinder._coord(cella_vicina)
                punti_adattati.append([gx, gy])
            else:
                # Se è troppo lontano da zone conosciute, tieni il punto originale
                punti_adattati.append([px, py])
        
        # Rimuove duplicati consecutivi che potrebbero crearsi con lo snap
        risultato = []
        for p in punti_adattati:
            if not risultato or (p[0] != risultato[-1][0] or p[1] != risultato[-1][1]):
                risultato.append(p)
        return risultato

    # ================= MAIN =================
    def run(self):
        print("=== Among Us AI Bot avviato ===")
        print(f"  Celle calpestabili: {len(self.pathfinder.walkable)}")
        print("  SX = destinazione (A*) | DX/ESC = annulla")
        print("  Rotella drag = pan | M = toggle auto-move")

        self._on_viewport_resize()
        try:
            while dpg.is_dearpygui_running():
                self.aggiorna_frame()
                dpg.render_dearpygui_frame()
        finally:
            self.key_ctrl.release_all()
            self.running = False
            dpg.destroy_context()
