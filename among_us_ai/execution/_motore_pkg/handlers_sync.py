"""
Handler per il minigioco "Calibrate Distributor" e simili sync-click.

Polling sul colore di un punto di osservazione: quando cambia
(rispetto al colore base iniziale), clicca il punto associato.
Verifica anche che i punti precedenti restino "accesi" (la sequenza
non sia stata invalidata dal gioco).
"""
import time as _time
try:
    import pyautogui as _pag
except Exception:
    _pag = None

def _h_sync_click(az, cx, cy, cw, ch, hwnd, durata, attesa):
    """
    Handler ``sync_click``: minigioco "Calibrate Distributor" e simili.

    Per ogni punto della sequenza:
      1. Polla il colore del punto di osservazione (chk_x, chk_y)
      2. Quando il colore cambia rispetto al baseline E supera una soglia
         di luminosita', clicca il pulsante (btn_x, btn_y)
      3. Dopo il click, verifica che TUTTI i punti precedenti siano ancora
         "accesi" (RGB sum > 75). Se uno e' spento, la sequenza e' stata
         invalidata dal gioco -> ricomincia da capo (retry).

    Max 3 retry per la sequenza completa, timeout 8s per ogni singolo punto.
    """
    punti_sync = az.get('punti', [])
    i_sync = 0
    max_retries = 3
    retry_count = 0

    # Pre-calcolo le coordinate assolute dei punti di check (una volta sola).
    check_coords_abs = []
    for cx_rel, cy_rel, _, _ in punti_sync:
        check_coords_abs.append((cx + int(cx_rel * cw), cy + int(cy_rel * ch)))

    while i_sync < len(punti_sync):
        if retry_count >= max_retries:
            print(f'[SyncClick] Tentativi massimi ({max_retries}) raggiunti. '
                  'Annullamento.')
            break

        _, _, bx_rel, by_rel = punti_sync[i_sync]
        chk_x, chk_y = check_coords_abs[i_sync]
        btn_x = cx + int(bx_rel * cw)
        btn_y = cy + int(by_rel * ch)

        # Pre-posiziono il mouse sul pulsante (cosi' il click successivo
        # e' istantaneo) e leggo il colore "spento" come baseline.
        _pag.moveTo(btn_x, btn_y, duration=0.1)
        try:
            base_col = _pag.pixel(chk_x, chk_y)
        except Exception:
            base_col = (0, 0, 0)

        # Loop di attesa "luce accesa": polla ogni 5ms fino a 8s.
        # "Accesa" = luminosita' totale > 60 E delta RGB dal baseline > 40.
        start_t = _time.time()
        clicked = False
        while _time.time() - start_t < 8.0:
            try:
                r, g, b = _pag.pixel(chk_x, chk_y)
                if (r + g + b > 60
                    and abs(r - base_col[0]) + abs(g - base_col[1])
                        + abs(b - base_col[2]) > 40):
                    _pag.click()
                    clicked = True
                    break
            except Exception:
                pass
            _time.sleep(0.005)

        if not clicked:
            # Timeout su questo punto: ricomincia tutta la sequenza.
            print(f'[SyncClick] Timeout al punto {i_sync + 1}. Riavvio sequenza.')
            i_sync = 0
            retry_count += 1
            _time.sleep(1.0)
            continue

        # Pausa breve per dare al gioco il tempo di registrare il click.
        _time.sleep(0.2)

        # Verifica integrita' della sequenza: tutti i punti gia' fatti
        # devono essere ancora "accesi" (RGB sum > 75). Se uno e' spento,
        # significa che il gioco ha resettato la sequenza (es. fallito
        # un timing). Ricomincia.
        sequence_failed = False
        failed_at_step = -1
        for k in range(i_sync + 1):
            prev_chk_x, prev_chk_y = check_coords_abs[k]
            try:
                r, g, b = _pag.pixel(prev_chk_x, prev_chk_y)
                if r + g + b < 75:
                    sequence_failed = True
                    failed_at_step = k + 1
                    break
            except Exception:
                sequence_failed = True
                failed_at_step = k + 1
                break

        if sequence_failed:
            print(f'[SyncClick] Fallimento rilevato al passo {failed_at_step}.'
                  f' Riavvio (tentativo {retry_count + 1}/{max_retries}).')
            i_sync = 0
            retry_count += 1
            _time.sleep(0.75)
            continue

        # Tutto OK: avanzo al prossimo punto.
        i_sync += 1
    _time.sleep(attesa)


