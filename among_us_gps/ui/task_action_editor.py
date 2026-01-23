"""
Editor di azioni per una singola task — finestra DearPyGui secondaria.

Permette all'utente di registrare visualmente la sequenza di click/drag/zone
che compongono l'esecuzione di una task. La dashboard principale continua a
funzionare in parallelo come finestra DPG separata.

Uso tipico::

    editor = TaskActionEditor(task_mgr)
    editor.apri(id_task, on_save=callback)

L'editor lavora in coordinate relative (0..1) sull'area client della finestra
target di Among Us, in modo da essere indipendente dalla risoluzione.
"""

import math
import threading
import time

import dearpygui.dearpygui as dpg

from ..core.config import MAX_PREVIEW_W, MAX_PREVIEW_H
from ..core.geometry import get_client_rect, point_in_polygon
from ..core import stop_flag
from ..core.win_deps import (
    WIN_OK as _WIN_OK,
    cv2,
    mss,
    np,
    pyautogui,
    win32api,
    win32con,
    win32gui,
)
from ..execution.runtime import esegui_azioni, _extract_pure_shape


class TaskActionEditor:
    """
    Editor di azioni per una singola task. Si apre come finestra DearPyGui
    secondaria. La dashboard principale continua a girare in background.

    Uso:
        editor = TaskActionEditor(task_mgr)
        editor.apri(id_task, on_save=callback)

    Il callback on_save riceve l'id della task ed è invocato dopo che
    l'utente preme "Salva e chiudi".
    """

    # Stati della macchina di interazione
    IDLE              = "IDLE"
    WAIT_CLICK        = "WAIT_CLICK"
    WAIT_DRAG_START   = "WAIT_DRAG_START"
    WAIT_DRAG_END     = "WAIT_DRAG_END"
    WAIT_MULTI        = "WAIT_MULTI"         
    WAIT_POLY         = "WAIT_POLY"          
    WAIT_POLY_ZONE_A      = "WAIT_POLY_ZONE_A"
    WAIT_POLY_ZONE_B      = "WAIT_POLY_ZONE_B"
    WAIT_DRAG_HOLD_START  = "WAIT_DRAG_HOLD_START"
    WAIT_DRAG_HOLD_END    = "WAIT_DRAG_HOLD_END"  
    WAIT_WIRING_L         = "WAIT_WIRING_L"
    WAIT_WIRING_R         = "WAIT_WIRING_R"
    WAIT_WIRING_C         = "WAIT_WIRING_C"
    WAIT_SYNC_CHECK       = "WAIT_SYNC_CHECK"
    WAIT_SYNC_BTN         = "WAIT_SYNC_BTN"
    WAIT_YOLO_POLY        = "WAIT_YOLO_POLY"
    WAIT_YOLO_DEST        = "WAIT_YOLO_DEST"
    WAIT_YOLO_ALL_POLY    = "WAIT_YOLO_ALL_POLY"
    WAIT_YOLO_ALL_DEST    = "WAIT_YOLO_ALL_DEST"
    WAIT_CUC_CHK          = "WAIT_CUC_CHK"
    WAIT_CUC_BTN          = "WAIT_CUC_BTN"
    WAIT_YOLO_CLICK_POLY  = "WAIT_YOLO_CLICK_POLY"
    WAIT_YOLO_CLICK_ALL_POLY = "WAIT_YOLO_CLICK_ALL_POLY"
    WAIT_YOLO_SEQ_POLY    = "WAIT_YOLO_SEQ_POLY"
    WAIT_SIMON_DISPLAY    = "WAIT_SIMON_DISPLAY"
    WAIT_SIMON_KEYPAD     = "WAIT_SIMON_KEYPAD"
    WAIT_ANOMALY_CHK      = "WAIT_ANOMALY_CHK"
    WAIT_ANOMALY_BTN      = "WAIT_ANOMALY_BTN"
    WAIT_NUM_MATCH_RECT   = "WAIT_NUM_MATCH_RECT"
    WAIT_OCR_POLY         = "WAIT_OCR_POLY"
    WAIT_OCR_KEYPAD       = "WAIT_OCR_KEYPAD"

    TAG_WIN           = "task_action_editor_window"
    TAG_CANVAS        = "tae_canvas"
    TAG_BG_TEX        = "tae_bg_texture"
    TAG_TEX_REG       = "tae_texture_registry"
    TAG_LIST          = "tae_list_azioni"
    TAG_IST           = "tae_testo_istruzioni"
    TAG_IN_WIN_NAME   = "tae_in_window_name"
    TAG_BTN_LIVE      = "tae_btn_live"
    TAG_IN_DUR        = "tae_in_duration"
    TAG_IN_PAUSE      = "tae_in_pause"
    TAG_PREVIEW_CONT  = "tae_preview_container"
    # Tag per il pannello di modifica tempi dell'azione selezionata
    TAG_EDIT_DUR      = "tae_edit_duration"
    TAG_EDIT_PAUSE    = "tae_edit_pause"
    TAG_EDIT_GROUP    = "tae_edit_group"
    TAG_IN_HOLD       = "tae_in_hold"
    TAG_EDIT_HOLD     = "tae_edit_hold"

    def __init__(self, task_mgr):
        self.task_mgr          = task_mgr
        self.id_task           = None
        self.on_save_cb        = None

        # Stato corrente
        self.stato             = self.IDLE
        self.azioni            = []          

        # Preview
        self.is_live           = False
        self.texture_width     = 0
        self.texture_height    = 0
        self.preview_w         = 500
        self.preview_h         = 500

        # Buffer per azioni multi-step
        self.buffer_punti      = []          
        self.buffer_zone_a     = []          
        self.buffer_w_l        = []
        self.buffer_w_r        = []
        self.buffer_w_c        = []
        self.buffer_sync       = []
        self.buffer_cuc        = []
        self.buffer_simon_d    = []
        self.buffer_simon_k    = []
        self.buffer_anomaly = []
        self.buffer_num_match  = []
        self.buffer_keypad     = []

        # Selezione
        self.sel_idx           = -1

        # Rettangolo disegnato col mouse
        self.rect_drag_active  = False
        self.rect_start        = None        
        self.rect_end          = None

        # Freeze
        self.frozen            = False
        self._prev_f_key       = False

        # Drag & drop vertici
        self._dragging_vertex       = False
        self._drag_vx_idx           = -1     
        self._drag_vx_key           = None   
        # Handler loop 
        self._aperto           = False

    # ======================= API PUBBLICA =======================

    def apri(self, id_task, on_save=None):
        task = self.task_mgr.get_by_id(id_task)
        if task is None:
            return False

        self.id_task    = id_task
        self.on_save_cb = on_save
        self.azioni     = list(task.get('azioni', [])) 
        self.stato      = self.IDLE
        self.buffer_punti  = []
        self.buffer_zone_a = []
        self.buffer_w_l    = []
        self.buffer_w_r    = []
        self.buffer_w_c    = []
        self.buffer_sync   = []
        self.buffer_cuc    = []
        self.buffer_simon_d = []
        self.buffer_simon_k = []
        self.buffer_anomaly = []
        self.buffer_num_match = []
        self.buffer_keypad = []
        self.sel_idx       = -1
        self.rect_drag_active = False
        self.frozen           = False
        self._dragging_vertex = False
        self._drag_vx_idx     = -1
        self._drag_vx_key     = None
        self.rect_start = None
        self.rect_end   = None

        self._build_ui(task)
        self._aperto = True
        self.aggiorna_lista()
        self.aggiorna_preview()
        return True

    def e_aperto(self):
        return self._aperto and dpg.does_item_exist(self.TAG_WIN)

    def tick(self):
        if not self.e_aperto():
            self._aperto = False
            return

        # Aggiorna il frame video
        self.aggiorna_frame()

        if not _WIN_OK:
            return

        # --- GESTIONE HOTKEY GLOBALE TASTO "F" ---
        # 0x46 è il Virtual-Key Code per il tasto F.
        # Controlliamo se è premuto e usiamo _prev_f_key per eseguire l'azione solo alla prima pressione (edge detection)
        f_key = (win32api.GetAsyncKeyState(0x46) & 0x8000) != 0
        if f_key and not self._prev_f_key:
            self._toggle_freeze()
        self._prev_f_key = f_key

        # Aggiorna solo il frame video. Non serve piu catturare i click globali.
        self.aggiorna_frame()

    def chiudi(self):
        self._aperto = False
        if dpg.does_item_exist(self.TAG_WIN):
            dpg.delete_item(self.TAG_WIN)

    # ======================= COSTRUZIONE UI =======================

