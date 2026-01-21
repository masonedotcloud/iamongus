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

