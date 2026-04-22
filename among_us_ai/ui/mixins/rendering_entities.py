"""
Rendering delle entita' dinamiche: task, altri giocatori, player locale, HUD.

Mixin di GPSVisualizerPro.
"""

from ._imports import *


class RenderingEntitiesMixin:
    """Mixin con i metodi di rendering entities di GPSVisualizerPro."""
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
            chiave_mem = (mt.get('tipo'), mt.get('id_stanza'))
            active_keys.add(chiave_mem)
            if mt.get('done', False):
                completed_keys.add(chiave_mem)

        # Itera tutte le task registrate
        for t in self.task_mgr.task_list:
            chiave_task = (t.get('tipo'), t.get('id_stanza'))
            is_vitale      = bool(t.get('vitale', False))
            is_due_p       = bool(t.get('due_giocatori', False))

            # Filtro opzionale: mostra solo se attiva in memoria
            if getattr(self, 'show_only_active_tasks', False) and chiave_task not in active_keys:
                continue

            # 2. Determinazione colore in base allo stato
            if chiave_task in completed_keys:
                # Task FATTA -> Verde (anche se vitale, ormai e' completata)
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

            # Disegno Fasi (se presenti) - punti numerati collegati con linea tratteggiata
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
                    # Freccia a meta' linea per indicare la direzione
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

                # Punti fase (dal secondo in poi - il primo e' gia' disegnato come task principale)
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

                # Aggiunge "1" al marker principale per coerenza visiva
                dpg.draw_text((sx - 4, sy - 7), "0", color=(10, 10, 10, 255), size=13)

            # Punti alternativo (simili a fasi ma senza collegamenti o con linea diversa)
            alternativi = t.get('alternativi', [])
            for i, frat in enumerate(alternativi, start=1):
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

        # === RENDERING DEL GIRO PREVIEW (popup F1 aperto) ===
        # Se la preview del giro Auto-All e' aperta, disegniamo le linee
        # numerate fra task in sequenza sopra la mappa.
        self._render_giro_preview(cam_x, cam_y, half_w, half_h, scale)

    def _render_giro_preview(self, cam_x, cam_y, half_w, half_h, scale):
        """
        Disegna sulla mappa la sequenza del giro Auto-All quando la
        preview e' aperta (popup F1). Mostra:
          - Linee colorate che SEGUONO IL PATHFINDING A* fra task in
            sequenza (NON in linea retta - rispettano muri/porte)
          - Numeri sui pallini delle task per indicare l'ordine
          - Linea dal bot alla prima task

        PERFORMANCE: i path A* sono PRE-CALCOLATI in
        `_aggiorna_preview_giro` (refresh ogni 1s) e qui solo letti
        dalla lista `_giro_preview_paths`. NON viene chiamato A*
        nel render loop, altrimenti laggherebbe pesantemente (60 fps
        x N task A* = troppo).

        Il nodo `giro_preview_node` e' pre-creato in `ui_setup.py`
        come gli altri layer (task_node, player_node, ecc.).
        """
        # Cleanup contenuto precedente del nodo (svuoto i children)
        if dpg.does_item_exist("giro_preview_node"):
            dpg.delete_item("giro_preview_node", children_only=True)
        else:
            # Sicurezza: se per qualche motivo il nodo non esiste, esco.
            # In condizioni normali viene creato in ui_setup.py.
            return

        giro = getattr(self, '_giro_preview_lista', None)
        if not giro:
            return
        paths = getattr(self, '_giro_preview_paths', None) or []

        dpg.push_container_stack("giro_preview_node")

        try:
            # Coordinate di partenza: posizione del bot
            prev_x, prev_y = self.pos_target

            for i, (task, dist, score) in enumerate(giro, 1):
                tx, ty = task['x'], task['y']

                # === COLORE DEL SEGMENTO ===
                # Verde brillante per la prossima (i=1), rosso per le
                # vitali successive, arancione/giallo per le altre.
                if i == 1:
                    col_line = (0, 255, 100, 220)    # verde (prossima)
                    col_text = (0, 255, 100, 255)
                elif task.get('vitale'):
                    col_line = (255, 100, 100, 200)  # rosso (vitale)
                    col_text = (255, 100, 100, 255)
                else:
                    # Sfumatura di arancione/giallo
                    alpha = max(80, 200 - i * 20)
                    col_line = (255, 200, 80, alpha)
                    col_text = (255, 200, 80, 255)

                # === DISEGNO DEL PERCORSO ===
                # Leggo il path pre-calcolato per il segmento i-esimo.
                # Se manca (lista pi corta del giro, A* fallita), uso
                # linea retta come fallback.
                path = paths[i - 1] if i - 1 < len(paths) else None

                if path and len(path) >= 2:
                    # Disegno il path come sequenza di segmenti consecutivi
                    # fra i waypoint dell'A*.
                    for j in range(1, len(path)):
                        ax, ay = path[j-1]
                        bx, by = path[j]
                        sax = (ax - cam_x) * scale + half_w
                        say = -(ay - cam_y) * scale + half_h
                        sbx = (bx - cam_x) * scale + half_w
                        sby = -(by - cam_y) * scale + half_h
                        dpg.draw_line((sax, say), (sbx, sby),
                                        color=col_line, thickness=2)
                else:
                    # Fallback: linea retta (path non disponibile)
                    px = (prev_x - cam_x) * scale + half_w
                    py = -(prev_y - cam_y) * scale + half_h
                    wx = (tx - cam_x) * scale + half_w
                    wy = -(ty - cam_y) * scale + half_h
                    # Linea sottile per evidenziare il fallback
                    dpg.draw_line((px, py), (wx, wy),
                                    color=col_line, thickness=1)

                # === NUMERO + CERCHIO SOPRA AL PALLINO TASK ===
                wx = (tx - cam_x) * scale + half_w
                wy = -(ty - cam_y) * scale + half_h
                # Cerchio nero di sfondo per leggibilita' del numero
                dpg.draw_circle((wx, wy), 16,
                                  color=(0, 0, 0, 180),
                                  fill=(0, 0, 0, 160),
                                  thickness=2)
                # Numero della sequenza al centro
                dpg.draw_text((wx - 5 if i < 10 else wx - 9, wy - 8),
                                str(i), color=col_text, size=14)

                prev_x, prev_y = tx, ty
        finally:
            dpg.pop_container_stack()

    def _render_other_players(self, cam_x, cam_y, half_w, half_h, scale):
        """Disegna gli altri player rilevati con YOLO: cerchio col loro colore + nome + score di sospettosita'."""
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
        """Disegna il marker del giocatore locale: cerchio verde con alone (\"glow\") e crocino centrale."""
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
        """Disegna l'HUD (testi sovraimpressi): stato auto-move, debug, status_msg."""
        dpg.set_value("status_x",    f"X: {self.pos_target[0]:.3f}")
        dpg.set_value("status_y",    f"Y: {self.pos_target[1]:.3f}")
        dpg.set_value("status_fps",  f"FPS: {dpg.get_frame_rate()}")
        dpg.set_value("status_mode", f"Mode: {self.camera_mode}")
        dpg.set_value("status_zoom", f"Zoom: {self.scale:.0f}")

        if self.auto_enabled:
            if self.auto_path:
                # Cambia le configurazioni di un widget gia' creato
                dpg.configure_item("status_auto", color=Colors.TARGET)
                dpg.set_value("status_auto", f"Auto: ON ({self.auto_status_msg})")
            else:
                # Cambia le configurazioni di un widget gia' creato
                dpg.configure_item("status_auto", color=Colors.ACCENT)
                dpg.set_value("status_auto", "Auto: ARMATO (click mappa)")
        else:
            # Cambia le configurazioni di un widget gia' creato
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
            dpg.set_value("auto_target_label", "-")
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
                keys_txt = "+".join(sorted(self.key_ctrl.pressed)) or "-"
                amsg = f"AUTO -> {self.auto_status_msg}  |  {keys_txt}"
                dpg.draw_text((11, 33), amsg, color=(0, 0, 0, 220), size=16)
                dpg.draw_text((10, 32), amsg, color=Colors.TARGET, size=16)
            dpg.pop_container_stack()
