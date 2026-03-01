"""
Handler per "Simon Says".

Il gioco mostra una sequenza di pulsanti che si illuminano, poi il
giocatore deve riprodurla. Il bot legge la sequenza tramite analisi
colore frame-per-frame e poi clicca i pulsanti nello stesso ordine.
"""
import time as _time
try:
    import pyautogui as _pag
except Exception:
    _pag = None
from .input_mouse import _click_hold

def _h_simon_says(az, cx, cy, cw, ch, hwnd, durata, attesa):
    """
    Handler Simon Says.

    Il gioco mostra una sequenza di LED che si illuminano in sequenza,
    poi il giocatore deve riprodurla. La sequenza cresce ogni round:
    - Round 1: 1 LED (A)
    - Round 2: 2 LED (A, B)
    - Round 3: 3 LED (A, B, C)
    - ecc.

    Il bot:
    1. Cattura una `base_img` iniziale (stato "spento" del pannello).
    2. Per ogni round, monitora i display point cercando colori molto
       diversi dalla base (= LED acceso).
    3. Costruisce la sequenza dei flash rilevati.
    4. Clicca i keypad corrispondenti nello stesso ordine.
    5. PAUSA prima del round successivo + RICATTURA della base
       (importante: dopo i click, lo stato del pannello cambia per
       feedback visivo del gioco, e la vecchia base_img puo' non essere
       piu' valida per il prossimo round).
    """
    import mss as _mss
    import numpy as _np
    disp_pts = [(cx + int(p[0] * cw), cy + int(p[1] * ch)) for p in az['display']]
    keyp_pts = [(cx + int(p[0] * cw), cy + int(p[1] * ch)) for p in az['keypad']]

    # Pausa fra la fine dei click di un round e l'inizio del rilevamento
    # del round successivo. Serve per:
    # - lasciar finire l'animazione di feedback dei click (luce sul pulsante)
    # - lasciar partire il gioco con la nuova sequenza
    # - ricatturare la base "pulita" senza artefatti
    POST_CLICK_PAUSE = 1.0

    with _mss.mss() as sct:
        monitor = {'top': cy, 'left': cx, 'width': cw, 'height': ch}

        def _read_base():
            """Cattura uno snapshot dei display point come base."""
            img = _np.array(sct.grab(monitor))
            return [img[p[1] - cy, p[0] - cx, :3] for p in disp_pts]

        # Cattura la prima base SUBITO. Per pannelli con animazione di
        # apertura lenta, configura `delay_avvio` sulla task cosi' il
        # motore aspetta prima di chiamare questo handler.
        base_colors = _read_base()
        print(f"[Simon] Base iniziale catturata su {len(disp_pts)} display point",
              flush=True)

        for rnd in range(1, 6):
            sequence = []
            last_lit = -1
            start_t = _time.time()
            print(f"[Simon] Round {rnd}: aspetto {rnd} flash...", flush=True)

            while len(sequence) < rnd and _time.time() - start_t < 10.0:
                img = _np.array(sct.grab(monitor))
                lit_now = -1
                for i, (dx, dy) in enumerate(disp_pts):
                    px_col = img[dy - cy, dx - cx, :3]
                    bc = base_colors[i]
                    diff = (abs(int(px_col[0]) - int(bc[0]))
                          + abs(int(px_col[1]) - int(bc[1]))
                          + abs(int(px_col[2]) - int(bc[2])))
                    if diff > 50:
                        lit_now = i
                        break
                if lit_now != -1:
                    if lit_now != last_lit:
                        sequence.append(lit_now)
                        last_lit = lit_now
                        # Reset timeout: ogni nuovo flash riparte il timer
                        start_t = _time.time()
                        print(f"[Simon] Round {rnd}: flash #{len(sequence)} = LED {lit_now} "
                              f"(seq={sequence})", flush=True)
                        # Pausa per non contare due volte lo stesso flash
                        # se rimane acceso a lungo
                        _time.sleep(0.15)
                else:
                    # Display tutti spenti: prossimo flash sara' un nuovo LED
                    last_lit = -1
                    # Polling rapido per non perdere flash brevi
                    _time.sleep(0.02)

            if len(sequence) == 0:
                print(f"[Simon] Round {rnd}: TIMEOUT, nessun flash rilevato. Esco.",
                      flush=True)
                break
            if len(sequence) < rnd:
                print(f"[Simon] Round {rnd}: rilevati solo {len(sequence)}/{rnd} "
                      f"flash. Provo a cliccare lo stesso.", flush=True)

            # Pausa tra ultimo flash e primo click. Nel gioco originale
            # c'e' un piccolo delay fra "fine sequenza" e "inizio input",
            # rispettiamolo cosi' il primo click va a buon fine.
            _time.sleep(0.4)

            # Click dei keypad nella sequenza rilevata
            print(f"[Simon] Round {rnd}: clicco {len(sequence)} keypad...",
                  flush=True)
            for idx in sequence:
                kx, ky = keyp_pts[idx]
                _click_hold(kx, ky, durata)
                _time.sleep(0.05)

            # === PAUSA POST-CLICK + RICATTURA BASE ===
            # Dopo aver cliccato i keypad:
            # - Il gioco mostra il feedback visivo (luce/animazione sui
            #   pulsanti cliccati), che potrebbe alterare i display point.
            # - Il gioco poi mostra il round successivo con UNA SEQUENZA
            #   PIU' LUNGA (rnd+1 flash).
            # Aspettiamo che le animazioni di feedback finiscano e
            # ricatturiamo la base, cosi' il prossimo round monitora
            # contro lo stato "spento" reale del pannello in quel momento.
            if rnd < 5:
                print(f"[Simon] Round {rnd}: pausa {POST_CLICK_PAUSE}s e "
                      f"ricattura base per round {rnd+1}", flush=True)
                _time.sleep(POST_CLICK_PAUSE)
                base_colors = _read_base()

    _time.sleep(attesa)


