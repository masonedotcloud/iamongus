"""
Applicazione principale: GPS Visualizer Pro.

Orchestra lettura RAM, scanner YOLO, rendering DPG, pathfinding, task,
zone, POI, popup di editing e input simulato.

Per organizzazione, i metodi sono distribuiti in mixin tematici dentro
``among_us_ai/ui/mixins/``. Ogni mixin contiene un blocco coerente di
metodi (es. tutti i ``_render_*`` in ``rendering.py``, tutto il pathfinding
runtime in ``auto_move.py``, ...). I mixin condividono lo stato self.*
inizializzato qui in ``__init__``.

Per orientarsi rapidamente:

============================  ===============================================
Mixin                         Cosa contiene
============================  ===============================================
MemorySyncMixin               Thread RAM (posizione + task)
MapLoaderMixin                Caricamento mappa + bounds
UISetupMixin                  Costruzione interfaccia DPG
YoloScannerMixin              Scanner YOLO altri giocatori / porte
InputCallbacksMixin           Callback mouse/zoom/camera
AutoMoveMixin                 Pathfinding A* + esecuzione cammino
AutoQuestMixin                Modalita' Auto-Quest (scelta task)
ZonesMixin                    UI zone nominate + zone porta
TasksListMixin                Liste task (mem/registrate) + selezione
TasksLifecycleMixin           Lancio task, subprocess, controllo, stop
TasksPopupsMixin              Popup di registrazione/modifica/link task
DialogsMixin                  Dialoghi modali generici
PoiMixin                      Punti di interesse (UI)
RenderingMixin                Tutti i ``_render_*`` chiamati nel frame
MiscMixin                     Trail, esportazione, ricarica mappa
============================  ===============================================

Solo ``__init__``, ``aggiorna_frame`` e ``run`` restano in questo file
perche' sono il "cuore" che lega insieme i mixin e definisce lo stato.
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
from .editor import TaskActionEditor

from .mixins.memory_sync import MemorySyncMixin
from .mixins.map_loader import MapLoaderMixin
from .mixins.ui_setup import UISetupMixin
from .mixins.yolo_scanner import YoloScannerMixin
from .mixins.input_callbacks import InputCallbacksMixin
from .mixins.auto_move import AutoMoveMixin
from .mixins.auto_quest import AutoQuestMixin
from .mixins.zones import ZonesMixin
from .mixins.tasks_list import TasksListMixin
from .mixins.tasks_launch import TasksLaunchMixin
from .mixins.tasks_process import TasksProcessMixin
from .mixins.tasks_popups_register import TasksPopupsRegisterMixin
from .mixins.tasks_popups_edit import TasksPopupsEditMixin
from .mixins.tasks_popups_subitem import TasksPopupsSubitemMixin
from .mixins.dialogs import DialogsMixin
from .mixins.poi import PoiMixin
from .mixins.rendering_world import RenderingWorldMixin
from .mixins.rendering_entities import RenderingEntitiesMixin
from .mixins.misc import MiscMixin
from .mixins.use_button_calib import UseButtonCalibMixin
from .mixins.planner_ui import PlannerMixin
from .mixins.intelligence_sidebar import IntelligenceSidebarMixin


class GPSVisualizerPro(
    # NB: l'ordine di ereditarieta' definisce l'MRO. Tutti i mixin sono
    # disgiunti (nessun metodo definito in piu' di uno), quindi l'ordine
    # qui sotto e' irrilevante per la dispatch - ma e' tenuto coerente
    # con l'ordine dei marker # ================= del file originale.
    MemorySyncMixin,
    MapLoaderMixin,
    UISetupMixin,
    YoloScannerMixin,
    InputCallbacksMixin,
    AutoMoveMixin,
    AutoQuestMixin,
    ZonesMixin,
    TasksListMixin,
    TasksLaunchMixin,
    TasksProcessMixin,
    TasksPopupsRegisterMixin,
    TasksPopupsEditMixin,
    TasksPopupsSubitemMixin,
    DialogsMixin,
    PoiMixin,
    RenderingWorldMixin,
    RenderingEntitiesMixin,
    MiscMixin,
    UseButtonCalibMixin,
    PlannerMixin,
    IntelligenceSidebarMixin,
):
    """Classe principale dell'applicazione: orchestra rendering, pathfinding, lettura RAM, scanner YOLO, esecuzione task."""
    def __init__(self):
        """Inizializza l'istanza con i valori di default."""
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
        # Messaggio di stato mostrato all'utente nel pannello
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

        # --- Task (formato dettagli + esecuzione separati) ---
        self.task_mgr = TaskManager(
            GPSConfig.TASK_DETTAGLI_FILE,
            GPSConfig.TASK_ESECUZIONE_DIR,
            GPSConfig.TASKS_DEF_FILE,
            GPSConfig.TASK_LEGACY_FILE,
        )

        # --- Pianificatore Auto-All ---
        # Decide la sequenza ottimale di task considerando vitalita',
        # lunghezza, multi-fase e distanza A* dal bot.
        from ..managers.task_planner import TaskPlanner
        self.task_planner = TaskPlanner(pathfinder=self.pathfinder)
        # Carico pesi personalizzati da `planner_weights.json` se presenti
        # (sovrascrivono i default di GPSConfig). Import locale per
        # evitare un import circolare con planner_ui.
        from .mixins.planner_ui import PlannerMixin
        PlannerMixin.carica_pesi_da_file()

        # Stato della preview giro Auto-All (popup F1)
        self._preview_giro_aperto = False
        self._preview_giro_refresh_timer = 0.0
        self._giro_preview_lista = []  # lista (task, dist, score) per rendering
        self._giro_preview_paths = []  # lista path A* pre-calcolati (uno per task del giro)

        # --- INTELLIGENCE: analisi sospettosita' player ---
        # Sistema MODULARE separato (vedi among_us_ai/intelligence/).
        # Si alimenta automaticamente dai detection YOLO esistenti.
        # Sidebar attivabile con F2 (vedi IntelligenceSidebarMixin).
        self._intelligence_enabled = bool(
            getattr(GPSConfig, 'INTELLIGENCE_ENABLED', True))
        if self._intelligence_enabled:
            from ..intelligence import (
                PlayerTracker, ActivityDetector,
                ProximityAnalyzer, TaskInference, SuspicionAnalyzer,
            )
            # Inizializzo i 5 moduli intelligence
            self._intelligence_tracker = PlayerTracker()
            # ActivityDetector senza posizioni vent: il rilevamento dei
            # vent uses funziona via teletrasporto fra osservazioni, senza
            # bisogno di sapere dove sono fisicamente le vent.
            self._intelligence_activity = ActivityDetector()
            self._intelligence_proximity = ProximityAnalyzer()
            # La task_list per inference dei task fatti dai player
            task_list_for_inf = []
            try:
                for t in self.task_mgr.dettagli.task_list:
                    task_list_for_inf.append({
                        'id': t.get('id'),
                        'nome': t.get('nome'),
                        'x': t.get('x'),
                        'y': t.get('y'),
                        'lunghezza': t.get('lunghezza', 'Short'),
                    })
            except Exception:
                pass
            self._intelligence_task_inf = TaskInference(task_list_for_inf)
            self._intelligence_suspicion = SuspicionAnalyzer()
            # Stato UI
            self._intelligence_sidebar_open = False
            self._intelligence_update_timer = 0.0

        # --- Punti di Interesse ---
        self.poi_mgr  = PoiManager(GPSConfig.POI_FILE)
        self.show_poi = True
        self.memory_tasks           = []
        self.task_launch_log        = []
        self._task_launch_nome      = ""
        self._task_launch_steps     = []
        self._task_launch_id        = None   # id task in corso di avvio
        self._task_prewarm_id       = None   # id task con pre-warming attivo
        self._task_launch_arrivo    = False  # True quando il player e' arrivato (fase 3)
        self._task_launch_timer_arr = 0.0    # timer fase 3
        self._task_process          = None   # subprocess.Popen del file .py in esecuzione
        self._task_process_task_id  = None   # id task associata al processo attivo
        self._pending_refresh_task_list = False
        
        # Cooldown per le task (Idea 3): { id_task: timestamp_ready }
        self.task_cooldowns         = {}
        self.task_internal_steps    = {} # Tiene traccia dei chunk (fasi) completate localmente

        # Counter tentativi di ripetizione per ciascuna task.
        # Struttura: { id_task: { idx_fase: numero_tentativi_fatti } }
        # Quando una fase con ripeti=True non riesce e va riprovata, il
        # contatore associato cresce di 1. Se raggiunge max_tentativi
        # (definito a livello fase nel JSON, default 5), interrompiamo
        # la ripetizione e premiamo ESC per uscire dal minigioco.
        # Il counter si azzera quando la fase passa (RAM avanza) o
        # quando si lancia una task da capo.
        self.task_retry_counts      = {}

        # Editor delle azioni (finestra DPG separata)
        self.action_editor          = TaskActionEditor(self.task_mgr)

        self.map_bounds = None
        self.running = True

        self.carica_mappa()
        self._calcola_bounds_mappa()
        self.pathfinder.rebuild(self.visitati_coords)

        # Crea un thread parallelo (per non bloccare l'UI)
        self.mem_thread = threading.Thread(target=self._leggi_memoria, daemon=True)
        self.mem_thread.start()
        
        # Avvio scanner YOLO in background
        self.yolo_scanner_thread = threading.Thread(target=self._yolo_scanner_loop, daemon=True)
        self.yolo_scanner_thread.start()

        atexit.register(self.key_ctrl.release_all)
        atexit.register(self._ferma_processo_task)
        self._setup_interfaccia()

    def aggiorna_frame(self):
        """Aggiorna lo stato e il rendering a ogni frame del loop principale."""
        dt = dpg.get_delta_time()
        if dt > 0.1: dt = 0.1

        # --- HOTKEY GLOBALE PER STOP TASK (F4 o END/FINE) ---
        if _WIN_OK:
            f4_pressed = (win32api.GetAsyncKeyState(0x73) & 0x8000) != 0
            end_pressed = (win32api.GetAsyncKeyState(0x23) & 0x8000) != 0
            if (f4_pressed or end_pressed) and not getattr(self, '_prev_stop_key', False):
                # Flag globale di stop (True quando F4 o FINE viene premuto)
                stop_flag.requested = True
                self._cancel_auto_move()
                self._ferma_processo_task()
                self._task_launch_arrivo = False
                try:
                    # Rilascia il tasto sinistro del mouse
                    pyautogui.mouseUp(button='left')
                except Exception:
                    pass
                # Verifica se l'elemento DPG e' gia' stato creato
                if dpg.does_item_exist("task_launch_popup"):
                    # Rimuove l'elemento DPG (cleanup)
                    dpg.delete_item("task_launch_popup")
                # Messaggio di stato mostrato all'utente nel pannello
                self.auto_status_msg = "[X] Esecuzione annullata (Stop)"
            self._prev_stop_key = (f4_pressed or end_pressed)

        self._update_trail_and_distance()
        self._update_auto_move(dt)
        self._update_task_launch(dt)
        self._controlla_processo_task()
        self._update_auto_all(dt)
        self._update_preview_giro(dt)
        self._update_intelligence_sidebar(dt)
        
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
                            # Messaggio di stato mostrato all'utente nel pannello
                            self.auto_status_msg = f"Navigo verso '{task_reg['nome']}' (Tappa {step_2p})"

        # Editor azioni (se aperto): aggiorna preview + gestisci Ctrl+Click
        if self.action_editor.e_aperto():
            self.action_editor.tick()

        # Aggiorna label stato processo accanto al pulsante Stop
        if dpg.does_item_exist("processo_status"):
            if self._task_process is not None and self._task_process.poll() is None:
                task_att = self.task_mgr.get_by_id(self._task_process_task_id)
                nome_att = task_att['nome'] if task_att else "?"
                # Cambia le configurazioni di un widget gia' creato
                dpg.configure_item("processo_status", color=(0, 220, 120, 255))
                # Aggiorna il valore di un widget DPG
                dpg.set_value("processo_status", f"> {nome_att}")
            else:
                # Cambia le configurazioni di un widget gia' creato
                dpg.configure_item("processo_status", color=(120, 120, 120, 200))
                # Aggiorna il valore di un widget DPG
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

    def run(self):
        """Avvia il loop principale dell'applicazione."""
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
