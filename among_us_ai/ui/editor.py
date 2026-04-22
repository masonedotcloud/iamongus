"""
Editor di azioni per una singola task - finestra DearPyGui secondaria.

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



from .editor_mixins.ui_build       import EditorUIMixin
from .editor_mixins.start_actions  import EditorStartActionsMixin
from .editor_mixins.sequence       import EditorSequenceMixin
from .editor_mixins.canvas_input   import EditorCanvasInputMixin
from .editor_mixins.drawing        import EditorDrawingMixin
from .editor_mixins.list_panel     import EditorListPanelMixin
from .editor_mixins.save_test      import EditorSaveTestMixin

class TaskActionEditor(
    # Tutti i mixin sono disgiunti (nessun metodo si sovrappone). L'ordine
    # qui non influisce sulla dispatch: tieni questo ordine per leggibilita'.
    EditorUIMixin,
    EditorStartActionsMixin,
    EditorSequenceMixin,
    EditorCanvasInputMixin,
    EditorDrawingMixin,
    EditorListPanelMixin,
    EditorSaveTestMixin,
):
    """Finestra di editing delle azioni di una task. Permette di registrare click, drag e altre azioni cliccando sulla preview del minigioco."""
    # =========================================================================
    # Costanti di classe (stati della macchina di interazione + tag DPG).
    # Erano definite cosi' anche nel file originale, prima dello split in
    # mixin: i mixin le accedono con ``self.IDLE``, ``self.TAG_CANVAS``, ecc.
    # =========================================================================

    # Stati della macchina di interazione
    IDLE                     = "IDLE"
    WAIT_CLICK               = "WAIT_CLICK"
    WAIT_DRAG_START          = "WAIT_DRAG_START"
    WAIT_DRAG_END            = "WAIT_DRAG_END"
    WAIT_MULTI               = "WAIT_MULTI"
    WAIT_POLY                = "WAIT_POLY"
    WAIT_POLY_ZONE_A         = "WAIT_POLY_ZONE_A"
    WAIT_POLY_ZONE_B         = "WAIT_POLY_ZONE_B"
    WAIT_DRAG_HOLD_START     = "WAIT_DRAG_HOLD_START"
    WAIT_DRAG_HOLD_END       = "WAIT_DRAG_HOLD_END"
    WAIT_WIRING_L            = "WAIT_WIRING_L"
    WAIT_WIRING_R            = "WAIT_WIRING_R"
    WAIT_WIRING_C            = "WAIT_WIRING_C"
    WAIT_SYNC_CHECK          = "WAIT_SYNC_CHECK"
    WAIT_SYNC_BTN            = "WAIT_SYNC_BTN"
    WAIT_YOLO_POLY           = "WAIT_YOLO_POLY"
    WAIT_YOLO_DEST           = "WAIT_YOLO_DEST"
    WAIT_YOLO_ALL_POLY       = "WAIT_YOLO_ALL_POLY"
    WAIT_YOLO_ALL_DEST       = "WAIT_YOLO_ALL_DEST"
    WAIT_CUC_CHK             = "WAIT_CUC_CHK"
    WAIT_CUC_BTN             = "WAIT_CUC_BTN"
    WAIT_YOLO_CLICK_POLY     = "WAIT_YOLO_CLICK_POLY"
    WAIT_YOLO_CLICK_ALL_POLY = "WAIT_YOLO_CLICK_ALL_POLY"
    WAIT_YOLO_SEQ_POLY       = "WAIT_YOLO_SEQ_POLY"
    WAIT_SIMON_DISPLAY       = "WAIT_SIMON_DISPLAY"
    WAIT_SIMON_KEYPAD        = "WAIT_SIMON_KEYPAD"
    WAIT_ANOMALY_CHK         = "WAIT_ANOMALY_CHK"
    WAIT_ANOMALY_BTN         = "WAIT_ANOMALY_BTN"
    WAIT_NUM_MATCH_RECT      = "WAIT_NUM_MATCH_RECT"
    WAIT_OCR_POLY            = "WAIT_OCR_POLY"
    WAIT_OCR_KEYPAD          = "WAIT_OCR_KEYPAD"

    # Tag DPG (identificatori dei widget)
    TAG_WIN          = "task_action_editor_window"
    TAG_CANVAS       = "tae_canvas"
    TAG_BG_TEX       = "tae_bg_texture"
    TAG_TEX_REG      = "tae_texture_registry"
    TAG_LIST         = "tae_list_azioni"
    TAG_IST          = "tae_testo_istruzioni"
    TAG_IN_WIN_NAME  = "tae_in_window_name"
    TAG_BTN_LIVE     = "tae_btn_live"
    TAG_IN_DUR       = "tae_in_duration"
    TAG_IN_PAUSE     = "tae_in_pause"
    TAG_PREVIEW_CONT = "tae_preview_container"
    # Tag per il pannello di modifica tempi dell'azione selezionata
    TAG_EDIT_DUR     = "tae_edit_duration"
    TAG_EDIT_PAUSE   = "tae_edit_pause"
    TAG_EDIT_GROUP   = "tae_edit_group"
    TAG_IN_HOLD      = "tae_in_hold"
    TAG_EDIT_HOLD    = "tae_edit_hold"

    def __init__(self, task_mgr):
        """Costruttore: inizializza lo stato a valori default."""
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

    def apri(self, id_task, on_save=None):
        """Apre la finestra dell'editor di azioni."""
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
        """Ritorna True se la finestra dell'editor e' aperta."""
        return self._aperto and dpg.does_item_exist(self.TAG_WIN)

    def tick(self):
        """Tick periodico dell'editor (chiamato a ogni frame)."""
        if not self.e_aperto():
            self._aperto = False
            return

        # Aggiorna il frame video
        self.aggiorna_frame()

        # Senza ambiente Windows non possiamo procedere
        if not _WIN_OK:
            return

        # --- GESTIONE HOTKEY GLOBALE TASTO "F" ---
        # 0x46 e' il Virtual-Key Code per il tasto F.
        # Controlliamo se e' premuto e usiamo _prev_f_key per eseguire l'azione solo alla prima pressione (edge detection)
        f_key = (win32api.GetAsyncKeyState(0x46) & 0x8000) != 0
        if f_key and not self._prev_f_key:
            self._toggle_freeze()
        self._prev_f_key = f_key

        # Aggiorna solo il frame video. Non serve piu catturare i click globali.
        self.aggiorna_frame()

    def chiudi(self):
        """Chiude la finestra dell'editor di azioni."""
        self._aperto = False
        if dpg.does_item_exist(self.TAG_WIN):
            dpg.delete_item(self.TAG_WIN)

    def aggiorna_frame(self, forza=False):
        """Aggiorna lo stato e il rendering a ogni frame del loop principale."""
        if not self.e_aperto():
            return
        # Senza ambiente Windows non possiamo procedere
        if not _WIN_OK:
            return
        if not self.is_live and not forza:
            return
        if self.frozen and not forza:
            return

        nome_finestra = dpg.get_value(self.TAG_IN_WIN_NAME)
        # Cerca la finestra del gioco per nome
        hwnd = win32gui.FindWindow(None, nome_finestra)
        if not hwnd:
            return
        # Ottiene il rect (x, y, w, h) dell'area client del gioco
        rect = get_client_rect(hwnd)
        if not rect or rect[2] <= 0 or rect[3] <= 0:
            return

        x, y, w, h = rect
        try:
            with mss.mss() as sct:
                monitor = {"top": y, "left": x, "width": w, "height": h}
                sct_img = np.array(sct.grab(monitor))
        except Exception:
            return
        rgba = cv2.cvtColor(sct_img, cv2.COLOR_BGRA2RGBA)
        texture_data = (rgba.astype(np.float32) / 255.0).ravel()

        if self.texture_width != w or self.texture_height != h:
            self.texture_width, self.texture_height = w, h
            if dpg.does_item_exist(self.TAG_BG_TEX):
                dpg.delete_item(self.TAG_BG_TEX)
            dpg.add_dynamic_texture(width=w, height=h, default_value=texture_data,
                                    tag=self.TAG_BG_TEX, parent=self.TAG_TEX_REG)
            
            self._ricalcola_dimensioni_preview()
            self.aggiorna_preview()
        else:
            if dpg.does_item_exist(self.TAG_BG_TEX):
                dpg.set_value(self.TAG_BG_TEX, texture_data)

    # Callback per l'evento
    def _on_resize(self, sender, app_data, user_data):
        """Callback del DPG su resize della finestra: ricalcola le dimensioni della preview."""
        if not self.e_aperto():
            return
        if self._ricalcola_dimensioni_preview():
            self.aggiorna_preview()

    def _imposta_istruzioni(self, testo, color=(150, 150, 150)):
        """Aggiorna il messaggio guida in alto nell'editor (colore + testo). No-op se il widget non esiste."""
        if dpg.does_item_exist(self.TAG_IST):
            dpg.set_value(self.TAG_IST, testo)
            # Cambia le configurazioni di un widget gia' creato
            dpg.configure_item(self.TAG_IST, color=color)
