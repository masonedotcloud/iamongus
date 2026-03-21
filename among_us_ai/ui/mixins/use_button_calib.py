"""
Popup di calibrazione del pulsante Use di Among Us.

Flusso:
  1. Utente apre Strumenti -> Calibra pulsante Use
  2. Si apre un popup con istruzioni
  3. Utente seleziona la ROI usando 4 input numerici (rx, ry, rw, rh)
     OPPURE clicca "Anteprima ROI" per vedere lo screenshot
  4. Utente posiziona l'avatar in un punto SENZA task interagibili
     (nessun pulsante illuminato), preme "Cattura SPENTO"
  5. Utente posiziona l'avatar VICINO a una task (pulsante illuminato),
     preme "Cattura ACCESO"
  6. Salva: scrive `use_button_calibration.json`

Una volta calibrato, il bot usa questa info in `_do_arrival_nudge`
per decidere se serve micro-nudge (vedi auto_move.py).
"""

from ._imports import *
from ...execution import use_button


class UseButtonCalibMixin:
    """Mixin con i metodi di calibrazione pulsante Use."""

    def _apri_popup_calibra_use_button(self):
        """Apre il popup di calibrazione pulsante Use."""
        tag = "popup_calibra_use"
        # Verifica se l'elemento DPG e' gia' stato creato
        if dpg.does_item_exist(tag):
            dpg.delete_item(tag)

        # Carica calibrazione corrente (default vuota)
        calib = use_button.carica_calibrazione()
        roi = calib.get('roi', {'rx': 0.92, 'ry': 0.85, 'rw': 0.07, 'rh': 0.12})

        vp_w = dpg.get_viewport_client_width()
        vp_h = dpg.get_viewport_client_height()
        win_w, win_h = 480, 480

        with dpg.window(label="Calibra pulsante Use",
                        tag=tag,
                        modal=True,
                        no_close=False,
                        width=win_w, height=win_h,
                        pos=((vp_w - win_w) // 2, (vp_h - win_h) // 2)):

            dpg.add_text("Calibrazione del pulsante 'Use' di Among Us",
                         color=Colors.ACCENT)
            dpg.add_separator()
            dpg.add_text("Aiuta il bot a capire quando puo' interagire con")
            dpg.add_text("una task. Il pulsante si ILLUMINA quando sei nel")
            dpg.add_text("raggio di interazione di un oggetto.", wrap=420)
            dpg.add_separator()

            # ROI rx, ry, rw, rh (in coordinate relative al client del gioco)
            dpg.add_text("1) ROI del pulsante (rect relativo al client):",
                         color=(180, 220, 255))
            with dpg.group(horizontal=True):
                dpg.add_text("rx:")
                dpg.add_input_float(tag="cu_rx",
                                    default_value=float(roi.get('rx', 0.92)),
                                    width=80, step=0.01, format="%.3f",
                                    min_value=0.0, max_value=1.0,
                                    min_clamped=True, max_clamped=True)
                dpg.add_text("ry:")
                dpg.add_input_float(tag="cu_ry",
                                    default_value=float(roi.get('ry', 0.85)),
                                    width=80, step=0.01, format="%.3f",
                                    min_value=0.0, max_value=1.0,
                                    min_clamped=True, max_clamped=True)
            with dpg.group(horizontal=True):
                dpg.add_text("rw:")
                dpg.add_input_float(tag="cu_rw",
                                    default_value=float(roi.get('rw', 0.07)),
                                    width=80, step=0.01, format="%.3f",
                                    min_value=0.01, max_value=1.0,
                                    min_clamped=True, max_clamped=True)
                dpg.add_text("rh:")
                dpg.add_input_float(tag="cu_rh",
                                    default_value=float(roi.get('rh', 0.12)),
                                    width=80, step=0.01, format="%.3f",
                                    min_value=0.01, max_value=1.0,
                                    min_clamped=True, max_clamped=True)

            dpg.add_text("(Default e' angolo basso-destra, regola se serve)",
                         color=Colors.TEXT_DIM)

            # Bottone per la selezione VISUALE della ROI (drag su screenshot)
            dpg.add_button(label="[ Seleziona dal vivo con il mouse ]",
                           width=-1, height=28,
                           callback=lambda *a: self._apri_popup_seleziona_roi_visuale())
            dpg.add_separator()

            # Pulsanti di cattura
            dpg.add_text("2) Cattura i 2 stati di riferimento:",
                         color=(180, 220, 255))
            dpg.add_text("- Posiziona l'avatar dove il pulsante e' SPENTO")
            dpg.add_text("  (lontano da ogni task), poi premi:")

            with dpg.group(horizontal=True):
                dpg.add_button(label="[ Cattura SPENTO ]", width=160,
                               callback=lambda *a: self._cattura_use_button_state('off'))
                dpg.add_text("brightness:", color=Colors.TEXT_DIM)
                dpg.add_text("--",
                             tag="cu_off_val",
                             color=Colors.TEXT_DIM)

            dpg.add_text("- Posiziona l'avatar VICINO a una task (pulsante")
            dpg.add_text("  illuminato), poi premi:")

            with dpg.group(horizontal=True):
                dpg.add_button(label="[ Cattura ACCESO ]", width=160,
                               callback=lambda *a: self._cattura_use_button_state('on'))
                dpg.add_text("brightness:", color=Colors.TEXT_DIM)
                dpg.add_text("--",
                             tag="cu_lit_val",
                             color=Colors.TEXT_DIM)

            # Pre-popola i valori dalla calibrazione corrente, se presenti
            if calib.get('off_brightness') is not None:
                dpg.set_value("cu_off_val", f"{calib['off_brightness']:.1f}")
            if calib.get('lit_brightness') is not None:
                dpg.set_value("cu_lit_val", f"{calib['lit_brightness']:.1f}")

            dpg.add_separator()

            # Stato calibrazione
            stato = "[OK] Calibrato" if calib.get('calibrated') else "[!] Non calibrato"
            stato_col = (60, 200, 60) if calib.get('calibrated') else (220, 180, 60)
            dpg.add_text(stato, tag="cu_stato", color=stato_col)

            dpg.add_separator()
            with dpg.group(horizontal=True):
                dpg.add_button(label="[ Salva ]", width=110,
                               callback=lambda *a: self._salva_use_button_calib())
                dpg.add_button(label="[ Annulla ]", width=110,
                               callback=lambda *a: dpg.delete_item(tag))
                dpg.add_button(label="[ Reset ]", width=110,
                               callback=lambda *a: self._reset_use_button_calib())

    def _cattura_use_button_state(self, stato):
        """
        Cattura la luminosita' della ROI corrente (rx, ry, rw, rh dai
        4 input del popup) e la salva come riferimento `stato`
        ('off' o 'on').
        """
        # Trova il client rect del gioco
        try:
            hwnd = win32gui.FindWindow(None, "Among Us")
            if not hwnd:
                self.auto_status_msg = "Finestra Among Us non trovata"
                return
            rect = win32gui.GetClientRect(hwnd)
            pt = win32gui.ClientToScreen(hwnd, (rect[0], rect[1]))
            cx_s, cy_s = pt
            cw_s, ch_s = rect[2], rect[3]
        except Exception as e:
            self.auto_status_msg = f"Errore lettura finestra: {e}"
            return

        # Costruisci la calibrazione "temporanea" con la ROI dei 4 input
        roi = {
            'rx': dpg.get_value("cu_rx"),
            'ry': dpg.get_value("cu_ry"),
            'rw': dpg.get_value("cu_rw"),
            'rh': dpg.get_value("cu_rh"),
        }
        calib_tmp = {'roi': roi}

        # Cattura luminosita'
        bright = use_button.cattura_roi_luminosita(
            (cx_s, cy_s, cw_s, ch_s), calib_tmp,
        )
        if bright is None:
            self.auto_status_msg = "Errore cattura ROI"
            return

        # Aggiorna il widget testuale
        if stato == 'off':
            dpg.set_value("cu_off_val", f"{bright:.1f}")
            self.auto_status_msg = f"Catturato SPENTO: brightness={bright:.1f}"
        else:
            dpg.set_value("cu_lit_val", f"{bright:.1f}")
            self.auto_status_msg = f"Catturato ACCESO: brightness={bright:.1f}"

    def _salva_use_button_calib(self):
        """Salva la calibrazione su disco e chiude il popup."""
        try:
            off_str = dpg.get_value("cu_off_val")
            lit_str = dpg.get_value("cu_lit_val")
            off_v = float(off_str) if off_str and off_str != "--" else None
            lit_v = float(lit_str) if lit_str and lit_str != "--" else None
        except (ValueError, TypeError):
            self.auto_status_msg = "Valori brightness non validi"
            return

        if off_v is None or lit_v is None:
            self.auto_status_msg = ("Cattura entrambi gli stati "
                                    "(SPENTO e ACCESO) prima di salvare.")
            return

        # Sanity check: lit deve essere significativamente piu' luminoso
        if lit_v <= off_v + 5:
            self.auto_status_msg = ("ATTENZIONE: ACCESO non e' piu' luminoso "
                                    "di SPENTO. Verifica la calibrazione.")
            return

        calib = {
            'roi': {
                'rx': dpg.get_value("cu_rx"),
                'ry': dpg.get_value("cu_ry"),
                'rw': dpg.get_value("cu_rw"),
                'rh': dpg.get_value("cu_rh"),
            },
            'off_brightness': off_v,
            'lit_brightness': lit_v,
            'calibrated': True,
        }
        if use_button.salva_calibrazione(calib):
            self.auto_status_msg = (f"Calibrazione salvata: "
                                    f"off={off_v:.1f}, lit={lit_v:.1f}")
            if dpg.does_item_exist("popup_calibra_use"):
                dpg.delete_item("popup_calibra_use")
        else:
            self.auto_status_msg = "Errore salvataggio calibrazione"

    def _reset_use_button_calib(self):
        """Resetta la calibrazione (cancella il file)."""
        import os
        try:
            if os.path.exists(use_button.CALIB_PATH):
                os.remove(use_button.CALIB_PATH)
            self.auto_status_msg = "Calibrazione pulsante Use resettata"
            if dpg.does_item_exist("popup_calibra_use"):
                dpg.delete_item("popup_calibra_use")
        except OSError as e:
            self.auto_status_msg = f"Errore reset: {e}"

    # ============================================================
    #  SELEZIONE VISUALE DELLA ROI: l'utente vede lo screenshot
    #  della finestra del gioco e disegna un rettangolo con 2 click.
    # ============================================================

    def _apri_popup_seleziona_roi_visuale(self):
        """
        Apre un popup secondario con lo screenshot della finestra del
        gioco. L'utente seleziona la ROI con DUE CLICK:
          - 1° click: angolo top-left
          - 2° click: angolo bottom-right
        Il rettangolo viene disegnato in tempo reale. Cliccando
        "Conferma" le coordinate (rx, ry, rw, rh) vengono propagate
        agli input numerici del popup principale.

        Diagnostica: tutti i passaggi stampano log + mostrano errori
        nello status panel + (se popup aperto) in un widget testuale
        interno.
        """
        print("[ROI-Sel] Apro popup selezione visuale...", flush=True)

        # === STEP 1: import dipendenze ===
        try:
            import win32gui
            import mss
            import numpy as np
            import cv2
        except ImportError as e:
            msg = f"Modulo mancante per cattura: {e}"
            print(f"[ROI-Sel] ERRORE: {msg}", flush=True)
            self.auto_status_msg = msg
            return

        # === STEP 2: trova finestra del gioco ===
        try:
            hwnd = win32gui.FindWindow(None, "Among Us")
            print(f"[ROI-Sel] HWND Among Us = {hwnd}", flush=True)
            if not hwnd:
                msg = "Finestra Among Us non trovata"
                print(f"[ROI-Sel] ERRORE: {msg}", flush=True)
                self.auto_status_msg = msg
                return
            rect = win32gui.GetClientRect(hwnd)
            pt = win32gui.ClientToScreen(hwnd, (rect[0], rect[1]))
            cx_s, cy_s = pt
            cw_s, ch_s = rect[2], rect[3]
            print(f"[ROI-Sel] Client rect: pos=({cx_s},{cy_s}) "
                  f"size=({cw_s}x{ch_s})", flush=True)
            if cw_s <= 0 or ch_s <= 0:
                msg = "Finestra di gioco non valida (dimensioni 0)"
                print(f"[ROI-Sel] ERRORE: {msg}", flush=True)
                self.auto_status_msg = msg
                return
        except Exception as e:
            msg = f"Errore accesso finestra: {e}"
            print(f"[ROI-Sel] ERRORE: {msg}", flush=True)
            self.auto_status_msg = msg
            return

        # === STEP 3: cattura screenshot ===
        try:
            with mss.mss() as sct:
                monitor = {'top': cy_s, 'left': cx_s,
                           'width': cw_s, 'height': ch_s}
                shot = np.array(sct.grab(monitor))
            print(f"[ROI-Sel] Screenshot OK: {shot.shape}", flush=True)
        except Exception as e:
            msg = f"Errore cattura screenshot: {e}"
            print(f"[ROI-Sel] ERRORE: {msg}", flush=True)
            self.auto_status_msg = msg
            return

        # === STEP 4: conversione formato + ridimensionamento ===
        try:
            # BGRA -> RGBA per DPG
            rgba = cv2.cvtColor(shot, cv2.COLOR_BGRA2RGBA)
            h_img, w_img = rgba.shape[:2]

            # Limite preview (proporzionale alla viewport DPG)
            vp_w = dpg.get_viewport_client_width()
            vp_h = dpg.get_viewport_client_height()
            max_w = max(400, vp_w - 80)
            max_h = max(300, vp_h - 220)
            scale = min(max_w / w_img, max_h / h_img, 1.0)
            prev_w = int(w_img * scale)
            prev_h = int(h_img * scale)
            print(f"[ROI-Sel] Preview: {prev_w}x{prev_h} (scale={scale:.3f})",
                  flush=True)

            if scale < 1.0:
                rgba_resized = cv2.resize(rgba, (prev_w, prev_h),
                                          interpolation=cv2.INTER_AREA)
            else:
                rgba_resized = rgba

            # Texture DPG: float32 in [0, 1], ravel
            texture_data = (rgba_resized.astype(np.float32) / 255.0).ravel()
        except Exception as e:
            msg = f"Errore conversione immagine: {e}"
            print(f"[ROI-Sel] ERRORE: {msg}", flush=True)
            self.auto_status_msg = msg
            return

        # === STEP 5: stato per i callback ===
        self._roi_sel = {
            'client_w': cw_s,
            'client_h': ch_s,
            'preview_w': prev_w,
            'preview_h': prev_h,
            'scale': scale,
            'point1': None,
            'point2': None,
            'canvas_tag': None,  # popolato dopo
        }

        # === STEP 6: costruisco popup ===
        sel_tag = "popup_seleziona_roi"
        tex_tag = "popup_seleziona_roi_tex"
        canvas_tag = "popup_seleziona_roi_canvas"
        rect_tag = "popup_seleziona_roi_rect"
        info_tag = "popup_seleziona_roi_info"
        mouse_handler_tag = "popup_seleziona_roi_mouse_handler"

        # Cleanup eventuali residui di aperture precedenti
        for t in [sel_tag, mouse_handler_tag]:
            if dpg.does_item_exist(t):
                dpg.delete_item(t)
        if dpg.does_item_exist(tex_tag):
            dpg.delete_item(tex_tag)

        # Texture registry condiviso
        if not dpg.does_item_exist("ub_texture_registry"):
            with dpg.texture_registry(show=False, tag="ub_texture_registry"):
                pass

        try:
            dpg.add_dynamic_texture(width=prev_w, height=prev_h,
                                    default_value=texture_data,
                                    tag=tex_tag,
                                    parent="ub_texture_registry")
            print(f"[ROI-Sel] Texture creata: {tex_tag}", flush=True)
        except Exception as e:
            msg = f"Errore creazione texture: {e}"
            print(f"[ROI-Sel] ERRORE: {msg}", flush=True)
            self.auto_status_msg = msg
            return

        win_w = prev_w + 40
        win_h = prev_h + 160

        # *** WORKAROUND MODAL SOPRA MODAL ***
        # DPG non gestisce bene un modal aperto sopra un altro modal:
        # il secondo viene creato ma non e' visibile / non riceve eventi.
        # Quindi:
        #   - Nascondiamo temporaneamente il popup principale ("popup_calibra_use")
        #   - Apriamo il secondo popup NON modale
        #   - Alla chiusura del secondo, riapriamo il principale
        if dpg.does_item_exist("popup_calibra_use"):
            try:
                dpg.configure_item("popup_calibra_use", show=False)
                print("[ROI-Sel] Popup principale nascosto temporaneamente",
                      flush=True)
            except Exception as e:
                print(f"[ROI-Sel] Warning hide popup principale: {e}",
                      flush=True)

        try:
            with dpg.window(label="Seleziona ROI del pulsante 'Use'",
                            tag=sel_tag,
                            modal=False,
                            no_close=False,
                            width=win_w, height=win_h,
                            pos=((vp_w - win_w) // 2, (vp_h - win_h) // 2),
                            on_close=lambda *a: self._chiudi_popup_roi_visuale()):
                dpg.add_text("Clicca DUE volte sull'immagine:",
                             color=Colors.ACCENT)
                dpg.add_text("  1° click = angolo in alto a sinistra del pulsante")
                dpg.add_text("  2° click = angolo in basso a destra del pulsante")
                dpg.add_text("Click successivi: ricominci dal 1° punto.",
                             color=Colors.TEXT_DIM)

                # Drawlist con la texture + livello per il rettangolo
                with dpg.drawlist(width=prev_w, height=prev_h, tag=canvas_tag):
                    dpg.draw_image(tex_tag, (0, 0), (prev_w, prev_h))
                    with dpg.draw_layer(tag=rect_tag):
                        pass

                dpg.add_text("Seleziona 2 punti...", tag=info_tag,
                             color=Colors.TEXT_DIM)

                with dpg.group(horizontal=True):
                    dpg.add_button(label="[ Conferma ]", width=110,
                                   callback=lambda *a: self._conferma_roi_visuale())
                    dpg.add_button(label="[ Resetta selezione ]", width=160,
                                   callback=lambda *a: self._reset_roi_visuale())
                    dpg.add_button(label="[ Annulla ]", width=110,
                                   callback=lambda *a: self._chiudi_popup_roi_visuale())
            print(f"[ROI-Sel] Popup creato OK (modal=False)", flush=True)
        except Exception as e:
            msg = f"Errore costruzione popup: {e}"
            print(f"[ROI-Sel] ERRORE: {msg}", flush=True)
            self.auto_status_msg = msg
            # Ripristina popup principale
            if dpg.does_item_exist("popup_calibra_use"):
                try:
                    dpg.configure_item("popup_calibra_use", show=True)
                except Exception:
                    pass
            return

        self._roi_sel['canvas_tag'] = canvas_tag

        # === STEP 7: handler mouse GLOBALE ===
        # Usiamo un handler_registry GLOBALE (non item_handler_registry sul
        # drawlist) perche' draw_list non sempre supporta item_clicked
        # in modo affidabile. Il callback controlla manualmente se il mouse
        # e' sopra il drawlist.
        try:
            if dpg.does_item_exist(mouse_handler_tag):
                dpg.delete_item(mouse_handler_tag)
            with dpg.handler_registry(tag=mouse_handler_tag):
                dpg.add_mouse_click_handler(
                    button=dpg.mvMouseButton_Left,
                    callback=self._roi_visuale_global_click,
                )
            print(f"[ROI-Sel] Mouse handler globale OK", flush=True)
        except Exception as e:
            msg = f"Errore handler mouse: {e}"
            print(f"[ROI-Sel] ERRORE: {msg}", flush=True)
            self.auto_status_msg = msg
            return

    def _chiudi_popup_roi_visuale(self):
        """
        Chiude il popup di selezione visuale, pulisce gli handler
        e riapre il popup principale di calibrazione (era stato
        nascosto temporaneamente).
        """
        sel_tag = "popup_seleziona_roi"
        mouse_handler_tag = "popup_seleziona_roi_mouse_handler"
        if dpg.does_item_exist(mouse_handler_tag):
            dpg.delete_item(mouse_handler_tag)
        if dpg.does_item_exist(sel_tag):
            dpg.delete_item(sel_tag)
        self._roi_sel = None
        # Riapri il popup principale di calibrazione
        if dpg.does_item_exist("popup_calibra_use"):
            try:
                dpg.configure_item("popup_calibra_use", show=True)
            except Exception:
                pass
        print("[ROI-Sel] Popup chiuso", flush=True)

    def _roi_visuale_global_click(self, sender, app_data, user_data):
        """
        Callback globale al click sinistro del mouse.

        Filtra: agisce solo se il mouse e' SOPRA il drawlist dello
        screenshot. Calcola la posizione click - drawlist_top_left
        per ottenere coordinate locali alla preview.
        """
        if not hasattr(self, '_roi_sel') or self._roi_sel is None:
            return
        canvas_tag = self._roi_sel.get('canvas_tag')
        if not canvas_tag or not dpg.does_item_exist(canvas_tag):
            return
        # Click solo se hover sul drawlist (esclude bottoni e text)
        try:
            if not dpg.is_item_hovered(canvas_tag):
                return
        except Exception:
            return

        # Posizione mouse: prendo "drawing_mouse_pos" se disponibile
        # (gestisce nativamente il sistema di coordinate del drawlist),
        # altrimenti calcolo a mano (mouse_pos globale - drawlist_top_left).
        mx, my = None, None
        try:
            # Funziona se il drawlist e' "focused" - cioe' il mouse e' sopra
            dmp = dpg.get_drawing_mouse_pos()
            mx, my = float(dmp[0]), float(dmp[1])
        except Exception:
            mx, my = None, None

        if mx is None or my is None:
            # Fallback: mouse globale - rect_min del drawlist
            try:
                gx, gy = dpg.get_mouse_pos(local=False)
                rmin = dpg.get_item_rect_min(canvas_tag)
                mx = float(gx) - float(rmin[0])
                my = float(gy) - float(rmin[1])
            except Exception as e:
                print(f"[ROI-Sel] Errore coord mouse: {e}", flush=True)
                return

        prev_w = self._roi_sel['preview_w']
        prev_h = self._roi_sel['preview_h']

        # Clamp dentro la preview
        mx = max(0, min(prev_w, int(mx)))
        my = max(0, min(prev_h, int(my)))

        print(f"[ROI-Sel] Click rilevato a ({mx}, {my})", flush=True)

        rect_tag = "popup_seleziona_roi_rect"
        info_tag = "popup_seleziona_roi_info"

        # Logica di gestione click
        if self._roi_sel['point1'] is None:
            self._roi_sel['point1'] = (mx, my)
            self._roi_sel['point2'] = None
            if dpg.does_item_exist(rect_tag):
                dpg.delete_item(rect_tag, children_only=True)
            dpg.draw_circle((mx, my), 5,
                            color=(100, 255, 100, 255),
                            fill=(100, 255, 100, 180),
                            parent=rect_tag)
            if dpg.does_item_exist(info_tag):
                dpg.set_value(info_tag,
                              f"Primo punto: ({mx}, {my}). "
                              f"Clicca ora l'angolo in basso a destra.")
        elif self._roi_sel['point2'] is None:
            self._roi_sel['point2'] = (mx, my)
            x1, y1 = self._roi_sel['point1']
            x2, y2 = mx, my
            xa, xb = min(x1, x2), max(x1, x2)
            ya, yb = min(y1, y2), max(y1, y2)
            if dpg.does_item_exist(rect_tag):
                dpg.delete_item(rect_tag, children_only=True)
            dpg.draw_rectangle((xa, ya), (xb, yb),
                               color=(100, 255, 100, 255),
                               thickness=2,
                               fill=(100, 255, 100, 50),
                               parent=rect_tag)
            client_w = self._roi_sel['client_w']
            client_h = self._roi_sel['client_h']
            scale = self._roi_sel['scale']
            cw_xa = xa / scale
            cw_ya = ya / scale
            cw_xb = xb / scale
            cw_yb = yb / scale
            rx = cw_xa / client_w
            ry = cw_ya / client_h
            rw = (cw_xb - cw_xa) / client_w
            rh = (cw_yb - cw_ya) / client_h
            if dpg.does_item_exist(info_tag):
                dpg.set_value(info_tag,
                              f"ROI: rx={rx:.3f}, ry={ry:.3f}, "
                              f"rw={rw:.3f}, rh={rh:.3f} - "
                              f"'Conferma' per applicare")
        else:
            # Ricomincio
            self._roi_sel['point1'] = (mx, my)
            self._roi_sel['point2'] = None
            if dpg.does_item_exist(rect_tag):
                dpg.delete_item(rect_tag, children_only=True)
            dpg.draw_circle((mx, my), 5,
                            color=(100, 255, 100, 255),
                            fill=(100, 255, 100, 180),
                            parent=rect_tag)
            if dpg.does_item_exist(info_tag):
                dpg.set_value(info_tag,
                              f"Primo punto: ({mx}, {my}). "
                              f"Clicca ora l'angolo in basso a destra.")

    def _reset_roi_visuale(self):
        """Resetta la selezione: cancella punti e disegni."""
        if hasattr(self, '_roi_sel') and self._roi_sel:
            self._roi_sel['point1'] = None
            self._roi_sel['point2'] = None
        rect_tag = "popup_seleziona_roi_rect"
        info_tag = "popup_seleziona_roi_info"
        if dpg.does_item_exist(rect_tag):
            dpg.delete_item(rect_tag, children_only=True)
        if dpg.does_item_exist(info_tag):
            dpg.set_value(info_tag, "Seleziona 2 punti...")

    def _conferma_roi_visuale(self):
        """
        Calcola rx, ry, rw, rh dai 2 punti selezionati e li scrive
        negli input numerici del popup principale.
        """
        if (not hasattr(self, '_roi_sel') or not self._roi_sel
                or self._roi_sel.get('point1') is None
                or self._roi_sel.get('point2') is None):
            self.auto_status_msg = "Seleziona prima 2 punti sull'immagine"
            return

        x1, y1 = self._roi_sel['point1']
        x2, y2 = self._roi_sel['point2']
        xa, xb = min(x1, x2), max(x1, x2)
        ya, yb = min(y1, y2), max(y1, y2)

        if xb - xa < 5 or yb - ya < 5:
            self.auto_status_msg = ("Selezione troppo piccola "
                                    "(< 5 px). Riprova.")
            return

        client_w = self._roi_sel['client_w']
        client_h = self._roi_sel['client_h']
        scale = self._roi_sel['scale']
        # Riporto dalle coord preview a quelle del client
        cw_xa = xa / scale
        cw_ya = ya / scale
        cw_xb = xb / scale
        cw_yb = yb / scale
        rx = cw_xa / client_w
        ry = cw_ya / client_h
        rw = (cw_xb - cw_xa) / client_w
        rh = (cw_yb - cw_ya) / client_h

        # Aggiorno gli input numerici nel popup principale
        if dpg.does_item_exist("cu_rx"):
            dpg.set_value("cu_rx", round(rx, 3))
            dpg.set_value("cu_ry", round(ry, 3))
            dpg.set_value("cu_rw", round(rw, 3))
            dpg.set_value("cu_rh", round(rh, 3))

        # Chiudo il popup di selezione + pulisco mouse handler
        sel_tag = "popup_seleziona_roi"
        mouse_handler_tag = "popup_seleziona_roi_mouse_handler"
        if dpg.does_item_exist(mouse_handler_tag):
            dpg.delete_item(mouse_handler_tag)
        if dpg.does_item_exist(sel_tag):
            dpg.delete_item(sel_tag)

        # Pulizia stato
        self._roi_sel = None

        # Riapri il popup principale di calibrazione
        if dpg.does_item_exist("popup_calibra_use"):
            try:
                dpg.configure_item("popup_calibra_use", show=True)
            except Exception:
                pass

        self.auto_status_msg = (f"ROI applicata: rx={rx:.3f} ry={ry:.3f} "
                                f"rw={rw:.3f} rh={rh:.3f}")
        print(f"[ROI-Sel] ROI confermata e applicata", flush=True)
