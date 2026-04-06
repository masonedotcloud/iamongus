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
    Handler Simon Says (Start Reactor in Skeld).

    Comportamento del minigioco (verificato):
    - Pannello si apre con la zona nera e i 9 quadrati spenti.
    - Il minigioco NON parte automaticamente: aspetta un click
      iniziale del giocatore su uno qualsiasi dei keypad per
      "innescarsi". Senza questo click iniziale, il pannello resta
      fermo e nessuna sequenza viene mostrata.
    - Dopo il click iniziale, il gioco mostra la sequenza:
      - Round 1: flash 1 LED -> giocatore clicca quel LED
      - Round 2: flash 2 LED (A, B da capo!) -> giocatore clicca A, B
      - Round 3: flash 3 LED da capo -> clicca tutti
      - Round 4: 4 LED da capo
      - Round 5: 5 LED da capo
    Ogni round la sequenza viene riprodotta DAL PRIMO LED, allungata
    di uno.

    Strategia robusta:

    1. CATTURA BASE INTELLIGENTE
       Prendiamo 30 snapshot in 600ms e per ogni LED teniamo il valore
       MIN (piu' scuro) come "spento reale". Robusto se al momento
       sbagliato un LED e' acceso.

    2. CLICK INIZIALE PER INNESCARE
       Clicchiamo il primo keypad (idx 0) per far partire la sequenza.
       Senza questo click il gioco non mostra mai nessun flash.

    3. LOOP DI ASCOLTO PER OGNI ROUND
       Aspetto che parta un flash. Quando un LED si accende, lo
       registro. Continuo a registrare LED diversi (con debounce).
       Quando vedo PAUSA SILENZIOSA (nessun LED acceso) per >0.6s,
       considero la sequenza finita -> clicco la sequenza registrata.

    4. RIPETO PER 6 ROUND (sicurezza)
       Dopo ogni click, aspetto il prossimo flash. Se non arriva
       entro 4s, considero la task completata -> esco.
    """
    import mss as _mss
    import numpy as _np
    disp_pts = [(cx + int(p[0] * cw), cy + int(p[1] * ch)) for p in az['display']]
    keyp_pts = [(cx + int(p[0] * cw), cy + int(p[1] * ch)) for p in az['keypad']]

    # Soglia diff colore per considerare un LED "acceso".
    # Somma delle differenze R+G+B fra pixel corrente e base "spento".
    SOGLIA_LED_ACCESO = 50

    # Pausa che separa "sequenza finita" da "fase input"
    PAUSA_FINE_SEQUENZA = 0.6   # secondi di silenzio per dichiarare fine seq

    # Timeout massimo di attesa per il flash inizio round
    TIMEOUT_PRIMO_FLASH = 4.0

    # Polling rate durante il rilevamento (50fps = 20ms)
    POLL_DT = 0.02

    # Debounce flash: pausa breve dopo aver rilevato un flash per non
    # contare due volte lo stesso LED se rimane acceso a lungo
    DEBOUNCE_DT = 0.10

    with _mss.mss() as sct:
        monitor = {'top': cy, 'left': cx, 'width': cw, 'height': ch}

        # === CATTURA BASE INTELLIGENTE ===
        # Prendo 30 snapshot in 600ms e per ogni LED tengo il colore
        # piu' SCURO (= spento). Robusto anche se durante la cattura
        # il pannello fosse gia' parzialmente illuminato.
        print(f"[Simon] Cattura base intelligente (30 frame in 600ms)...",
              flush=True)
        base_colors = None
        for _ in range(30):
            img = _np.array(sct.grab(monitor))
            campione = [img[p[1] - cy, p[0] - cx, :3] for p in disp_pts]
            if base_colors is None:
                # Prima iterazione: la copia diventa la base
                base_colors = [c.copy() for c in campione]
            else:
                # Iterazioni successive: per ogni LED, tieni il piu' scuro
                # (somma RGB minima = piu' scuro = spento)
                for i, c in enumerate(campione):
                    if (int(c[0]) + int(c[1]) + int(c[2])
                            < int(base_colors[i][0]) + int(base_colors[i][1])
                              + int(base_colors[i][2])):
                        base_colors[i] = c.copy()
            _time.sleep(0.02)
        print(f"[Simon] Base catturata su {len(disp_pts)} display point",
              flush=True)

        def _led_acceso(img):
            """
            Ritorna l'indice del LED acceso, o -1 se tutti spenti.
            Confronta ogni display point con la sua base "spento".
            """
            for i, (dx, dy) in enumerate(disp_pts):
                px_col = img[dy - cy, dx - cx, :3]
                bc = base_colors[i]
                diff = (abs(int(px_col[0]) - int(bc[0]))
                      + abs(int(px_col[1]) - int(bc[1]))
                      + abs(int(px_col[2]) - int(bc[2])))
                if diff > SOGLIA_LED_ACCESO:
                    return i
            return -1

        # === CLICK INIZIALE PER INNESCARE IL MINIGIOCO ===
        # Il minigioco non parte da solo: clicchiamo il primo keypad
        # per farlo iniziare. Il gioco poi mostrera' la sequenza dal
        # round 1.
        kx0, ky0 = keyp_pts[0]
        print(f"[Simon] Click iniziale di innesco sul keypad 0 "
              f"({kx0},{ky0})", flush=True)
        _click_hold(kx0, ky0, durata)
        # Pausa breve per dare al gioco il tempo di "registrare" il
        # click di innesco e iniziare a mostrare la sequenza.
        _time.sleep(0.3)

        for rnd in range(1, 7):  # max 6 round (Among Us ne fa 5)
            print(f"[Simon] Round {rnd}: aspetto inizio sequenza...",
                  flush=True)
            sequence = []
            last_lit = -1
            ultimo_flash_t = None
            inizio_attesa = _time.time()

            while True:
                img = _np.array(sct.grab(monitor))
                lit_now = _led_acceso(img)

                if lit_now != -1:
                    # Un LED e' acceso ora
                    if lit_now != last_lit:
                        # Nuovo LED (diverso dal precedente) -> registra
                        sequence.append(lit_now)
                        last_lit = lit_now
                        ultimo_flash_t = _time.time()
                        print(f"[Simon] Round {rnd}: flash #{len(sequence)} "
                              f"= LED {lit_now} (seq={sequence})", flush=True)
                        # Debounce: pausa breve per non contare due volte
                        # lo stesso flash se rimane acceso
                        _time.sleep(DEBOUNCE_DT)
                    else:
                        # Stesso LED ancora acceso: ignora, polling normale
                        _time.sleep(POLL_DT)
                else:
                    # Tutti spenti
                    last_lit = -1
                    if not sequence:
                        # Nessun flash ancora: timeout primo flash
                        if _time.time() - inizio_attesa > TIMEOUT_PRIMO_FLASH:
                            print(f"[Simon] Round {rnd}: TIMEOUT, nessun "
                                  f"flash rilevato in {TIMEOUT_PRIMO_FLASH}s. "
                                  f"Task probabilmente completata, esco.",
                                  flush=True)
                            _time.sleep(attesa)
                            return
                        _time.sleep(POLL_DT)
                    else:
                        # Ho gia' visto qualche flash: se silenzio sufficiente,
                        # la sequenza e' finita
                        silenzio = _time.time() - ultimo_flash_t
                        if silenzio > PAUSA_FINE_SEQUENZA:
                            # Sequenza completa, vado a cliccare
                            print(f"[Simon] Round {rnd}: sequenza completa "
                                  f"({len(sequence)} flash), silenzio "
                                  f"{silenzio:.2f}s -> clicco", flush=True)
                            break
                        _time.sleep(POLL_DT)

            # Pausa tra fine sequenza e primo click. Il gioco passa in
            # "fase input": piccolo delay e' buona pratica per stabilita'.
            _time.sleep(0.25)

            # Click dei keypad nella sequenza rilevata
            print(f"[Simon] Round {rnd}: clicco {len(sequence)} keypad...",
                  flush=True)
            for idx in sequence:
                kx, ky = keyp_pts[idx]
                _click_hold(kx, ky, durata)
                _time.sleep(0.05)

    _time.sleep(attesa)


