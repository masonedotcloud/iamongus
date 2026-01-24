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

    def _build_ui(self, task):
        if dpg.does_item_exist(self.TAG_WIN):
            dpg.delete_item(self.TAG_WIN)

        if not dpg.does_item_exist(self.TAG_TEX_REG):
            with dpg.texture_registry(show=False, tag=self.TAG_TEX_REG):
                pass

        titolo = f"Editor Azioni - [{task['id']}] {task['nome']}"
        with dpg.window(label=titolo, tag=self.TAG_WIN,
                        width=1180, height=740,
                        on_close=lambda *a: self.chiudi()):
            # Colore unificato per gli header di sezione del pannello sinistro
            col_section = (255, 200, 0)
            with dpg.group(horizontal=True):
                # ----- Colonna sinistra: controlli -----
                with dpg.child_window(width=420, height=-1):

                    # ========== 1. FINESTRA BERSAGLIO ==========
                    dpg.add_text("1. FINESTRA BERSAGLIO", color=col_section)
                    dpg.add_separator()
                    dpg.add_input_text(label="Nome",
                                       default_value="Among Us",
                                       tag=self.TAG_IN_WIN_NAME)
                    with dpg.group(horizontal=True):
                        dpg.add_button(label="AVVIA Preview",
                                       tag=self.TAG_BTN_LIVE,
                                       callback=self._toggle_live,
                                       width=125, height=30)
                        dpg.add_button(label="Cattura Frame",
                                       callback=lambda *a: self.aggiorna_frame(True),
                                       width=125, height=30)
                        dpg.add_button(label="Freeze [F]",
                                       tag="tae_btn_freeze",
                                       callback=self._toggle_freeze,
                                       width=125, height=30)
                    dpg.add_text("Preview: LIVE", tag="tae_label_freeze",
                                 color=(150, 200, 255))

                    # ========== 2. TEMPI DEFAULT (NUOVE AZIONI) ==========
                    dpg.add_spacer(height=6)
                    dpg.add_text("2. TEMPI DEFAULT PER NUOVE AZIONI",
                                 color=col_section)
                    dpg.add_separator()
                    dpg.add_text("Questi valori vengono applicati alle nuove azioni "
                                 "che aggiungi sotto. Per modificare i tempi di "
                                 "un'azione GIA' presente, usa la sezione 4.",
                                 color=(150, 150, 150), wrap=380)
                    with dpg.group(horizontal=True):
                        dpg.add_input_float(label="Durata (s)",
                                            tag=self.TAG_IN_DUR,
                                            default_value=0.2, step=0.05,
                                            format="%.2f", width=120,
                                            min_value=0.0, min_clamped=True)
                        dpg.add_input_float(label="Pausa (s)",
                                            tag=self.TAG_IN_PAUSE,
                                            default_value=0.5, step=0.05,
                                            format="%.2f", width=120,
                                            min_value=0.0, min_clamped=True)
                    dpg.add_input_float(
                        label="Mantieni @ B (s)  [solo DRAG+TIENI]",
                        tag=self.TAG_IN_HOLD,
                        default_value=1.0, step=0.1,
                        format="%.2f", width=220,
                        min_value=0.0, min_clamped=True)

                    # ========== 3. AGGIUNGI AZIONE ==========
                    dpg.add_spacer(height=6)
                    dpg.add_text("3. AGGIUNGI AZIONE", color=col_section)
                    dpg.add_separator()
                    dpg.add_text("In attesa...", tag=self.TAG_IST,
                                 color=(150, 150, 150), wrap=380)

                    dpg.add_text("Punto singolo / drag:", color=(180, 255, 180))
                    with dpg.group(horizontal=True):
                        dpg.add_button(label="+ CLICK",
                                       callback=lambda *a: self._avvia(self.WAIT_CLICK,
                                           "CLICK sulla preview per piazzare il punto.",
                                           (0, 255, 0)),
                                       width=125, height=35)
                        dpg.add_button(label="+ DRAG",
                                       callback=lambda *a: self._avvia(self.WAIT_DRAG_START,
                                           "PARTENZA drag: CLICK sulla preview.",
                                           (255, 200, 0)),
                                       width=125, height=35)
                        dpg.add_button(label="+ MULTI-DRAG",
                                       callback=self._avvia_multi,
                                       width=125, height=35)

                    dpg.add_text("Drag con pressione finale al punto B:",
                                 color=(255, 140, 180))
                    with dpg.group(horizontal=True):
                        dpg.add_button(label="+ DRAG + TIENI",
                                       callback=self._avvia_drag_hold,
                                       width=190, height=35)
                        dpg.add_text(
                            "Trascina A->B,\nmantieni premuto su B\nper 'Mantieni (s)'",
                            color=(180, 180, 180))

                    dpg.add_text("Zone (click casuale nell'area):",
                                 color=(200, 180, 255))
                    with dpg.group(horizontal=True):
                        dpg.add_button(label="+ CLICK RETT",
                                       callback=self._avvia_rect_click,
                                       width=125, height=35)
                        dpg.add_button(label="+ CLICK POLY",
                                       callback=lambda *a: self._avvia_poly_click(),
                                       width=125, height=35)
                        dpg.add_button(label="+ DRAG A->B",
                                       callback=self._avvia_drag_zone,
                                       width=125, height=35)
                                       
                    dpg.add_text("Azioni speciali collegate alla vista:",
                                 color=(255, 255, 100))
                    with dpg.group(horizontal=True):
                        dpg.add_button(label="+ FIX WIRING",
                                       callback=self._avvia_wiring,
                                       width=125, height=35)
                        dpg.add_text("Risove i cavi usando i\ncolori dello schermo.",
                                     color=(180, 180, 180))
                    with dpg.group(horizontal=True):
                        dpg.add_button(label="+ SYNC CLICK",
                                       callback=self._avvia_sync_click,
                                       width=125, height=35)
                        dpg.add_text("Attende colore (non\nnero) e clicca bottone.",
                                     color=(180, 180, 180))
                    with dpg.group(horizontal=True):
                        dpg.add_button(label="+ CLICK ANOMALIA",
                                       callback=self._avvia_anomaly_click,
                                       width=125, height=35)
                        dpg.add_text("Seleziona >=3 punti, clicca\nquello col colore diverso.",
                                     color=(180, 180, 180))
                    with dpg.group(horizontal=True):
                        dpg.add_button(label="+ DRAG YOLO",
                                       callback=self._avvia_yolo_drag,
                                       width=125, height=35)
                        dpg.add_text("Usa YOLOv8 per rilevare\nl'oggetto e trascinarlo.",
                                     color=(180, 180, 180))
                    with dpg.group(horizontal=True):
                        dpg.add_button(label="+ COOLDOWN / FASE",
                                       callback=self._avvia_cooldown,
                                       width=125, height=35)
                        dpg.add_text("Divide in FASI e mette il\nbot in attesa per X secondi.",
                                     color=(180, 180, 180))

                    with dpg.group(horizontal=True):
                        dpg.add_button(label="+ CLICK YOLO",
                                       callback=self._avvia_yolo_click,
                                       width=125, height=35)
                        dpg.add_text("Usa YOLOv8 per rilevare\nl'oggetto e cliccarlo.",
                                     color=(180, 180, 180))

                    with dpg.group(horizontal=True):
                        dpg.add_button(label="+ CLICK ALL YOLO",
                                       callback=self._avvia_yolo_click_all,
                                       width=125, height=35)
                        dpg.add_text("Clicca TUTTI gli oggetti\nrilevati finché non finiscono.",
                                     color=(180, 180, 180))

                    with dpg.group(horizontal=True):
                        dpg.add_button(label="+ DRAG ALL YOLO",
                                       callback=self._avvia_yolo_drag_all,
                                       width=125, height=35)
                        dpg.add_text("Trascina TUTTI gli oggetti\nrilevati finché non finiscono.",
                                     color=(180, 180, 180))

                    with dpg.group(horizontal=True):
                        dpg.add_button(label="+ DRAG SEQ YOLO",
                                       callback=self._avvia_yolo_drag_seq,
                                       width=125, height=35)
                        dpg.add_text("Trascina l'oggetto unico\nsugli altri in sequenza.",
                                     color=(180, 180, 180))

                    with dpg.group(horizontal=True):
                        dpg.add_button(label="+ CLICK UNTIL",
                                       callback=self._avvia_click_until,
                                       width=125, height=35)
                        dpg.add_text("Clicca un bottone finché il\ncheck non è bianco.",
                                     color=(180, 180, 180))
                    with dpg.group(horizontal=True):
                        dpg.add_button(label="+ SIMON SAYS",
                                       callback=self._avvia_simon_says,
                                       width=125, height=35)
                        dpg.add_text("Memo reattore: mappa i punti\nluminosi e il tastierino.",
                                     color=(180, 180, 180))

                    with dpg.group(horizontal=True):
                        dpg.add_button(label="+ NUMBER MATCH",
                                       callback=self._avvia_num_match,
                                       width=125, height=35)
                        dpg.add_text("Trascina i rect dei numeri in\nordine (es: 1 a 10). Poi CHIUDI.", color=(180, 180, 180))

                    with dpg.group(horizontal=True):
                        dpg.add_button(label="+ OCR KEYPAD",
                                       callback=self._avvia_ocr_keypad,
                                       width=125, height=35)
                        dpg.add_text("Legge numeri (EasyOCR)\ne preme tastierino 0-9.", color=(180, 180, 180))

                    with dpg.group(horizontal=True):
                        dpg.add_button(label="CHIUDI PUNTI (Invio)",
                                       callback=self._chiudi_sequenza,
                                       width=190, height=28)
                        dpg.add_button(label="ANNULLA (Esc)",
                                       callback=self._annulla,
                                       width=190, height=28)

                    # ========== 4. AZIONE SELEZIONATA ==========
                    dpg.add_spacer(height=6)
                    dpg.add_text("4. AZIONE SELEZIONATA", color=col_section)
                    dpg.add_separator()
                    dpg.add_text("Clicca su un punto/poligono nella preview per "
                                 "selezionare l'azione relativa.",
                                 color=(150, 150, 150), wrap=380)
                    dpg.add_text("— nessuna azione selezionata —",
                                 tag="tae_sel_info", color=(150, 150, 150), wrap=380)

                    # --- Modifica tempi dell'azione selezionata (in-place) ---
                    # Prima si poteva cambiare la durata/attesa solo cancellando
                    # e ridisegnando l'azione. Ora c'è una coppia di input
                    # dedicata che scrive direttamente in self.azioni[sel_idx].
                    with dpg.group(tag=self.TAG_EDIT_GROUP, show=False):
                        dpg.add_text("Modifica tempi (senza ridisegnare la geometria):",
                                     color=(150, 200, 255))
                        with dpg.group(horizontal=True):
                            dpg.add_text("Durata:")
                            dpg.add_input_float(tag=self.TAG_EDIT_DUR,
                                                default_value=0.2, step=0.05,
                                                format="%.2f", width=90,
                                                min_value=0.0, min_clamped=True)
                            dpg.add_text("s    Pausa:")
                            dpg.add_input_float(tag=self.TAG_EDIT_PAUSE,
                                                default_value=0.5, step=0.05,
                                                format="%.2f", width=90,
                                                min_value=0.0, min_clamped=True)
                            dpg.add_text("s")
                        dpg.add_input_float(
                                            tag=self.TAG_EDIT_HOLD,
                                            label="Mantieni @ B (s)  [solo DRAG+TIENI]",
                                            default_value=1.0, step=0.1,
                                            format="%.2f", width=90,
                                            min_value=0.0, min_clamped=True)
                        dpg.add_button(label="Applica tempi all'azione selezionata",
                                       callback=self._applica_tempi_selezione,
                                       width=-1, height=26)

                    dpg.add_spacer(height=2)
                    with dpg.group(horizontal=True):
                        dpg.add_button(label="Ridisegna geometria",
                                       callback=self._modifica_selezione,
                                       width=190, height=28)
                        dpg.add_button(label="Elimina (Canc)",
                                       callback=self._elimina_selezione,
                                       width=190, height=28)

                    # ========== 5. LISTA AZIONI / TEST / SALVA ==========
                    dpg.add_spacer(height=6)
                    dpg.add_text("5. LISTA AZIONI REGISTRATE", color=col_section)
                    dpg.add_separator()
                    with dpg.child_window(tag=self.TAG_LIST, height=180):
                        pass

                    dpg.add_spacer(height=4)
                    dpg.add_button(label="TEST SEQUENZA (esegue tutte le azioni)",
                                   callback=self._avvia_test,
                                   width=-1, height=36)
                    dpg.add_spacer(height=4)
                    with dpg.group(horizontal=True):
                        dpg.add_button(label="SALVA e CHIUDI",
                                       callback=self._salva_e_chiudi,
                                       width=200, height=38)
                        dpg.add_button(label="Annulla",
                                       callback=lambda *a: self.chiudi(),
                                       width=180, height=38)

                # ----- Colonna destra: preview -----
                with dpg.child_window(tag=self.TAG_PREVIEW_CONT, width=-1, height=-1, border=False):
                    with dpg.drawlist(width=self.preview_w, height=self.preview_h,
                                      tag=self.TAG_CANVAS):
                        pass

        if not dpg.does_item_exist("tae_canvas_handler"):
            with dpg.item_handler_registry(tag="tae_canvas_handler"):
                dpg.add_item_clicked_handler(button=0, callback=self._canvas_mouse_down)
        dpg.bind_item_handler_registry(self.TAG_CANVAS, "tae_canvas_handler")

        if not dpg.does_item_exist("tae_key_handler"):
            with dpg.handler_registry(tag="tae_key_handler"):
                dpg.add_key_press_handler(key=dpg.mvKey_Delete, callback=self._on_key_delete)
                dpg.add_key_press_handler(key=dpg.mvKey_F, callback=self._on_key_freeze)

        # Handler per ridimensionamento
        if not dpg.does_item_exist("tae_win_resize_handler"):
            with dpg.item_handler_registry(tag="tae_win_resize_handler"):
                dpg.add_item_resize_handler(callback=self._on_resize)
        dpg.bind_item_handler_registry(self.TAG_WIN, "tae_win_resize_handler")

    # ======================= DIMENSIONAMENTO PREVIEW =======================

    def _ricalcola_dimensioni_preview(self):
        if not dpg.does_item_exist(self.TAG_PREVIEW_CONT) or self.texture_width <= 0:
            return False
            
        avail_w, avail_h = dpg.get_item_rect_size(self.TAG_PREVIEW_CONT)
        if avail_w <= 0: avail_w = MAX_PREVIEW_W
        if avail_h <= 0: avail_h = MAX_PREVIEW_H
        
        aspect = self.texture_width / self.texture_height
        temp_w = avail_w
        temp_h = int(temp_w / aspect)
        
        if temp_h > avail_h:
            temp_h = avail_h
            temp_w = int(temp_h * aspect)

        if temp_w != self.preview_w or temp_h != self.preview_h:
            self.preview_w, self.preview_h = int(temp_w), int(temp_h)
            dpg.set_item_width(self.TAG_CANVAS, self.preview_w)
            dpg.set_item_height(self.TAG_CANVAS, self.preview_h)
            return True
        return False

    def _on_resize(self, sender, app_data, user_data):
        if not self.e_aperto():
            return
        if self._ricalcola_dimensioni_preview():
            self.aggiorna_preview()

    # ======================= INTERAZIONE UI =======================

    def _toggle_live(self, *_):
        self.is_live = not self.is_live
        dpg.set_item_label(self.TAG_BTN_LIVE,
                           "FERMA Live Preview" if self.is_live else "AVVIA Live Preview")

    def _toggle_freeze(self, *_):
        self.frozen = not self.frozen
        if dpg.does_item_exist("tae_label_freeze"):
            if self.frozen:
                dpg.set_value("tae_label_freeze", "Preview: FROZEN")
                dpg.configure_item("tae_label_freeze", color=(100, 200, 255))
            else:
                dpg.set_value("tae_label_freeze", "Preview: LIVE")
                dpg.configure_item("tae_label_freeze", color=(150, 200, 255))
        if dpg.does_item_exist("tae_btn_freeze"):
            dpg.set_item_label("tae_btn_freeze",
                               "Sblocca [F]" if self.frozen else "Freeze [F]")
        self.aggiorna_preview()

    def _on_key_freeze(self, *_):
        if self.e_aperto():
            self._toggle_freeze()

    def _imposta_istruzioni(self, testo, color=(150, 150, 150)):
        if dpg.does_item_exist(self.TAG_IST):
            dpg.set_value(self.TAG_IST, testo)
            dpg.configure_item(self.TAG_IST, color=color)

    def _avvia(self, nuovo_stato, msg, color):
        self.stato = nuovo_stato
        self.buffer_punti = []
        self._imposta_istruzioni(msg, color)

    def _avvia_multi(self, *_):
        self.buffer_punti = []
        self.stato = self.WAIT_MULTI
        self._imposta_istruzioni(
            "MULTI-DRAG: CLICK sulla preview per ogni punto (>=2). Poi 'CHIUDI PUNTI'.",
            (255, 180, 100))

    def _avvia_poly_click(self, *_):
        self.buffer_punti = []
        self.stato = self.WAIT_POLY
        self._imposta_istruzioni(
            "POLIGONO: CLICK sulla preview per ogni vertice (>=3). Poi 'CHIUDI PUNTI'.",
            (200, 180, 255))

    def _avvia_drag_zone(self, *_):
        self.buffer_punti  = []
        self.buffer_zone_a = []
        self.stato = self.WAIT_POLY_ZONE_A
        self._imposta_istruzioni(
            "DRAG ZONA: disegna ZONA A (click vertici, >=3). Poi 'CHIUDI PUNTI'.",
            (255, 150, 200))

    def _avvia_wiring(self, *_):
        self.stato = self.WAIT_WIRING_L
        self.buffer_w_l, self.buffer_w_r, self.buffer_w_c = [], [], []
        self._imposta_istruzioni("WIRING: Clicca sulla punta dei 4 CAVI DI SINISTRA (1/4)",
                                 (200, 255, 100))

    def _avvia_sync_click(self, *_):
        self.stato = self.WAIT_SYNC_CHECK
        self.buffer_sync = []
        self._imposta_istruzioni("SYNC CLICK: Clicca PUNTO DA CONTROLLARE (luce/led).", (255, 255, 100))

    def _avvia_yolo_drag(self, *_):
        def on_name(nome):
            if nome:
                self._tmp_yolo_model = nome
                self.stato = self.WAIT_YOLO_POLY
                self.buffer_punti = []
                self.buffer_zone_a = []
                self._imposta_istruzioni(f"DRAG YOLO '{nome}': Disegna la ZONA DI RICERCA (poly, >=3). Poi 'CHIUDI PUNTI'.", (255, 100, 255))
            else:
                self._imposta_istruzioni("Aggiunta azione annullata.", (255, 100, 100))
        self._show_text_input("Inserisci il nome del modello YOLO (es. arrow.pt)", "best.pt", on_name)

    def _avvia_yolo_drag_all(self, *_):
        def on_name(nome):
            if nome:
                self._tmp_yolo_model = nome
                self.stato = self.WAIT_YOLO_ALL_POLY
                self.buffer_punti = []
                self.buffer_zone_a = []
                self._imposta_istruzioni(f"DRAG ALL YOLO '{nome}': Disegna la ZONA (poly, >=3). Poi 'CHIUDI PUNTI'.", (255, 120, 100))
            else:
                self._imposta_istruzioni("Aggiunta azione annullata.", (255, 100, 100))
        self._show_text_input("Inserisci il nome del modello YOLO (es. foglie.pt)", "best.pt", on_name)

    def _avvia_click_until(self, *_):
        self.stato = self.WAIT_CUC_CHK
        self.buffer_cuc = []
        self._imposta_istruzioni("CLICK UNTIL: Clicca PUNTO DA CONTROLLARE (diventerà bianco).", (255, 255, 255))

    def _avvia_simon_says(self, *_):
        self.stato = self.WAIT_SIMON_DISPLAY
        self.buffer_simon_d = []
        self.buffer_simon_k = []
        self._imposta_istruzioni("SIMON SAYS: Clicca le posizioni delle LUCI/SCHERMO (minimo 1). Poi CHIUDI PUNTI.", (100, 200, 255))

    def _avvia_anomaly_click(self, *_):
        self.stato = self.WAIT_ANOMALY_CHK
        self.buffer_anomaly = []
        self._imposta_istruzioni("CLICK ANOMALIA: Clicca PUNTO DA CONTROLLARE (colore).",
                                 (255, 100, 200))
                                 
    def _avvia_num_match(self, *_):
        self.stato = self.WAIT_NUM_MATCH_RECT
        self.buffer_num_match = []
        self.rect_drag_active = False
        self.rect_start = None
        self.rect_end = None
        self._imposta_istruzioni("NUMBER MATCH: Trascina rect per il numero 1.", (100, 255, 255))

    def _avvia_ocr_keypad(self, *_):
        self.stato = self.WAIT_OCR_POLY
        self.buffer_punti = []
        self.buffer_keypad = []
        self._imposta_istruzioni("OCR KEYPAD: Disegna ZONA DISPLAY (poly, >=3). Poi 'CHIUDI PUNTI'.", (100, 255, 200))

    def _avvia_yolo_click(self, *_):
        def on_name(nome):
            if nome:
                self._tmp_yolo_model = nome
                self.stato = self.WAIT_YOLO_CLICK_POLY
                self.buffer_punti = []
                self.buffer_zone_a = []
                self._imposta_istruzioni(f"CLICK YOLO '{nome}': Disegna la ZONA DI RICERCA (poly, >=3). Poi 'CHIUDI PUNTI'.", (100, 255, 100))
            else:
                self._imposta_istruzioni("Aggiunta azione annullata.", (255, 100, 100))
        self._show_text_input("Inserisci il nome del modello YOLO (es. asteroidi.pt)", "best.pt", on_name)

    def _avvia_yolo_click_all(self, *_):
        def on_name(nome):
            if nome:
                self._tmp_yolo_model = nome
                self.stato = self.WAIT_YOLO_CLICK_ALL_POLY
                self.buffer_punti = []
                self.buffer_zone_a = []
                self._imposta_istruzioni(f"CLICK ALL YOLO '{nome}': Disegna la ZONA DI RICERCA (poly, >=3). Poi 'CHIUDI PUNTI'.", (100, 255, 150))
            else:
                self._imposta_istruzioni("Aggiunta azione annullata.", (255, 100, 100))
        self._show_text_input("Inserisci il nome del modello YOLO (es. asteroidi.pt)", "best.pt", on_name)

    def _avvia_yolo_drag_seq(self, *_):
        def on_name(nome):
            if nome:
                self._tmp_yolo_model = nome
                self.stato = self.WAIT_YOLO_SEQ_POLY
                self.buffer_punti = []
                self._imposta_istruzioni(f"DRAG SEQ YOLO '{nome}': Disegna la ZONA DI RICERCA (poly, >=3). Poi 'CHIUDI PUNTI'.", (255, 120, 200))
            else:
                self._imposta_istruzioni("Aggiunta azione annullata.", (255, 100, 100))
        self._show_text_input("Nome modello YOLO (es. seq.pt)", "best.pt", on_name)

    def _avvia_cooldown(self, *_):
        durata = dpg.get_value(self.TAG_IN_DUR)
        self.azioni.append({
            "tipo": "cooldown",
            "durata": durata
        })
        self._imposta_istruzioni(f"Cooldown (cambio fase) aggiunto: {durata}s.", (100, 255, 100))
        self.aggiorna_lista()
        self.aggiorna_preview()

    def _show_text_input(self, title, default_text, callback):
        """Mostra un popup modale per inserimento testo nell'editor."""
        tag = "tae_text_input_popup"
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
                        no_collapse=True, width=340, height=135,
                        pos=(max(0, vp_w // 2 - 170), max(0, vp_h // 2 - 68))):
            dpg.add_input_text(tag=f"{tag}_input", default_value=default_text or "", width=-1, on_enter=True, callback=do_ok)
            dpg.add_spacer(height=4)
            with dpg.group(horizontal=True):
                dpg.add_button(label="OK", width=155, callback=do_ok)
                dpg.add_button(label="Annulla", width=155, callback=do_cancel)
        try:
            dpg.focus_item(f"{tag}_input")
        except Exception:
            pass

    def _avvia_drag_hold(self, *_):
        """Avvia registrazione drag_hold: due click (A, poi B)."""
        self.buffer_punti = []
        self.stato = self.WAIT_DRAG_HOLD_START
        self._imposta_istruzioni(
            "DRAG+TIENI: CLICK sulla preview per PARTENZA (punto A).",
            (255, 140, 180))

    def _avvia_rect_click(self, *_):
        self.stato = "WAIT_RECT_ON_CANVAS"
        self.rect_drag_active = False
        self.rect_start = None
        self.rect_end   = None
        self._imposta_istruzioni(
            "CLICK RETT: trascina sulla PREVIEW per disegnare il rettangolo.",
            (180, 255, 180))

    def _chiudi_sequenza(self, *_):
        durata = dpg.get_value(self.TAG_IN_DUR)
        attesa = dpg.get_value(self.TAG_IN_PAUSE)

        if self.stato == self.WAIT_MULTI:
            if len(self.buffer_punti) >= 2:
                self.azioni.append({
                    "tipo":   "drag_multi",
                    "punti":  [list(p) for p in self.buffer_punti],
                    "durata": durata,
                    "attesa": attesa,
                })
                self._imposta_istruzioni(
                    f"Multi-drag aggiunto ({len(self.buffer_punti)} punti).")
            else:
                self._imposta_istruzioni("Servono almeno 2 punti.", (255, 100, 100))
            self._reset_stato()

        elif self.stato == self.WAIT_POLY:
            if len(self.buffer_punti) >= 3:
                self.azioni.append({
                    "tipo":   "click_poly",
                    "poly":   [list(p) for p in self.buffer_punti],
                    "durata": durata,
                    "attesa": attesa,
                })
                self._imposta_istruzioni(
                    f"Click poligono aggiunto ({len(self.buffer_punti)} vertici).")
            else:
                self._imposta_istruzioni("Servono almeno 3 vertici.", (255, 100, 100))
            self._reset_stato()

        elif self.stato == self.WAIT_POLY_ZONE_A:
            if len(self.buffer_punti) >= 3:
                self.buffer_zone_a = list(self.buffer_punti)
                self.buffer_punti = []
                self.stato = self.WAIT_POLY_ZONE_B
                self._imposta_istruzioni(
                    f"ZONA A ok ({len(self.buffer_zone_a)} vertici). Ora disegna ZONA B.",
                    (255, 200, 100))
            else:
                self._imposta_istruzioni("Zona A: servono almeno 3 vertici.",
                                         (255, 100, 100))

        elif self.stato == self.WAIT_POLY_ZONE_B:
            if len(self.buffer_punti) >= 3:
                self.azioni.append({
                    "tipo":    "drag_zone",
                    "zone_a":  [list(p) for p in self.buffer_zone_a],
                    "zone_b":  [list(p) for p in self.buffer_punti],
                    "durata":  durata,
                    "attesa":  attesa,
                })
                self._imposta_istruzioni("Drag zona->zona aggiunto.")
            else:
                self._imposta_istruzioni("Zona B: servono almeno 3 vertici.",
                                         (255, 100, 100))
            self._reset_stato()
        elif self.stato in (self.WAIT_SYNC_CHECK, self.WAIT_SYNC_BTN):
            if len(self.buffer_sync) > 0:
                self.azioni.append({
                    "tipo": "sync_click",
                    "punti": self.buffer_sync,
                    "durata": durata,
                    "attesa": attesa
                })
                self._imposta_istruzioni(f"Sync Click aggiunto ({len(self.buffer_sync)} coppie).")
            else:
                self._imposta_istruzioni("Nessuna coppia aggiunta.", (255, 100, 100))
            self._reset_stato()

        elif self.stato == self.WAIT_YOLO_POLY:
            if len(self.buffer_punti) >= 3:
                self.buffer_zone_a = list(self.buffer_punti)
                self.buffer_punti = []
                self.stato = self.WAIT_YOLO_DEST
                self._imposta_istruzioni(f"ROI registrata ({len(self.buffer_zone_a)} vertici). Ora clicca la DESTINAZIONE sulla preview.", (255, 200, 100))
            else:
                self._imposta_istruzioni("Servono almeno 3 vertici per la ROI.", (255, 100, 100))

        elif self.stato == self.WAIT_YOLO_ALL_POLY:
            if len(self.buffer_punti) >= 3:
                self.buffer_zone_a = list(self.buffer_punti)
                self.buffer_punti = []
                self.stato = self.WAIT_YOLO_ALL_DEST
                self._imposta_istruzioni(f"ROI registrata ({len(self.buffer_zone_a)} vertici). Ora clicca la DESTINAZIONE sulla preview.", (255, 180, 100))
            else:
                self._imposta_istruzioni("Servono almeno 3 vertici per la ROI.", (255, 100, 100))

        elif self.stato == self.WAIT_YOLO_CLICK_POLY:
            if len(self.buffer_punti) >= 3:
                self.azioni.append({
                    "tipo": "yolo_click",
                    "yolo_model": getattr(self, '_tmp_yolo_model', 'best.pt'),
                    "roi_poly": [list(p) for p in self.buffer_punti],
                    "durata": durata, "attesa": attesa
                })
                self._reset_stato()
                self._imposta_istruzioni(f"Click YOLO aggiunto.", (100, 255, 100))
            else:
                self._imposta_istruzioni("Servono almeno 3 vertici per la ROI.", (255, 100, 100))

        elif self.stato == self.WAIT_YOLO_CLICK_ALL_POLY:
            if len(self.buffer_punti) >= 3:
                self.azioni.append({
                    "tipo": "yolo_click_all",
                    "yolo_model": getattr(self, '_tmp_yolo_model', 'best.pt'),
                    "roi_poly": [list(p) for p in self.buffer_punti],
                    "durata": durata, "attesa": attesa
                })
                self._reset_stato()
                self._imposta_istruzioni(f"Click ALL YOLO aggiunto.", (100, 255, 100))
            else:
                self._imposta_istruzioni("Servono almeno 3 vertici per la ROI.", (255, 100, 100))

        elif self.stato == self.WAIT_YOLO_SEQ_POLY:
            if len(self.buffer_punti) >= 3:
                self.azioni.append({
                    "tipo": "yolo_drag_seq",
                    "yolo_model": getattr(self, '_tmp_yolo_model', 'best.pt'),
                    "roi_poly": [list(p) for p in self.buffer_punti],
                    "durata": durata, "attesa": attesa
                })
                self._reset_stato()
                self._imposta_istruzioni(f"Drag Sequenziale YOLO aggiunto.", (100, 255, 100))
            else:
                self._imposta_istruzioni("Servono almeno 3 vertici per la ROI.", (255, 100, 100))

        elif self.stato in (self.WAIT_CUC_CHK, self.WAIT_CUC_BTN):
            if len(self.buffer_cuc) > 0:
                self.azioni.append({
                    "tipo": "click_until",
                    "punti": self.buffer_cuc,
                    "durata": durata,
                    "attesa": attesa
                })
                self._imposta_istruzioni(f"Click Until aggiunto ({len(self.buffer_cuc)} coppie).")
            else:
                self._imposta_istruzioni("Nessuna coppia aggiunta.", (255, 100, 100))
            self._reset_stato()

        elif self.stato == self.WAIT_SIMON_DISPLAY:
            if len(self.buffer_simon_d) > 0:
                self.stato = self.WAIT_SIMON_KEYPAD
                self._imposta_istruzioni(f"Display ok ({len(self.buffer_simon_d)} luci). Ora clicca ESATTAMENTE {len(self.buffer_simon_d)} BOTTONI corrispondenti. Poi CHIUDI PUNTI.", (255, 100, 255))
            else:
                self._imposta_istruzioni("Servono punti per il display.", (255, 100, 100))
                
        elif self.stato == self.WAIT_SIMON_KEYPAD:
            if len(self.buffer_simon_k) == len(self.buffer_simon_d):
                self.azioni.append({"tipo": "simon_says", "display": [list(p) for p in self.buffer_simon_d], "keypad": [list(p) for p in self.buffer_simon_k], "durata": durata, "attesa": attesa})
                self._reset_stato()
                self._imposta_istruzioni("Simon Says registrato correttamente!", (100, 255, 100))
            else:
                self._imposta_istruzioni(f"Errore: hai cliccato {len(self.buffer_simon_k)} bottoni ma le luci sono {len(self.buffer_simon_d)}.", (255, 100, 100))

        elif self.stato in (self.WAIT_ANOMALY_CHK, self.WAIT_ANOMALY_BTN):
            if len(self.buffer_anomaly) >= 3:
                self.azioni.append({
                    "tipo": "click_anomaly",
                    "punti": self.buffer_anomaly,
                    "durata": durata, "attesa": attesa
                })
                self._reset_stato()
                self._imposta_istruzioni(f"Click Anomalia aggiunto ({len(self.buffer_anomaly)} coppie da valutare).", (100, 255, 100))
            else:
                self._imposta_istruzioni("Servono almeno 3 coppie per fare un confronto.", (255, 100, 100))
                
        elif self.stato == self.WAIT_NUM_MATCH_RECT:
            if len(self.buffer_num_match) > 0:
                self.azioni.append({
                    "tipo": "number_match",
                    "buttons": self.buffer_num_match,
                    "durata": durata,
                    "attesa": attesa
                })
                self._imposta_istruzioni(f"Number Match aggiunto ({len(self.buffer_num_match)} numeri in ordine).", (100, 255, 255))
            else:
                self._imposta_istruzioni("Nessun numero registrato.", (255, 100, 100))
            self._reset_stato()

        elif self.stato == self.WAIT_OCR_POLY:
            if len(self.buffer_punti) >= 3:
                self.buffer_zone_a = list(self.buffer_punti)
                self.buffer_punti = []
                self.stato = self.WAIT_OCR_KEYPAD
                self._imposta_istruzioni("Zona OK. Ora clicca 10 TASTI in ordine da 0 a 9.", (255, 100, 255))
            else:
                self._imposta_istruzioni("Servono almeno 3 vertici per la zona display.", (255, 100, 100))

        else:
            self._imposta_istruzioni("Nessuna sequenza attiva.", (150, 150, 150))

        self.aggiorna_lista()
        self.aggiorna_preview()

    def _annulla(self, *_):
        self._reset_stato()
        self._imposta_istruzioni("Annullato.", (150, 150, 150))

    def _reset_stato(self):
        self.stato = self.IDLE
        self.buffer_punti = []
        self.buffer_zone_a = []
        self.buffer_w_l = []
        self.buffer_w_r = []
        self.buffer_w_c = []
        self.buffer_sync = []
        self.buffer_cuc = []
        self.buffer_simon_d = []
        self.buffer_simon_k = []
        self.buffer_anomaly = []
        self.buffer_num_match = []
        self.buffer_keypad = []
        self.rect_drag_active = False
        self.rect_start = None
        self.rect_end = None

    # ======================= LISTA AZIONI =======================

    def _descr_azione(self, a):
        t = a.get("tipo")
        if t == "click":
            return f"Click @({a['rx']:.2f},{a['ry']:.2f})"
        if t == "click_rect":
            r = a.get("rect", [0, 0, 0, 0])
            return f"ClickRect [{r[0]:.2f},{r[1]:.2f}]->[{r[2]:.2f},{r[3]:.2f}]"
        if t == "click_poly":
            return f"ClickPoly ({len(a.get('poly', []))} vertici)"
        if t == "drag":
            return f"Drag ({a['start_rx']:.2f},{a['start_ry']:.2f})->({a['end_rx']:.2f},{a['end_ry']:.2f})"
        if t == "drag_multi":
            return f"MultiDrag ({len(a.get('punti', []))} punti)"
        if t == "drag_zone":
            return f"DragZona ({len(a.get('zone_a', []))}v -> {len(a.get('zone_b', []))}v)"
        if t == "drag_hold":
            return (f"DragTieni ({a['start_rx']:.2f},{a['start_ry']:.2f})"
                    f"->({a['end_rx']:.2f},{a['end_ry']:.2f})"
                    f" H:{a.get('hold', 0):.2f}s")
        if t == "wiring":
            return f"Fix Wiring (4 cavi + visore colore)"
        if t == "sync_click":
            return f"Sync Click ({len(a.get('punti', []))} coppie)"
        if t == "yolo_drag":
            return f"Drag YOLO '{a.get('yolo_model')}' ROI({len(a.get('roi_poly', []))}v)"
        if t == "yolo_drag_all":
            return f"Drag ALL YOLO '{a.get('yolo_model')}' ROI({len(a.get('roi_poly', []))}v)"
        if t == "yolo_click":
            return f"Click YOLO '{a.get('yolo_model')}' ROI({len(a.get('roi_poly', []))}v)"
        if t == "yolo_click_all":
            return f"Click ALL YOLO '{a.get('yolo_model')}' ROI({len(a.get('roi_poly', []))}v)"
        if t == "yolo_drag_seq":
            return f"Drag Seq YOLO '{a.get('yolo_model')}' ROI({len(a.get('roi_poly', []))}v)"
        if t == "click_until":
            return f"Click Until ({len(a.get('punti', []))} coppie)"
        if t == "simon_says":
            return f"Simon Says ({len(a.get('display', []))} associazioni)"
        if t == "click_anomaly":
            return f"Click Anomalia ({len(a.get('punti', []))} coppie)"
        if t == "number_match":
            return f"Number Match ({len(a.get('buttons', []))} numeri)"
        if t == "ocr_keypad":
            return f"OCR Keypad (ROI + 10 tasti)"
        if t == "cooldown":
            return f"Cooldown / Cambio Fase ({a.get('durata', 0)}s)"
        return str(t)

    def aggiorna_lista(self):
        if not dpg.does_item_exist(self.TAG_LIST):
            return
        dpg.delete_item(self.TAG_LIST, children_only=True)
        for i, a in enumerate(self.azioni):
            sel = (i == self.sel_idx)
            col_testo = (255, 255, 0) if sel else (255, 255, 255)
            prefix    = "> " if sel else "  "
            with dpg.group(horizontal=True, parent=self.TAG_LIST):
                dpg.add_text(f"{prefix}{i+1}. {self._descr_azione(a)}",
                             color=col_testo)
                dpg.add_button(label="^", user_data=i, callback=self._sposta_su, width=22)
                dpg.add_button(label="v", user_data=i, callback=self._sposta_giu, width=22)
                dpg.add_button(label="X", user_data=i, callback=self._elimina_azione, width=22)
                _ts = (f"D:{a.get('durata',0):.2f}s"
                       + (f" H:{a.get('hold',0):.2f}s"
                          if a.get("tipo") == "drag_hold" else "")
                       + f" P:{a.get('attesa',0):.2f}s")
                dpg.add_text(_ts, color=(100, 200, 255))

    def _sposta_su(self, sender, app_data, user_data):
        i = user_data
        if i > 0:
            self.azioni[i], self.azioni[i-1] = self.azioni[i-1], self.azioni[i]
            if self.sel_idx == i:
                self.sel_idx = i - 1
            elif self.sel_idx == i - 1:
                self.sel_idx = i
            self.aggiorna_lista(); self.aggiorna_preview()
            self._aggiorna_pannello_selezione()

    def _sposta_giu(self, sender, app_data, user_data):
        i = user_data
        if i < len(self.azioni) - 1:
            self.azioni[i], self.azioni[i+1] = self.azioni[i+1], self.azioni[i]
            if self.sel_idx == i:
                self.sel_idx = i + 1
            elif self.sel_idx == i + 1:
                self.sel_idx = i
            self.aggiorna_lista(); self.aggiorna_preview()
            self._aggiorna_pannello_selezione()

    def _elimina_azione(self, sender, app_data, user_data):
        i = user_data
        if 0 <= i < len(self.azioni):
            self.azioni.pop(i)
            if self.sel_idx == i:
                self.sel_idx = -1
            elif self.sel_idx > i:
                self.sel_idx -= 1
            self.aggiorna_lista(); self.aggiorna_preview()
            self._aggiorna_pannello_selezione()

    # ======================= PREVIEW LIVE =======================

    def aggiorna_frame(self, forza=False):
        if not self.e_aperto():
            return
        if not _WIN_OK:
            return
        if not self.is_live and not forza:
            return
        if self.frozen and not forza:
            return

        nome_finestra = dpg.get_value(self.TAG_IN_WIN_NAME)
        hwnd = win32gui.FindWindow(None, nome_finestra)
        if not hwnd:
            return
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

    def aggiorna_preview(self):
        if not dpg.does_item_exist(self.TAG_CANVAS):
            return
        dpg.delete_item(self.TAG_CANVAS, children_only=True)

        if self.texture_width > 0 and dpg.does_item_exist(self.TAG_BG_TEX):
            dpg.draw_image(self.TAG_BG_TEX, (0, 0),
                           (self.preview_w, self.preview_h),
                           parent=self.TAG_CANVAS)
        else:
            dpg.draw_rectangle((0, 0), (self.preview_w, self.preview_h),
                               color=(100, 100, 100, 255),
                               fill=(40, 40, 40, 255),
                               parent=self.TAG_CANVAS)

        for i, a in enumerate(self.azioni):
            self._disegna_azione(i, a, selezionato=(i == self.sel_idx))

        self._disegna_buffer_corrente()

        if self.frozen:
            dpg.draw_rectangle((8, 8), (135, 34),
                               color=(0, 0, 0, 200),
                               fill=(0, 0, 0, 180),
                               parent=self.TAG_CANVAS)
            dpg.draw_text((14, 12), "FROZEN [F]",
                          color=(100, 220, 255, 255), size=18,
                          parent=self.TAG_CANVAS)

    def _px(self, rx, ry):
        return rx * self.preview_w, ry * self.preview_h

    def _disegna_azione(self, idx, a, selezionato=False):
        num = str(idx + 1)
        t = a.get("tipo")
        p = self.TAG_CANVAS
        SEL_COL = (255, 255, 0, 255)
        SEL_TH  = 3 

        if t == "click":
            x, y = self._px(a["rx"], a["ry"])
            dpg.draw_circle((x, y), 8, color=(0, 255, 0), fill=(0, 200, 0), parent=p)
            dpg.draw_text((x + 12, y - 12), num, color=(255, 255, 255), size=18, parent=p)
            if selezionato:
                dpg.draw_circle((x, y), 14, color=SEL_COL, thickness=SEL_TH, parent=p)

        elif t == "click_rect":
            r = a["rect"]
            x1, y1 = self._px(r[0], r[1])
            x2, y2 = self._px(r[2], r[3])
            dpg.draw_rectangle((x1, y1), (x2, y2),
                               color=(180, 255, 180, 255),
                               fill=(180, 255, 180, 40), parent=p)
            dpg.draw_text((x1 + 4, y1 + 4), num, color=(180, 255, 180), size=18, parent=p)
            if selezionato:
                dpg.draw_rectangle((x1 - 3, y1 - 3), (x2 + 3, y2 + 3),
                                   color=SEL_COL, thickness=SEL_TH, parent=p)

        elif t == "click_poly":
            pts = [self._px(px, py) for px, py in a["poly"]]
            if len(pts) >= 3:
                dpg.draw_polygon(pts, color=(200, 180, 255, 255),
                                 fill=(200, 180, 255, 40), parent=p)
                dpg.draw_text(pts[0], num, color=(200, 180, 255), size=18, parent=p)
                if selezionato:
                    dpg.draw_polygon(pts, color=SEL_COL,
                                     thickness=SEL_TH, parent=p)

        elif t == "drag":
            sx, sy = self._px(a["start_rx"], a["start_ry"])
            ex, ey = self._px(a["end_rx"],   a["end_ry"])
            dpg.draw_circle((sx, sy), 6, color=(255, 200, 0), fill=(255, 200, 0), parent=p)
            dpg.draw_arrow((ex, ey), (sx, sy), color=(255, 50, 50),
                           thickness=3, size=18, parent=p)
            dpg.draw_text((sx + 12, sy - 12), num, color=(255, 255, 255), size=18, parent=p)
            if selezionato:
                dpg.draw_circle((sx, sy), 12, color=SEL_COL, thickness=SEL_TH, parent=p)
                dpg.draw_circle((ex, ey), 12, color=SEL_COL, thickness=SEL_TH, parent=p)

        elif t == "drag_multi":
            pts = [self._px(px, py) for px, py in a["punti"]]
            for i in range(len(pts) - 1):
                dpg.draw_arrow(pts[i+1], pts[i], color=(255, 120, 50),
                               thickness=2, size=14, parent=p)
            if pts:
                dpg.draw_circle(pts[0], 6, color=(255, 200, 0),
                                fill=(255, 200, 0), parent=p)
                dpg.draw_text((pts[0][0] + 12, pts[0][1] - 12), num,
                              color=(255, 255, 255), size=18, parent=p)
                if selezionato:
                    for pt in pts:
                        dpg.draw_circle(pt, 11, color=SEL_COL,
                                        thickness=SEL_TH, parent=p)

        elif t == "drag_hold":
            sx, sy = self._px(a["start_rx"], a["start_ry"])
            ex, ey = self._px(a["end_rx"],   a["end_ry"])
            hold   = a.get("hold", 0)
            dpg.draw_circle((sx, sy), 6, color=(255, 140, 180),
                            fill=(255, 140, 180), parent=p)
            dpg.draw_arrow((ex, ey), (sx, sy), color=(255, 80, 160),
                           thickness=3, size=18, parent=p)
            hold_r = min(30, max(10, int(hold * 8 + 10)))
            dpg.draw_circle((ex, ey), hold_r,
                            color=(255, 80, 160, 140), fill=(255, 80, 160, 60), parent=p)
            dpg.draw_text((ex + hold_r + 4, ey - 8),
                          f"H:{hold:.1f}s", color=(255, 140, 180), size=16, parent=p)
            dpg.draw_text((sx + 12, sy - 12), num,
                          color=(255, 255, 255), size=18, parent=p)
            if selezionato:
                dpg.draw_circle((sx, sy), 12,
                                color=SEL_COL, thickness=SEL_TH, parent=p)
                dpg.draw_circle((ex, ey), hold_r + 4,
                                color=SEL_COL, thickness=SEL_TH, parent=p)

        elif t == "drag_zone":
            poly_a = [self._px(px, py) for px, py in a["zone_a"]]
            poly_b = [self._px(px, py) for px, py in a["zone_b"]]
            if len(poly_a) >= 3:
                dpg.draw_polygon(poly_a, color=(255, 200, 0, 255),
                                 fill=(255, 200, 0, 40), parent=p)
            if len(poly_b) >= 3:
                dpg.draw_polygon(poly_b, color=(255, 50, 50, 255),
                                 fill=(255, 50, 50, 40), parent=p)
            if poly_a and poly_b:
                ca_x = sum(pt[0] for pt in poly_a) / len(poly_a)
                ca_y = sum(pt[1] for pt in poly_a) / len(poly_a)
                cb_x = sum(pt[0] for pt in poly_b) / len(poly_b)
                cb_y = sum(pt[1] for pt in poly_b) / len(poly_b)
                dpg.draw_arrow((cb_x, cb_y), (ca_x, ca_y),
                               color=(255, 255, 255), thickness=2, size=14, parent=p)
                dpg.draw_text((ca_x + 12, ca_y - 12), num,
                              color=(255, 255, 255), size=18, parent=p)
            if selezionato:
                if len(poly_a) >= 3:
                    dpg.draw_polygon(poly_a, color=SEL_COL,
                                     thickness=SEL_TH, parent=p)
                if len(poly_b) >= 3:
                    dpg.draw_polygon(poly_b, color=SEL_COL,
                                     thickness=SEL_TH, parent=p)
                                     
        elif t == "wiring":
            for cx, cy in a.get("left", []):
                pt = self._px(cx, cy)
                dpg.draw_circle(pt, 5, color=(200, 255, 100), fill=(200, 255, 100), parent=p)
            for cx, cy in a.get("right", []):
                pt = self._px(cx, cy)
                dpg.draw_circle(pt, 5, color=(255, 160, 50), fill=(255, 160, 50), parent=p)
            for cx, cy in a.get("lights", []):
                pt = self._px(cx, cy)
                dpg.draw_circle(pt, 6, color=(255, 255, 100), fill=(255, 255, 100), parent=p)
                dpg.draw_circle(pt, 10, color=(255, 255, 100), thickness=1, parent=p)
                
        elif t == "sync_click":
            for i, (cx, cy, bx, by) in enumerate(a.get("punti", [])):
                pc = self._px(cx, cy)
                pb = self._px(bx, by)
                dpg.draw_circle(pc, 5, color=(255, 255, 100), fill=(255, 255, 100), parent=p)
                dpg.draw_circle(pb, 5, color=(255, 100, 100), fill=(255, 100, 100), parent=p)
                dpg.draw_arrow(pb, pc, color=(255, 200, 150), thickness=2, size=10, parent=p)
                if selezionato:
                    dpg.draw_circle(pc, 10, color=SEL_COL, thickness=SEL_TH, parent=p)
                    dpg.draw_circle(pb, 10, color=SEL_COL, thickness=SEL_TH, parent=p)
                    
        elif t == "yolo_drag":
            ex, ey = self._px(a["end_rx"], a["end_ry"])
            dpg.draw_circle((ex, ey), 8, color=(255, 100, 100), fill=(255, 100, 100, 100), parent=p)
            dpg.draw_text((ex + 12, ey - 12), f"{num} (YOLO: {a.get('yolo_model')})", color=(255, 100, 100), size=16, parent=p)
            
            roi_poly = a.get("roi_poly", [])
            if len(roi_poly) >= 3:
                za = [self._px(px, py) for px, py in roi_poly]
                dpg.draw_polygon(za, color=(255, 100, 255, 150), fill=(255, 100, 255, 40), parent=p)
                cx = sum(pt[0] for pt in roi_poly) / len(roi_poly)
                cy = sum(pt[1] for pt in roi_poly) / len(roi_poly)
                c_px, c_py = self._px(cx, cy)
                dpg.draw_arrow((ex, ey), (c_px, c_py), color=(255, 150, 255, 150), thickness=2, size=10, parent=p)

            if selezionato:
                dpg.draw_circle((ex, ey), 14, color=SEL_COL, thickness=SEL_TH, parent=p)
                if len(roi_poly) >= 3:
                    dpg.draw_polygon(za, color=SEL_COL, thickness=SEL_TH, parent=p)
                    
        elif t == "yolo_drag_all":
            ex, ey = self._px(a["end_rx"], a["end_ry"])
            dpg.draw_circle((ex, ey), 8, color=(255, 150, 50), fill=(255, 150, 50, 100), parent=p)
            dpg.draw_text((ex + 12, ey - 12), f"{num} (ALL YOLO: {a.get('yolo_model')})", color=(255, 150, 50), size=16, parent=p)
            
            roi_poly = a.get("roi_poly", [])
            if len(roi_poly) >= 3:
                za = [self._px(px, py) for px, py in roi_poly]
                dpg.draw_polygon(za, color=(255, 150, 50, 150), fill=(255, 150, 50, 40), parent=p)
                cx = sum(pt[0] for pt in roi_poly) / len(roi_poly)
                cy = sum(pt[1] for pt in roi_poly) / len(roi_poly)
                c_px, c_py = self._px(cx, cy)
                dpg.draw_arrow((ex, ey), (c_px, c_py), color=(255, 180, 100, 150), thickness=2, size=10, parent=p)

            if selezionato:
                dpg.draw_circle((ex, ey), 14, color=SEL_COL, thickness=SEL_TH, parent=p)
                if len(roi_poly) >= 3:
                    dpg.draw_polygon(za, color=SEL_COL, thickness=SEL_TH, parent=p)

        elif t == "yolo_click":
            roi_poly = a.get("roi_poly", [])
            if len(roi_poly) >= 3:
                za = [self._px(px, py) for px, py in roi_poly]
                dpg.draw_polygon(za, color=(100, 255, 100, 150), fill=(100, 255, 100, 40), parent=p)
                cx = sum(pt[0] for pt in roi_poly) / len(roi_poly)
                cy = sum(pt[1] for pt in roi_poly) / len(roi_poly)
                c_px, c_py = self._px(cx, cy)
                dpg.draw_circle((c_px, c_py), 8, color=(100, 255, 100), fill=(100, 255, 100, 100), parent=p)
                dpg.draw_text((c_px + 12, c_py - 12), f"{num} (YOLO Click: {a.get('yolo_model')})", color=(100, 255, 100), size=16, parent=p)

            if selezionato:
                if len(roi_poly) >= 3:
                    dpg.draw_polygon(za, color=SEL_COL, thickness=SEL_TH, parent=p)
                    
        elif t == "yolo_click_all":
            roi_poly = a.get("roi_poly", [])
            if len(roi_poly) >= 3:
                za = [self._px(px, py) for px, py in roi_poly]
                dpg.draw_polygon(za, color=(100, 255, 150, 150), fill=(100, 255, 150, 40), parent=p)
                cx = sum(pt[0] for pt in roi_poly) / len(roi_poly)
                cy = sum(pt[1] for pt in roi_poly) / len(roi_poly)
                c_px, c_py = self._px(cx, cy)
                dpg.draw_circle((c_px, c_py), 8, color=(100, 255, 150), fill=(100, 255, 150, 100), parent=p)
                dpg.draw_text((c_px + 12, c_py - 12), f"{num} (ALL YOLO Click: {a.get('yolo_model')})", color=(100, 255, 150), size=16, parent=p)

            if selezionato:
                if len(roi_poly) >= 3:
                    dpg.draw_polygon(za, color=SEL_COL, thickness=SEL_TH, parent=p)

        elif t == "yolo_drag_seq":
            roi_poly = a.get("roi_poly", [])
            if len(roi_poly) >= 3:
                za = [self._px(px, py) for px, py in roi_poly]
                dpg.draw_polygon(za, color=(255, 120, 200, 150), fill=(255, 120, 200, 40), parent=p)
                cx = sum(pt[0] for pt in roi_poly) / len(roi_poly)
                cy = sum(pt[1] for pt in roi_poly) / len(roi_poly)
                c_px, c_py = self._px(cx, cy)
                dpg.draw_circle((c_px, c_py), 8, color=(255, 120, 200), fill=(255, 120, 200, 100), parent=p)
                dpg.draw_text((c_px + 12, c_py - 12), f"{num} (SEQ YOLO: {a.get('yolo_model')})", color=(255, 120, 200), size=16, parent=p)
            if selezionato:
                if len(roi_poly) >= 3:
                    dpg.draw_polygon(za, color=SEL_COL, thickness=SEL_TH, parent=p)

        elif t == "click_until":
            for i, (cx, cy, bx, by) in enumerate(a.get("punti", [])):
                pc = self._px(cx, cy)
                pb = self._px(bx, by)
                dpg.draw_circle(pc, 5, color=(255, 255, 255), fill=(255, 255, 255), parent=p)
                dpg.draw_circle(pb, 5, color=(100, 255, 255), fill=(100, 255, 255), parent=p)
                dpg.draw_arrow(pb, pc, color=(200, 255, 255), thickness=2, size=10, parent=p)
                if selezionato:
                    dpg.draw_circle(pc, 10, color=SEL_COL, thickness=SEL_TH, parent=p)
                    dpg.draw_circle(pb, 10, color=SEL_COL, thickness=SEL_TH, parent=p)
                    
        elif t == "simon_says":
            for i, (dx, dy) in enumerate(a.get("display", [])):
                pd = self._px(dx, dy)
                pk = self._px(a["keypad"][i][0], a["keypad"][i][1])
                dpg.draw_circle(pd, 6, color=(100, 200, 255), fill=(100, 200, 255), parent=p)
                dpg.draw_circle(pk, 6, color=(255, 100, 255), fill=(255, 100, 255), parent=p)
                dpg.draw_arrow(pk, pd, color=(200, 150, 255, 150), thickness=2, size=10, parent=p)
                if selezionato:
                    dpg.draw_circle(pd, 12, color=SEL_COL, thickness=SEL_TH, parent=p)
                    dpg.draw_circle(pk, 12, color=SEL_COL, thickness=SEL_TH, parent=p)

        elif t == "click_anomaly":
            for i, p_list in enumerate(a.get("punti", [])):
                if len(p_list) == 4:
                    cx, cy, bx, by = p_list
                    pc = self._px(cx, cy)
                    pb = self._px(bx, by)
                    dpg.draw_circle(pc, 5, color=(255, 100, 200), fill=(255, 100, 200), parent=p)
                    dpg.draw_circle(pb, 5, color=(255, 50, 100), fill=(255, 50, 100), parent=p)
                    dpg.draw_arrow(pb, pc, color=(255, 150, 200), thickness=2, size=10, parent=p)
                    dpg.draw_text((pc[0] + 10, pc[1] - 10), str(i+1), color=(255, 100, 200), size=14, parent=p)
                    if selezionato:
                        dpg.draw_circle(pc, 10, color=SEL_COL, thickness=SEL_TH, parent=p)
                        dpg.draw_circle(pb, 10, color=SEL_COL, thickness=SEL_TH, parent=p)
                elif len(p_list) == 2:
                    cx, cy = p_list
                    pc = self._px(cx, cy)
                    dpg.draw_circle(pc, 5, color=(255, 100, 200), fill=(255, 100, 200), parent=p)
                    dpg.draw_text((pc[0] + 10, pc[1] - 10), str(i+1) + " (old)", color=(255, 100, 200), size=14, parent=p)
                    if selezionato:
                        dpg.draw_circle(pc, 10, color=SEL_COL, thickness=SEL_TH, parent=p)
                        
        elif t == "number_match":
            for k, btn in enumerate(a.get("buttons", [])):
                r = btn["rect"]
                x1, y1 = self._px(r[0], r[1])
                x2, y2 = self._px(r[2], r[3])
                dpg.draw_rectangle((x1, y1), (x2, y2), color=(100, 255, 255, 255), fill=(100, 255, 255, 40), parent=p)
                dpg.draw_text((x1 + 4, y1 + 4), f"{num}.{k+1}", color=(100, 255, 255), size=14, parent=p)
                if selezionato:
                    dpg.draw_rectangle((x1 - 3, y1 - 3), (x2 + 3, y2 + 3),
                                       color=SEL_COL, thickness=SEL_TH, parent=p)

        elif t == "ocr_keypad":
            roi = a.get("roi_poly", [])
            kp = a.get("keypad", [])
            if len(roi) >= 3:
                za = [self._px(px, py) for px, py in roi]
                dpg.draw_polygon(za, color=(100, 255, 200, 150), fill=(100, 255, 200, 40), parent=p)
                if selezionato: dpg.draw_polygon(za, color=SEL_COL, thickness=SEL_TH, parent=p)
            for i, (kx, ky) in enumerate(kp):
                pk = self._px(kx, ky)
                dpg.draw_circle(pk, 7, color=(255, 100, 255), fill=(255, 100, 255), parent=p)
                dpg.draw_text((pk[0]-4, pk[1]-6), str(i), color=(0, 0, 0, 255), size=12, parent=p)
                if selezionato: dpg.draw_circle(pk, 11, color=SEL_COL, thickness=SEL_TH, parent=p)

        if selezionato:
            self._disegna_handles(a)

    def _disegna_handles(self, a):
        p = self.TAG_CANVAS
        HANDLE_R    = 5
        HANDLE_FILL = (255, 255, 255, 230)
        HANDLE_EDGE = (30, 30, 30, 255)

        def h(vx, vy):
            x, y = self._px(vx, vy)
            dpg.draw_circle((x, y), HANDLE_R, color=HANDLE_EDGE,
                            fill=HANDLE_FILL, thickness=1, parent=p)

        t = a.get("tipo")
        if t == "click":
            h(a["rx"], a["ry"])
        elif t == "click_rect":
            r = a["rect"]
            h(r[0], r[1])
            h(r[2], r[3])
        elif t == "click_poly":
            for vx, vy in a.get("poly", []):
                h(vx, vy)
        elif t in ("drag", "drag_hold"):
            h(a["start_rx"], a["start_ry"])
            h(a["end_rx"],   a["end_ry"])
        elif t == "drag_multi":
            for vx, vy in a.get("punti", []):
                h(vx, vy)
        elif t == "drag_zone":
            for vx, vy in a.get("zone_a", []):
                h(vx, vy)
            for vx, vy in a.get("zone_b", []):
                h(vx, vy)
        elif t == "wiring":
            for k, (vx, vy) in enumerate(a.get("left", [])):
                h(vx, vy)
            for k, (vx, vy) in enumerate(a.get("right", [])):
                h(vx, vy)
            for k, (vx, vy) in enumerate(a.get("lights", [])):
                h(vx, vy)
        elif t == "sync_click":
            for k, (cx, cy, bx, by) in enumerate(a.get("punti", [])):
                h(cx, cy)
                h(bx, by)
        elif t in ("yolo_drag", "yolo_drag_all"):
            h(a["end_rx"], a["end_ry"])
            for k, (vx, vy) in enumerate(a.get("roi_poly", [])):
                h(vx, vy)
        elif t in ("yolo_click", "yolo_click_all", "yolo_drag_seq"):
            for k, (vx, vy) in enumerate(a.get("roi_poly", [])):
                h(vx, vy)
        elif t == "click_until":
            for k, (cx, cy, bx, by) in enumerate(a.get("punti", [])):
                h(cx, cy)
                h(bx, by)
        elif t == "simon_says":
            for k, (dx, dy) in enumerate(a.get("display", [])):
                h(dx, dy)
            for k, (kx, ky) in enumerate(a.get("keypad", [])):
                h(kx, ky)
        elif t == "click_anomaly":
            for k, p_list in enumerate(a.get("punti", [])):
                if len(p_list) == 4:
                    cx, cy, bx, by = p_list
                    h(cx, cy)
                    h(bx, by)
                elif len(p_list) == 2:
                    cx, cy = p_list
                    h(cx, cy)
        elif t == "number_match":
            for btn in a.get("buttons", []):
                r = btn["rect"]
                h(r[0], r[1])
                h(r[2], r[3])
        elif t == "ocr_keypad":
            for k, (vx, vy) in enumerate(a.get("roi_poly", [])):
                h(vx, vy)
            for k, (vx, vy) in enumerate(a.get("keypad", [])):
                h(vx, vy)

    def _disegna_buffer_corrente(self):
        p = self.TAG_CANVAS

        if self.stato in (self.WAIT_POLY,
                          self.WAIT_POLY_ZONE_A,
                          self.WAIT_POLY_ZONE_B,
                          self.WAIT_YOLO_POLY,
                          self.WAIT_YOLO_DEST,
                          self.WAIT_YOLO_ALL_POLY,
                          self.WAIT_YOLO_ALL_DEST,
                          self.WAIT_YOLO_CLICK_POLY,
                          self.WAIT_YOLO_CLICK_ALL_POLY,
                          self.WAIT_YOLO_SEQ_POLY,
                          self.WAIT_OCR_POLY):
            pts = [self._px(rx, ry) for rx, ry in self.buffer_punti]
            for pt in pts:
                dpg.draw_circle(pt, 4, color=(255, 255, 0),
                                fill=(255, 255, 0), parent=p)
            for i in range(len(pts) - 1):
                dpg.draw_line(pts[i], pts[i+1], color=(255, 255, 0), thickness=2, parent=p)

            if self.stato == self.WAIT_POLY_ZONE_B and len(self.buffer_zone_a) >= 3:
                za = [self._px(rx, ry) for rx, ry in self.buffer_zone_a]
                dpg.draw_polygon(za, color=(255, 200, 0, 255),
                                 fill=(255, 200, 0, 40), parent=p)

            if self.stato == self.WAIT_YOLO_DEST and len(self.buffer_zone_a) >= 3:
                za = [self._px(rx, ry) for rx, ry in self.buffer_zone_a]
                dpg.draw_polygon(za, color=(255, 100, 255, 255),
                                 fill=(255, 100, 255, 40), parent=p)

            if self.stato == self.WAIT_YOLO_ALL_DEST and len(self.buffer_zone_a) >= 3:
                za = [self._px(rx, ry) for rx, ry in self.buffer_zone_a]
                dpg.draw_polygon(za, color=(255, 150, 50, 255),
                                 fill=(255, 150, 50, 40), parent=p)
            
            if self.stato == self.WAIT_OCR_KEYPAD and len(self.buffer_zone_a) >= 3:
                za = [self._px(rx, ry) for rx, ry in self.buffer_zone_a]
                dpg.draw_polygon(za, color=(100, 255, 200, 255), fill=(100, 255, 200, 40), parent=p)

        if self.stato == self.WAIT_MULTI:
            pts = [self._px(rx, ry) for rx, ry in self.buffer_punti]
            for pt in pts:
                dpg.draw_circle(pt, 5, color=(255, 180, 100),
                                fill=(255, 180, 100), parent=p)
            for i in range(len(pts) - 1):
                dpg.draw_arrow(pts[i+1], pts[i], color=(255, 180, 100),
                               thickness=2, size=12, parent=p)

        if self.stato == "WAIT_RECT_ON_CANVAS" and self.rect_start and self.rect_end:
            x1, y1 = self._px(*self.rect_start)
            x2, y2 = self._px(*self.rect_end)
            dpg.draw_rectangle((x1, y1), (x2, y2),
                               color=(180, 255, 180, 255),
                               fill=(180, 255, 180, 40), parent=p)

        if self.stato in (self.WAIT_DRAG_END, self.WAIT_DRAG_HOLD_END) and self.buffer_punti:
            rx, ry = self.buffer_punti[0]
            x, y = self._px(rx, ry)
            col = (255, 200, 0) if self.stato == self.WAIT_DRAG_END else (255, 140, 180)
            dpg.draw_circle((x, y), 6, color=col, fill=col, parent=p)
            dpg.draw_text((x + 10, y - 10), "A", color=col, size=16, parent=p)

        if self.stato in (self.WAIT_WIRING_L, self.WAIT_WIRING_R, self.WAIT_WIRING_C):
            for (rx, ry) in self.buffer_w_l:
                dpg.draw_circle(self._px(rx, ry), 5, color=(200, 255, 100), fill=(200, 255, 100), parent=p)
            for (rx, ry) in self.buffer_w_r:
                dpg.draw_circle(self._px(rx, ry), 5, color=(255, 160, 50), fill=(255, 160, 50), parent=p)
            for (rx, ry) in self.buffer_w_c:
                dpg.draw_circle(self._px(rx, ry), 6, color=(255, 255, 100), fill=(255, 255, 100), parent=p)

        if self.stato in (self.WAIT_SYNC_CHECK, self.WAIT_SYNC_BTN):
            for (cx, cy, bx, by) in self.buffer_sync:
                pc = self._px(cx, cy)
                pb = self._px(bx, by)
                dpg.draw_circle(pc, 5, color=(255, 255, 100), fill=(255, 255, 100), parent=p)
                dpg.draw_circle(pb, 5, color=(255, 100, 100), fill=(255, 100, 100), parent=p)
                dpg.draw_arrow(pb, pc, color=(255, 200, 150), thickness=2, size=10, parent=p)
            if self.stato == self.WAIT_SYNC_BTN and self.buffer_punti:
                pc = self._px(self.buffer_punti[0][0], self.buffer_punti[0][1])
                dpg.draw_circle(pc, 5, color=(255, 255, 100), fill=(255, 255, 100), parent=p)
                
        if self.stato in (self.WAIT_CUC_CHK, self.WAIT_CUC_BTN):
            for (cx, cy, bx, by) in self.buffer_cuc:
                pc = self._px(cx, cy)
                pb = self._px(bx, by)
                dpg.draw_circle(pc, 5, color=(255, 255, 255), fill=(255, 255, 255), parent=p)
                dpg.draw_circle(pb, 5, color=(100, 255, 255), fill=(100, 255, 255), parent=p)
                dpg.draw_arrow(pb, pc, color=(200, 255, 255), thickness=2, size=10, parent=p)
            if self.stato == self.WAIT_CUC_BTN and self.buffer_punti:
                pc = self._px(self.buffer_punti[0][0], self.buffer_punti[0][1])
                dpg.draw_circle(pc, 5, color=(255, 255, 255), fill=(255, 255, 255), parent=p)
                
        if self.stato in (self.WAIT_SIMON_DISPLAY, self.WAIT_SIMON_KEYPAD):
            for (rx, ry) in self.buffer_simon_d:
                pd = self._px(rx, ry)
                dpg.draw_circle(pd, 6, color=(100, 200, 255), fill=(100, 200, 255), parent=p)
            for i, (rx, ry) in enumerate(self.buffer_simon_k):
                pk = self._px(rx, ry)
                dpg.draw_circle(pk, 6, color=(255, 100, 255), fill=(255, 100, 255), parent=p)
                if i < len(self.buffer_simon_d):
                    pd = self._px(self.buffer_simon_d[i][0], self.buffer_simon_d[i][1])
                    dpg.draw_arrow(pk, pd, color=(200, 150, 255, 150), thickness=2, size=10, parent=p)
                    
        if self.stato in (self.WAIT_ANOMALY_CHK, self.WAIT_ANOMALY_BTN):
            for (cx, cy, bx, by) in self.buffer_anomaly:
                pc = self._px(cx, cy)
                pb = self._px(bx, by)
                dpg.draw_circle(pc, 5, color=(255, 100, 200), fill=(255, 100, 200), parent=p)
                dpg.draw_circle(pb, 5, color=(255, 50, 100), fill=(255, 50, 100), parent=p)
                dpg.draw_arrow(pb, pc, color=(255, 150, 200), thickness=2, size=10, parent=p)
            if self.stato == self.WAIT_ANOMALY_BTN and self.buffer_punti:
                pc = self._px(self.buffer_punti[0][0], self.buffer_punti[0][1])
                dpg.draw_circle(pc, 5, color=(255, 100, 200), fill=(255, 100, 200), parent=p)
                
        if self.stato == self.WAIT_NUM_MATCH_RECT:
            for i, btn in enumerate(self.buffer_num_match):
                r = btn["rect"]
                x1, y1 = self._px(r[0], r[1])
                x2, y2 = self._px(r[2], r[3])
                dpg.draw_rectangle((x1, y1), (x2, y2), color=(100, 255, 255, 255), fill=(100, 255, 255, 40), parent=p)
                dpg.draw_text((x1 + 4, y1 + 4), f"{i+1}", color=(100, 255, 255), size=16, parent=p)
            if self.rect_start and self.rect_end:
                x1, y1 = self._px(*self.rect_start)
                x2, y2 = self._px(*self.rect_end)
                dpg.draw_rectangle((x1, y1), (x2, y2), color=(100, 255, 255, 255), fill=(100, 255, 255, 40), parent=p)
                
        if self.stato == self.WAIT_OCR_KEYPAD:
            for i, (kx, ky) in enumerate(self.buffer_keypad):
                pk = self._px(kx, ky)
                dpg.draw_circle(pk, 7, color=(255, 100, 255), fill=(255, 100, 255), parent=p)
                dpg.draw_text((pk[0]-4, pk[1]-6), str(i), color=(0, 0, 0, 255), size=12, parent=p)

    # ======================= EVENTI MOUSE SULLA PREVIEW =======================

    def _canvas_mouse_down(self, *_):
        pos = dpg.get_drawing_mouse_pos()
        rx = max(0.0, min(1.0, pos[0] / max(1, self.preview_w)))
        ry = max(0.0, min(1.0, pos[1] / max(1, self.preview_h)))

        if self.stato in ("WAIT_RECT_ON_CANVAS", self.WAIT_NUM_MATCH_RECT):
            self.rect_start = (rx, ry)
            self.rect_end   = (rx, ry)
            self.rect_drag_active = True
            threading.Thread(target=self._segui_mouse_rect, daemon=True).start()
            return

        inserimento_attivo = self.stato in (
            self.WAIT_CLICK, self.WAIT_DRAG_START, self.WAIT_DRAG_END,
            self.WAIT_MULTI, self.WAIT_POLY,
            self.WAIT_POLY_ZONE_A, self.WAIT_POLY_ZONE_B,
            self.WAIT_DRAG_HOLD_START, self.WAIT_DRAG_HOLD_END,
            self.WAIT_WIRING_L, self.WAIT_WIRING_R, self.WAIT_WIRING_C,
            self.WAIT_SYNC_CHECK, self.WAIT_SYNC_BTN,
            self.WAIT_YOLO_POLY, self.WAIT_YOLO_DEST,
            self.WAIT_YOLO_ALL_POLY, self.WAIT_YOLO_ALL_DEST,
            self.WAIT_CUC_CHK, self.WAIT_CUC_BTN,
            self.WAIT_YOLO_CLICK_POLY, self.WAIT_YOLO_CLICK_ALL_POLY,
            self.WAIT_YOLO_SEQ_POLY,
            self.WAIT_SIMON_DISPLAY, self.WAIT_SIMON_KEYPAD,
            self.WAIT_ANOMALY_CHK, self.WAIT_ANOMALY_BTN,
            self.WAIT_OCR_POLY, self.WAIT_OCR_KEYPAD
        )
        
        # Se c'è un inserimento attivo, il click sulla preview registra il punto
        if inserimento_attivo:
            self._piazza_punto_rel(rx, ry)
            return

        # Altrimenti, gestiamo la selezione o il drag dei vertici
        v_idx, v_key = self._hit_test_vertex(rx, ry)
        if v_idx >= 0:
            self._dragging_vertex = True
            self._drag_vx_idx     = v_idx
            self._drag_vx_key     = v_key
            self.sel_idx          = v_idx
            self._aggiorna_pannello_selezione()
            threading.Thread(target=self._segui_mouse_vertex, daemon=True).start()
            return

        idx = self._hit_test(rx, ry)
        self.sel_idx = idx
        self._aggiorna_pannello_selezione()
        self.aggiorna_preview()
        self.aggiorna_lista()

    def _piazza_punto_rel(self, rx, ry):
        durata = dpg.get_value(self.TAG_IN_DUR)
        attesa = dpg.get_value(self.TAG_IN_PAUSE)

        if self.stato == self.WAIT_CLICK:
            self.azioni.append({
                "tipo": "click", "rx": rx, "ry": ry,
                "durata": durata, "attesa": attesa,
            })
            self._reset_stato()
            self._imposta_istruzioni("Click aggiunto.")

        elif self.stato == self.WAIT_DRAG_START:
            self.buffer_punti = [(rx, ry)]
            self.stato = self.WAIT_DRAG_END
            self._imposta_istruzioni("Ora CLICK sulla preview per ARRIVO drag.", (255, 100, 100))

        elif self.stato == self.WAIT_DRAG_END:
            sx, sy = self.buffer_punti[0]
            self.azioni.append({
                "tipo": "drag",
                "start_rx": sx, "start_ry": sy,
                "end_rx":   rx, "end_ry":   ry,
                "durata": durata, "attesa": attesa,
            })
            self._reset_stato()
            self._imposta_istruzioni("Drag aggiunto.")

        elif self.stato == self.WAIT_DRAG_HOLD_START:
            self.buffer_punti = [(rx, ry)]
            self.stato = self.WAIT_DRAG_HOLD_END
            self._imposta_istruzioni(
                "Ora CLICK sulla preview per ARRIVO (verrà tenuto premuto).",
                (255, 140, 180))

        elif self.stato == self.WAIT_DRAG_HOLD_END:
            sx, sy = self.buffer_punti[0]
            hold = max(0.0, float(dpg.get_value(self.TAG_IN_HOLD)))
            self.azioni.append({
                "tipo":     "drag_hold",
                "start_rx": sx,     "start_ry": sy,
                "end_rx":   rx,     "end_ry":   ry,
                "durata":   durata, "hold":     hold, "attesa": attesa,
            })
            self._reset_stato()
            self._imposta_istruzioni(f"Drag+Tieni aggiunto (hold={hold:.2f}s).")

        elif self.stato == self.WAIT_WIRING_L:
            self.buffer_w_l.append((rx, ry))
            if len(self.buffer_w_l) >= 4:
                self.stato = self.WAIT_WIRING_R
                self._imposta_istruzioni("Ora clicca sui 4 CONNETTORI A DESTRA (1/4)", (255, 160, 50))
            else:
                self._imposta_istruzioni(f"Cavo {len(self.buffer_w_l)+1}/4...", (200, 255, 100))

        elif self.stato == self.WAIT_WIRING_R:
            self.buffer_w_r.append((rx, ry))
            if len(self.buffer_w_r) >= 4:
                self.stato = self.WAIT_WIRING_C
                self._imposta_istruzioni("Ora clicca sulle 4 LUCI INDICATRICI (1/4)", (255, 255, 100))
            else:
                self._imposta_istruzioni(f"Connettore {len(self.buffer_w_r)+1}/4...", (255, 160, 50))

        elif self.stato == self.WAIT_WIRING_C:
            self.buffer_w_c.append((rx, ry))
            if len(self.buffer_w_c) >= 4:
                self.azioni.append({
                    "tipo": "wiring", "left": self.buffer_w_l,
                    "right": self.buffer_w_r, "lights": self.buffer_w_c,
                    "durata": durata, "attesa": attesa,
                })
                self._reset_stato()
                self._imposta_istruzioni("Fix Wiring registrato correttamente!", (100, 255, 100))
            else:
                self._imposta_istruzioni(f"Luce {len(self.buffer_w_c)+1}/4...", (255, 255, 100))

        elif self.stato == self.WAIT_SYNC_CHECK:
            self.buffer_punti = [(rx, ry)]
            self.stato = self.WAIT_SYNC_BTN
            self._imposta_istruzioni("Ora clicca il BOTTONE DA PREMERE associato.", (255, 100, 100))

        elif self.stato == self.WAIT_SYNC_BTN:
            cx_rel, cy_rel = self.buffer_punti[0]
            self.buffer_sync.append((cx_rel, cy_rel, rx, ry))
            self.stato = self.WAIT_SYNC_CHECK
            self._imposta_istruzioni(f"Coppia {len(self.buffer_sync)} aggiunta. Clicca nuovo PUNTO CHECK o 'CHIUDI PUNTI'.", (255, 255, 100))

        elif self.stato == self.WAIT_YOLO_DEST:
            self.azioni.append({
                "tipo": "yolo_drag",
                "yolo_model": getattr(self, '_tmp_yolo_model', 'best.pt'),
                "roi_poly": [list(p) for p in self.buffer_zone_a],
                "end_rx": rx, "end_ry": ry,
                "durata": durata, "attesa": attesa
            })
            self._reset_stato()
            self._imposta_istruzioni(f"Drag YOLO aggiunto.", (100, 255, 100))

        elif self.stato == self.WAIT_YOLO_ALL_DEST:
            self.azioni.append({
                "tipo": "yolo_drag_all",
                "yolo_model": getattr(self, '_tmp_yolo_model', 'best.pt'),
                "roi_poly": [list(p) for p in self.buffer_zone_a],
                "end_rx": rx, "end_ry": ry,
                "durata": durata, "attesa": attesa
            })
            self._reset_stato()
            self._imposta_istruzioni(f"Drag ALL YOLO aggiunto.", (100, 255, 100))

        elif self.stato == self.WAIT_CUC_CHK:
            self.buffer_punti = [(rx, ry)]
            self.stato = self.WAIT_CUC_BTN
            self._imposta_istruzioni("Ora clicca il BOTTONE DA PREMERE associato.", (100, 255, 255))

        elif self.stato == self.WAIT_CUC_BTN:
            cx_rel, cy_rel = self.buffer_punti[0]
            self.buffer_cuc.append((cx_rel, cy_rel, rx, ry))
            self.stato = self.WAIT_CUC_CHK
            self._imposta_istruzioni(f"Coppia {len(self.buffer_cuc)} aggiunta. Clicca nuovo PUNTO CHECK o 'CHIUDI PUNTI'.", (255, 255, 255))

        elif self.stato == self.WAIT_SIMON_DISPLAY:
            self.buffer_simon_d.append((rx, ry))
            self._imposta_istruzioni(f"Luce display {len(self.buffer_simon_d)} mappata.", (100, 200, 255))
            
        elif self.stato == self.WAIT_SIMON_KEYPAD:
            self.buffer_simon_k.append((rx, ry))
            self._imposta_istruzioni(f"Bottone tastierino {len(self.buffer_simon_k)} mappato.", (255, 100, 255))

        elif self.stato == self.WAIT_ANOMALY_CHK:
            self.buffer_punti = [(rx, ry)]
            self.stato = self.WAIT_ANOMALY_BTN
            self._imposta_istruzioni("Ora clicca il BOTTONE DA PREMERE associato all'anomalia.", (255, 50, 100))

        elif self.stato == self.WAIT_ANOMALY_BTN:
            cx_rel, cy_rel = self.buffer_punti[0]
            self.buffer_anomaly.append((cx_rel, cy_rel, rx, ry))
            self.stato = self.WAIT_ANOMALY_CHK
            self._imposta_istruzioni(f"Coppia {len(self.buffer_anomaly)} aggiunta. Clicca nuovo CHECK o 'CHIUDI PUNTI'.", (255, 100, 200))
            
        elif self.stato == self.WAIT_OCR_KEYPAD:
            self.buffer_keypad.append((rx, ry))
            if len(self.buffer_keypad) == 10:
                self.azioni.append({
                    "tipo": "ocr_keypad",
                    "roi_poly": [list(p) for p in self.buffer_zone_a],
                    "keypad": [list(p) for p in self.buffer_keypad],
                    "durata": durata, "attesa": attesa
                })
                self._reset_stato()
                self._imposta_istruzioni("OCR Keypad salvato!", (100, 255, 100))
            else:
                self._imposta_istruzioni(f"Tasto {len(self.buffer_keypad)}/10 mappato.", (255, 100, 255))

        elif self.stato in (self.WAIT_MULTI, self.WAIT_POLY,
                            self.WAIT_POLY_ZONE_A, self.WAIT_POLY_ZONE_B,
                            self.WAIT_YOLO_POLY,
                            self.WAIT_YOLO_ALL_POLY,
                            self.WAIT_YOLO_CLICK_POLY,
                            self.WAIT_YOLO_CLICK_ALL_POLY,
                          self.WAIT_YOLO_SEQ_POLY,
                          self.WAIT_OCR_POLY):
            self.buffer_punti.append((rx, ry))
            self._imposta_istruzioni(
                f"Punto {len(self.buffer_punti)} aggiunto.", (200, 200, 200))

        self.aggiorna_lista()
        self.aggiorna_preview()

    def _segui_mouse_vertex(self):
        if not _WIN_OK:
            self._dragging_vertex = False
            return
        time.sleep(0.02)
        while self._dragging_vertex:
            lmb = (win32api.GetAsyncKeyState(win32con.VK_LBUTTON) & 0x8000) != 0
            if not lmb:
                break
            try:
                pos = dpg.get_drawing_mouse_pos()
                rx = max(0.0, min(1.0, pos[0] / max(1, self.preview_w)))
                ry = max(0.0, min(1.0, pos[1] / max(1, self.preview_h)))
                self._muovi_vertice(self._drag_vx_idx, self._drag_vx_key, rx, ry)
                self.aggiorna_preview()
            except Exception:
                pass
            time.sleep(0.015)

        self._dragging_vertex = False
        self._drag_vx_idx     = -1
        self._drag_vx_key     = None
        try:
            self.aggiorna_lista()
            self.aggiorna_preview()
            self._imposta_istruzioni("Vertice spostato.")
        except Exception:
            pass

    # ======================= HIT-TEST SELEZIONE =======================

    def _hit_test(self, rx, ry, tol_click=0.015, tol_line=0.012):
        for i in range(len(self.azioni) - 1, -1, -1):
            a = self.azioni[i]
            t = a.get("tipo")
            if t == "click":
                if math.hypot(rx - a["rx"], ry - a["ry"]) <= tol_click:
                    return i
            elif t == "click_rect":
                r = a["rect"]
                if min(r[0], r[2]) <= rx <= max(r[0], r[2]) and \
                   min(r[1], r[3]) <= ry <= max(r[1], r[3]):
                    return i
            elif t == "click_poly":
                if point_in_polygon(rx, ry, a["poly"]):
                    return i
            elif t in ("drag", "drag_hold"):
                if math.hypot(rx - a["start_rx"], ry - a["start_ry"]) <= tol_click:
                    return i
                if math.hypot(rx - a["end_rx"], ry - a["end_ry"]) <= tol_click:
                    return i
                if self._point_near_segment(rx, ry,
                        a["start_rx"], a["start_ry"],
                        a["end_rx"],   a["end_ry"], tol_line):
                    return i
            elif t == "drag_multi":
                pts = a.get("punti", [])
                for p in pts:
                    if math.hypot(rx - p[0], ry - p[1]) <= tol_click:
                        return i
                for k in range(len(pts) - 1):
                    if self._point_near_segment(rx, ry,
                            pts[k][0], pts[k][1],
                            pts[k+1][0], pts[k+1][1], tol_line):
                        return i
            elif t == "drag_zone":
                if point_in_polygon(rx, ry, a.get("zone_a", [])):
                    return i
                if point_in_polygon(rx, ry, a.get("zone_b", [])):
                    return i
            elif t == "wiring":
                for grp in ["left", "right", "lights"]:
                    for p in a.get(grp, []):
                        if math.hypot(rx - p[0], ry - p[1]) <= tol_click:
                            return i
            elif t == "sync_click":
                for cx, cy, bx, by in a.get("punti", []):
                    if math.hypot(rx - cx, ry - cy) <= tol_click: return i
                    if math.hypot(rx - bx, ry - by) <= tol_click: return i
            elif t in ("yolo_drag", "yolo_drag_all"):
                if math.hypot(rx - a["end_rx"], ry - a["end_ry"]) <= tol_click:
                    return i
                if point_in_polygon(rx, ry, a.get("roi_poly", [])):
                    return i
            elif t in ("yolo_click", "yolo_click_all", "yolo_drag_seq"):
                if point_in_polygon(rx, ry, a.get("roi_poly", [])):
                    return i
            elif t == "click_until":
                for cx, cy, bx, by in a.get("punti", []):
                    if math.hypot(rx - cx, ry - cy) <= tol_click: return i
                    if math.hypot(rx - bx, ry - by) <= tol_click: return i
            elif t == "simon_says":
                for cx, cy in a.get("display", []):
                    if math.hypot(rx - cx, ry - cy) <= tol_click: return i
                for bx, by in a.get("keypad", []):
                    if math.hypot(rx - bx, ry - by) <= tol_click: return i
            elif t == "click_anomaly":
                for p_list in a.get("punti", []):
                    if len(p_list) == 4:
                        cx, cy, bx, by = p_list
                        if math.hypot(rx - cx, ry - cy) <= tol_click: return i
                        if math.hypot(rx - bx, ry - by) <= tol_click: return i
                    elif len(p_list) == 2:
                        cx, cy = p_list
                        if math.hypot(rx - cx, ry - cy) <= tol_click: return i
            elif t == "number_match":
                for btn in a.get("buttons", []):
                    r = btn["rect"]
                    if min(r[0], r[2]) <= rx <= max(r[0], r[2]) and min(r[1], r[3]) <= ry <= max(r[1], r[3]):
                        return i
            elif t == "ocr_keypad":
                if point_in_polygon(rx, ry, a.get("roi_poly", [])): return i
                for px, py in a.get("keypad", []):
                    if math.hypot(rx - px, ry - py) <= tol_click: return i

        return -1

    @staticmethod
    def _point_near_segment(px, py, ax, ay, bx, by, tol):
        dx, dy = bx - ax, by - ay
        lung2 = dx * dx + dy * dy
        if lung2 < 1e-12:
            return math.hypot(px - ax, py - ay) <= tol
        t = ((px - ax) * dx + (py - ay) * dy) / lung2
        t = max(0.0, min(1.0, t))
        proj_x = ax + t * dx
        proj_y = ay + t * dy
        return math.hypot(px - proj_x, py - proj_y) <= tol

    def _hit_test_vertex(self, rx, ry, tol=0.018):
        best = (-1, None, float('inf'))
        for i in range(len(self.azioni) - 1, -1, -1):
            a = self.azioni[i]
            t = a.get("tipo")

            def check(px, py, key):
                nonlocal best
                d = math.hypot(rx - px, ry - py)
                if d <= tol and d < best[2]:
                    best = (i, key, d)

            if t == "click":
                check(a["rx"], a["ry"], 'c')
            elif t == "click_rect":
                r = a["rect"]
                check(r[0], r[1], 'r1')
                check(r[2], r[3], 'r2')
            elif t == "click_poly":
                for k, (vx, vy) in enumerate(a.get("poly", [])):
                    check(vx, vy, f'p{k}')
            elif t in ("drag", "drag_hold"):
                check(a["start_rx"], a["start_ry"], 's')
                check(a["end_rx"],   a["end_ry"],   'e')
            elif t == "drag_multi":
                for k, (vx, vy) in enumerate(a.get("punti", [])):
                    check(vx, vy, f'm{k}')
            elif t == "drag_zone":
                for k, (vx, vy) in enumerate(a.get("zone_a", [])):
                    check(vx, vy, f'a{k}')
                for k, (vx, vy) in enumerate(a.get("zone_b", [])):
                    check(vx, vy, f'b{k}')
            elif t == "wiring":
                for k, (vx, vy) in enumerate(a.get("left", [])):
                    check(vx, vy, f'wl{k}')
                for k, (vx, vy) in enumerate(a.get("right", [])):
                    check(vx, vy, f'wr{k}')
                for k, (vx, vy) in enumerate(a.get("lights", [])):
                    check(vx, vy, f'wc{k}')
            elif t == "sync_click":
                for k, (cx, cy, bx, by) in enumerate(a.get("punti", [])):
                    check(cx, cy, f'sc{k}')
                    check(bx, by, f'sb{k}')
            elif t in ("yolo_drag", "yolo_drag_all"):
                check(a["end_rx"], a["end_ry"], 'e')
                for k, (vx, vy) in enumerate(a.get("roi_poly", [])):
                    check(vx, vy, f'yr{k}')
            elif t in ("yolo_click", "yolo_click_all", "yolo_drag_seq"):
                for k, (vx, vy) in enumerate(a.get("roi_poly", [])):
                    check(vx, vy, f'yr{k}')
            elif t == "click_until":
                for k, (cx, cy, bx, by) in enumerate(a.get("punti", [])):
                    check(cx, cy, f'uc{k}')
                    check(bx, by, f'ub{k}')
            elif t == "simon_says":
                for k, (cx, cy) in enumerate(a.get("display", [])):
                    check(cx, cy, f'sd{k}')
                for k, (bx, by) in enumerate(a.get("keypad", [])):
                    check(bx, by, f'sk{k}')
            elif t == "click_anomaly":
                for k, p_list in enumerate(a.get("punti", [])):
                    if len(p_list) == 4:
                        cx, cy, bx, by = p_list
                        check(cx, cy, f'ac{k}')
                        check(bx, by, f'ab{k}')
                    elif len(p_list) == 2:
                        cx, cy = p_list
                        check(cx, cy, f'ac{k}')
            elif t == "number_match":
                for k, btn in enumerate(a.get("buttons", [])):
                    r = btn["rect"]
                    check(r[0], r[1], f'nm{k}_1')
                    check(r[2], r[3], f'nm{k}_2')
            elif t == "ocr_keypad":
                for k, (vx, vy) in enumerate(a.get("roi_poly", [])):
                    check(vx, vy, f'okp{k}')
                for k, (vx, vy) in enumerate(a.get("keypad", [])):
                    check(vx, vy, f'okk{k}')

        return best[0], best[1]

    def _muovi_vertice(self, idx, key, rx, ry):
        if idx < 0 or idx >= len(self.azioni):
            return
        a = self.azioni[idx]
        t = a.get("tipo")
        if t == "click" and key == 'c':
            a["rx"] = rx; a["ry"] = ry
        elif t == "click_rect":
            r = a["rect"]
            if key == 'r1':
                r[0] = rx; r[1] = ry
            elif key == 'r2':
                r[2] = rx; r[3] = ry
        elif t == "click_poly" and key and key.startswith('p'):
            try:
                k = int(key[1:])
                a["poly"][k] = [rx, ry]
            except (ValueError, IndexError):
                pass
        elif t in ("drag", "drag_hold"):
            if key == 's':
                a["start_rx"] = rx; a["start_ry"] = ry
            elif key == 'e':
                a["end_rx"]   = rx; a["end_ry"]   = ry
        elif t == "drag_multi" and key and key.startswith('m'):
            try:
                k = int(key[1:])
                a["punti"][k] = [rx, ry]
            except (ValueError, IndexError):
                pass
        elif t == "drag_zone" and key:
            try:
                if key.startswith('a'):
                    k = int(key[1:])
                    a["zone_a"][k] = [rx, ry]
                elif key.startswith('b'):
                    k = int(key[1:])
                    a["zone_b"][k] = [rx, ry]
            except (ValueError, IndexError):
                pass
        elif t == "wiring" and key:
            try:
                if key.startswith('wl'):
                    k = int(key[2:])
                    a["left"][k] = [rx, ry]
                elif key.startswith('wr'):
                    k = int(key[2:])
                    a["right"][k] = [rx, ry]
                elif key.startswith('wc'):
                    k = int(key[2:])
                    a["lights"][k] = [rx, ry]
            except (ValueError, IndexError):
                pass
        elif t == "sync_click" and key:
            try:
                if key.startswith('sc'):
                    k = int(key[2:])
                    a["punti"][k] = [rx, ry, a["punti"][k][2], a["punti"][k][3]]
                elif key.startswith('sb'):
                    k = int(key[2:])
                    a["punti"][k] = [a["punti"][k][0], a["punti"][k][1], rx, ry]
            except (ValueError, IndexError):
                pass
        elif t in ("yolo_drag", "yolo_drag_all", "yolo_click", "yolo_click_all", "yolo_drag_seq"):
            if key == 'e' and t in ("yolo_drag", "yolo_drag_all"):
                a["end_rx"] = rx; a["end_ry"] = ry
            elif key and key.startswith('yr'):
                try:
                    k = int(key[2:])
                    a["roi_poly"][k] = [rx, ry]
                except (ValueError, IndexError):
                    pass
        elif t == "click_until" and key:
            try:
                if key.startswith('uc'):
                    k = int(key[2:])
                    a["punti"][k] = [rx, ry, a["punti"][k][2], a["punti"][k][3]]
                elif key.startswith('ub'):
                    k = int(key[2:])
                    a["punti"][k] = [a["punti"][k][0], a["punti"][k][1], rx, ry]
            except (ValueError, IndexError):
                pass
        elif t == "simon_says" and key:
            try:
                if key.startswith('sd'):
                    k = int(key[2:])
                    a["display"][k] = [rx, ry]
                elif key.startswith('sk'):
                    k = int(key[2:])
                    a["keypad"][k] = [rx, ry]
            except (ValueError, IndexError):
                pass
        elif t == "click_anomaly" and key:
            try:
                if key.startswith('ac'):
                    k = int(key[2:])
                    a["punti"][k] = [rx, ry, a["punti"][k][2], a["punti"][k][3]]
                elif key.startswith('ab'):
                    k = int(key[2:])
                    a["punti"][k] = [a["punti"][k][0], a["punti"][k][1], rx, ry]
            except (ValueError, IndexError):
                pass
        elif t == "number_match" and key and key.startswith('nm'):
            try:
                parts = key[2:].split('_')
                k = int(parts[0])
                corner = int(parts[1])
                r = a["buttons"][k]["rect"]
                if corner == 1:
                    r[0] = rx; r[1] = ry
                else:
                    r[2] = rx; r[3] = ry
            except Exception:
                pass
        elif t == "ocr_keypad" and key:
            try:
                if key.startswith('okp'):
                    k = int(key[3:])
                    a["roi_poly"][k] = [rx, ry]
                elif key.startswith('okk'):
                    k = int(key[3:])
                    a["keypad"][k] = [rx, ry]
            except Exception:
                pass

    def _aggiorna_pannello_selezione(self):
        if not dpg.does_item_exist("tae_sel_info"):
            return
        if self.sel_idx < 0 or self.sel_idx >= len(self.azioni):
            dpg.set_value("tae_sel_info", "— nessuna azione selezionata —")
            dpg.configure_item("tae_sel_info", color=(150, 150, 150))
            # Nascondi il gruppo di modifica tempi: non c'è nulla su cui agire
            if dpg.does_item_exist(self.TAG_EDIT_GROUP):
                dpg.configure_item(self.TAG_EDIT_GROUP, show=False)
        else:
            a = self.azioni[self.sel_idx]
            dpg.set_value("tae_sel_info",
                          f"#{self.sel_idx + 1}: {self._descr_azione(a)}")
            dpg.configure_item("tae_sel_info", color=(255, 200, 0))
            # Pre-compila i campi tempi con i valori correnti dell'azione
            # selezionata, così l'utente vede subito cosa sta modificando.
            if dpg.does_item_exist(self.TAG_EDIT_DUR):
                dpg.set_value(self.TAG_EDIT_DUR, float(a.get("durata", 0.0)))
            if dpg.does_item_exist(self.TAG_EDIT_PAUSE):
                dpg.set_value(self.TAG_EDIT_PAUSE, float(a.get("attesa", 0.0)))
            if dpg.does_item_exist(self.TAG_EDIT_HOLD):
                dpg.set_value(self.TAG_EDIT_HOLD, float(a.get("hold", 0.0)))
            if dpg.does_item_exist(self.TAG_EDIT_GROUP):
                dpg.configure_item(self.TAG_EDIT_GROUP, show=True)

    def _applica_tempi_selezione(self, *_):
        """
        Aggiorna durata e attesa dell'azione selezionata senza toccarne la
        geometria. Scritto come operazione in-place sulla lista azioni:
        nessun pop/re-draw, nessun cambio di sel_idx.
        """
        if self.sel_idx < 0 or self.sel_idx >= len(self.azioni):
            self._imposta_istruzioni("Seleziona prima un'azione.", (255, 150, 100))
            return
        dur_nuova   = max(0.0, float(dpg.get_value(self.TAG_EDIT_DUR)))
        pausa_nuova = max(0.0, float(dpg.get_value(self.TAG_EDIT_PAUSE)))
        self.azioni[self.sel_idx]["durata"] = dur_nuova
        self.azioni[self.sel_idx]["attesa"] = pausa_nuova
        _az = self.azioni[self.sel_idx]
        if _az.get("tipo") == "drag_hold" and dpg.does_item_exist(self.TAG_EDIT_HOLD):
            _az["hold"] = max(0.0, float(dpg.get_value(self.TAG_EDIT_HOLD)))
        _h = (f", H={_az['hold']:.2f}s" if _az.get("tipo") == "drag_hold" else "")
        self._imposta_istruzioni(
            f"#{self.sel_idx + 1}: tempi aggiornati (D={dur_nuova:.2f}s{_h}, P={pausa_nuova:.2f}s)",
            (150, 255, 150))
        # La lista mostra i tempi per ogni azione: basta ridisegnarla.
        self.aggiorna_lista()

    # ======================= MODIFICA / ELIMINA SELEZIONE =======================

    def _elimina_selezione(self, *_):
        if self.sel_idx < 0 or self.sel_idx >= len(self.azioni):
            self._imposta_istruzioni("Nessuna azione selezionata.", (255, 150, 100))
            return
        rimossa = self.azioni.pop(self.sel_idx)
        self._imposta_istruzioni(
            f"Eliminata: {self._descr_azione(rimossa)}", (255, 150, 100))
        self.sel_idx = -1
        self._aggiorna_pannello_selezione()
        self.aggiorna_lista()
        self.aggiorna_preview()

    def _on_key_delete(self, *_):
        if not self.e_aperto():
            return
        if self.sel_idx < 0:
            return
        self._elimina_selezione()

    def _modifica_selezione(self, *_):
        if self.sel_idx < 0 or self.sel_idx >= len(self.azioni):
            self._imposta_istruzioni("Nessuna azione selezionata.", (255, 150, 100))
            return
        a = self.azioni.pop(self.sel_idx)
        self.sel_idx = -1
        
        if dpg.does_item_exist(self.TAG_IN_DUR):
            dpg.set_value(self.TAG_IN_DUR, a.get("durata", 0.2))
        if dpg.does_item_exist(self.TAG_IN_PAUSE):
            dpg.set_value(self.TAG_IN_PAUSE, a.get("attesa", 0.5))
            
        tipo = a.get("tipo")
        if tipo == "click":
            self._avvia(self.WAIT_CLICK,
                        "MODIFICA: CLICK sulla preview per nuovo punto.", (0, 255, 0))
        elif tipo == "drag":
            self._avvia(self.WAIT_DRAG_START,
                        "MODIFICA: CLICK sulla preview per PARTENZA drag.", (255, 200, 0))
        elif tipo == "click_rect":
            self._avvia_rect_click()
            self._imposta_istruzioni(
                "MODIFICA: trascina sulla PREVIEW per il nuovo rettangolo.",
                (180, 255, 180))
        elif tipo == "click_poly":
            self._avvia_poly_click()
            self._imposta_istruzioni(
                "MODIFICA: CLICK per nuovi vertici, poi CHIUDI PUNTI.",
                (200, 180, 255))
        elif tipo == "drag_multi":
            self._avvia_multi()
            self._imposta_istruzioni(
                "MODIFICA: CLICK per nuovi punti (>=2), poi CHIUDI PUNTI.",
                (255, 180, 100))
        elif tipo == "drag_hold":
            self._avvia_drag_hold()
            self._imposta_istruzioni(
                "MODIFICA: CLICK per nuova PARTENZA, poi CLICK per nuovo ARRIVO.",
                (255, 140, 180))
        elif tipo == "drag_zone":
            self._avvia_drag_zone()
            self._imposta_istruzioni(
                "MODIFICA: ridisegna ZONA A, poi ZONA B.", (255, 150, 200))
        elif tipo == "wiring":
            self._avvia_wiring()
            self._imposta_istruzioni("MODIFICA: Ridisegna intero Fix Wiring.", (200, 255, 100))
        elif tipo == "sync_click":
            self._avvia_sync_click()
            self._imposta_istruzioni("MODIFICA: Ridisegna intero Sync Click.", (200, 255, 100))
        elif tipo == "yolo_drag":
            self._tmp_yolo_model = a.get("yolo_model")
            self.stato = self.WAIT_YOLO_POLY
            self.buffer_punti = []
            self.buffer_zone_a = []
            self._imposta_istruzioni(f"MODIFICA YOLO '{self._tmp_yolo_model}': Ridisegna ZONA DI RICERCA, poi CHIUDI PUNTI.", (255, 100, 255))
        elif tipo == "yolo_drag_all":
            self._tmp_yolo_model = a.get("yolo_model")
            self.stato = self.WAIT_YOLO_ALL_POLY
            self.buffer_punti = []
            self.buffer_zone_a = []
            self._imposta_istruzioni(f"MODIFICA ALL YOLO '{self._tmp_yolo_model}': Ridisegna ZONA DI RICERCA, poi CHIUDI PUNTI.", (255, 150, 50))
        elif tipo == "yolo_click":
            self._tmp_yolo_model = a.get("yolo_model")
            self.stato = self.WAIT_YOLO_CLICK_POLY
            self.buffer_punti = []
            self.buffer_zone_a = []
            self._imposta_istruzioni(f"MODIFICA YOLO CLICK '{self._tmp_yolo_model}': Ridisegna ZONA DI RICERCA, poi CHIUDI PUNTI.", (100, 255, 100))
        elif tipo == "yolo_click_all":
            self._tmp_yolo_model = a.get("yolo_model")
            self.stato = self.WAIT_YOLO_CLICK_ALL_POLY
            self.buffer_punti = []
            self.buffer_zone_a = []
            self._imposta_istruzioni(f"MODIFICA ALL YOLO CLICK '{self._tmp_yolo_model}': Ridisegna ZONA DI RICERCA, poi CHIUDI PUNTI.", (100, 255, 150))
        elif tipo == "yolo_drag_seq":
            self._tmp_yolo_model = a.get("yolo_model")
            self.stato = self.WAIT_YOLO_SEQ_POLY
            self.buffer_punti = []
            self.buffer_zone_a = []
            self._imposta_istruzioni(f"MODIFICA SEQ YOLO '{self._tmp_yolo_model}': Ridisegna ZONA DI RICERCA, poi CHIUDI PUNTI.", (255, 120, 200))
        elif tipo == "click_until":
            self._avvia_click_until()
            self._imposta_istruzioni("MODIFICA: Ridisegna intero Click Until.", (200, 255, 255))
        elif tipo == "click_anomaly":
            self._avvia_anomaly_click()
            self._imposta_istruzioni("MODIFICA: Ridisegna intera Anomalia (>=3 coppie).", (255, 100, 200))
        elif tipo == "number_match":
            self._avvia_num_match()
            self._imposta_istruzioni("MODIFICA: Ridisegna intera griglia Number Match.", (100, 255, 255))
        elif tipo == "ocr_keypad":
            self.stato = self.WAIT_OCR_POLY
            self.buffer_punti = []
            self.buffer_keypad = []
            self._imposta_istruzioni("MODIFICA: Ridisegna ZONA SCHERMO (poly), poi i 10 tasti.", (100, 255, 200))
        self._aggiorna_pannello_selezione()
        self.aggiorna_lista()
        self.aggiorna_preview()

    def _segui_mouse_rect(self):
        if not _WIN_OK:
            return
        time.sleep(0.02)
        while self.rect_drag_active:
            lmb = (win32api.GetAsyncKeyState(win32con.VK_LBUTTON) & 0x8000) != 0
            if not lmb:
                break
            try:
                pos = dpg.get_drawing_mouse_pos()
                rx = max(0.0, min(1.0, pos[0] / max(1, self.preview_w)))
                ry = max(0.0, min(1.0, pos[1] / max(1, self.preview_h)))
                self.rect_end = (rx, ry)
            except Exception:
                pass
            time.sleep(0.015)

        if self.rect_start and self.rect_end:
            x1, y1 = self.rect_start
            x2, y2 = self.rect_end
            if abs(x2 - x1) > 0.005 and abs(y2 - y1) > 0.005:
                if self.stato == "WAIT_RECT_ON_CANVAS":
                    durata = dpg.get_value(self.TAG_IN_DUR)
                    attesa = dpg.get_value(self.TAG_IN_PAUSE)
                    self.azioni.append({
                        "tipo":   "click_rect",
                        "rect":   [x1, y1, x2, y2],
                        "durata": durata,
                        "attesa": attesa,
                    })
                    self._imposta_istruzioni("Click-rect aggiunto.")
                elif self.stato == self.WAIT_NUM_MATCH_RECT:
                    hwnd = win32gui.FindWindow(None, dpg.get_value(self.TAG_IN_WIN_NAME))
                    rect = get_client_rect(hwnd)
                    if rect:
                        cx, cy, cw, ch = rect
                        px1, py1 = int(min(x1, x2)*cw), int(min(y1, y2)*ch)
                        px2, py2 = int(max(x1, x2)*cw), int(max(y1, y2)*ch)
                        ax1, ay1 = cx + px1, cy + py1
                        ax2, ay2 = cx + px2, cy + py2
                        try:
                            import mss
                            import cv2
                            import numpy as np
                            with mss.mss() as sct:
                                img = np.array(sct.grab({"left": ax1, "top": ay1, "width": ax2-ax1, "height": ay2-ay1}))
                                shape_blurred = _extract_pure_shape(img)
                                self.buffer_num_match.append({
                                    "rect": [x1, y1, x2, y2],
                                    "template": shape_blurred.flatten().tolist()
                                })
                                self._imposta_istruzioni(f"Numero {len(self.buffer_num_match)} salvato. Trascina prossimo o CHIUDI PUNTI.", (100, 255, 255))
                        except Exception as e:
                            print("[Number Match] Errore salvataggio template:", e)
            else:
                if self.stato == "WAIT_RECT_ON_CANVAS":
                    self._imposta_istruzioni("Rettangolo troppo piccolo, annullato.", (255, 150, 100))
        self.rect_drag_active = False
        if self.stato == "WAIT_RECT_ON_CANVAS":
            self._reset_stato()
        else:
            self.rect_start = None
            self.rect_end = None
        try:
            self.aggiorna_lista()
            self.aggiorna_preview()
        except Exception:
            pass

    # ======================= SALVA / TEST =======================

    def _salva_e_chiudi(self, *_):
        if self.id_task is None:
            self.chiudi(); return
        self.task_mgr.imposta_azioni(self.id_task, self.azioni)
        if self.on_save_cb:
            try:
                self.on_save_cb(self.id_task)
            except Exception as e:
                print(f"[TaskActionEditor] on_save_cb error: {e}")
        self.chiudi()

    def _avvia_test(self, *_):
        stop_flag.requested = False
        if not _WIN_OK:
            self._imposta_istruzioni("pyautogui/win32 non disponibili.", (255, 100, 100))
            return
        if not self.azioni:
            self._imposta_istruzioni("Nessuna azione da testare.", (255, 100, 100))
            return
        threading.Thread(target=self._esegui_test_thread, daemon=True).start()

    def _esegui_test_thread(self):
        nome_finestra = dpg.get_value(self.TAG_IN_WIN_NAME)
        hwnd = win32gui.FindWindow(None, nome_finestra)
        if not hwnd:
            return
        try:
            win32gui.SetForegroundWindow(hwnd)
            time.sleep(0.5)
        except Exception:
            pass
        esegui_azioni(self.azioni, hwnd, is_test=True)

