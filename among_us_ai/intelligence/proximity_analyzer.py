"""
ProximityAnalyzer: analizza la prossimita' fra player e il bot.

Misura "chi mi segue di piu'" calcolando per ogni player il tempo cumulato
passato entro un certo raggio dal bot. Utile per:
- identificare stalker / killer potenziali
- sapere chi e' costantemente vicino in modo sospetto
- rilevare "gruppi" (3+ player vicini fra loro)
- bonus "alone-with-safe": se sono 1v1 con un player e NON muoio, ogni
  secondo passato cosi' abbassa il suo sospetto.
"""

import math
import time as _time


# Configurazione default (override-able tramite costruttore)
PROXIMITY_RADIUS = 5.0   # raggio per dire "vicino al bot" (unita' di gioco)
GROUP_RADIUS = 4.0       # raggio per dire "in gruppo" fra player
TIME_WINDOW_SEC = 120.0  # finestra di tempo per il "follow score" cumulato


class ProximityAnalyzer:
    """
    Calcola in continuo statistiche di prossimita'.

    Va chiamato `update(tracker, bot_pos, now)` da loop principale
    (es. 2-5 Hz). Mantiene contatori cumulativi che vengono usati
    dal UI/Sidebar.
    """

    def __init__(self, radius=PROXIMITY_RADIUS, window_sec=TIME_WINDOW_SEC):
        self.radius = radius
        self.window_sec = window_sec

        # player_name -> lista di (t, distance_from_bot)
        # Rolling: scartiamo i campioni piu' vecchi di window_sec.
        self._proximity_log = {}

        # player_name -> contatore "tempo totale vicino al bot"
        # Aggiornato dall' `update` e usato per il follow score.
        self._cumulative_near_time = {}

        # Per il "tempo speso vicino", abbiamo bisogno del delta-t fra
        # update. Memorizziamo l'ultimo tempo per ciascun player.
        self._last_seen_near_t = {}

        # === SOLO CON LUI (alone-with-safe, 1v1 sicuro) ===
        # Se sono SOLO con un player (nessun altro nelle vicinanze) e
        # NON muoio, ogni secondo passato cosi' abbassa il suo sospetto:
        # un impostore avrebbe killato in 1v1, quindi probabilmente
        # questo player e' crewmate.
        # player_name -> secondi cumulati di "1v1 vivo"
        self._alone_with_safe_time = {}
        # Ultima volta che abbiamo visto "io + lui da soli". Serve per
        # calcolare il delta-t da accumulare al prossimo update.
        self._alone_with_last_t = {}

    # ============================================================
    # ALIMENTAZIONE
    # ============================================================

    def update(self, tracker, bot_pos, now=None):
        """
        Aggiorna le statistiche di prossimita'.

        Per ogni player visibile, calcola la distanza dal bot e:
        - Se vicino: aggiorna il contatore di "tempo vicino"
        - Se lontano: chiude eventuale "sessione di vicinanza"
        """
        if now is None:
            now = _time.time()
        bx, by = bot_pos

        for player in tracker.all_players():
            if player.is_dead:
                continue
            if not player.last_snapshot:
                continue

            # Solo player visti recentemente (entro 3s)
            if player.seconds_since_last_seen(now) > 3.0:
                continue

            lp = player.last_snapshot
            dist = math.hypot(lp.x - bx, lp.y - by)

            # Log della distanza
            log = self._proximity_log.setdefault(player.name, [])
            log.append((now, dist))
            # Prune i campioni piu' vecchi di window_sec
            cutoff = now - self.window_sec
            while log and log[0][0] < cutoff:
                log.pop(0)

            # Tempo "vicino"
            if dist <= self.radius:
                last_t = self._last_seen_near_t.get(player.name)
                if last_t is not None:
                    # Player era gia' vicino: aggiungi delta
                    delta = now - last_t
                    if 0.0 < delta < 5.0:  # cap delta (sanity check)
                        self._cumulative_near_time[player.name] = (
                            self._cumulative_near_time.get(player.name, 0.0)
                            + delta
                        )
                self._last_seen_near_t[player.name] = now
            else:
                # Player NON e' piu' vicino: reset del marker
                self._last_seen_near_t.pop(player.name, None)

        # === ALONE WITH (1v1 sicuro) ===
        # Per ogni player vicino al bot: se non c'e' nessun ALTRO player
        # vicino (entro radius * 1.5 dal bot), siamo "soli" -> ogni
        # secondo che passo cosi' e' un punto a suo favore.
        # Se invece ci sono altri, NON conta come "alone" - MA non
        # cancello il bonus gia' accumulato per quel player: solo non
        # accumulo nuovi secondi finche' siamo di nuovo soli.
        nearby_alive = [
            p for p in tracker.all_players()
            if (not p.is_dead) and p.last_snapshot is not None
            and p.seconds_since_last_seen(now) <= 3.0
            and math.hypot(p.last_snapshot.x - bx,
                            p.last_snapshot.y - by) <= self.radius * 1.5
        ]
        if len(nearby_alive) == 1:
            # Esattamente un player con me: 1v1.
            solo = nearby_alive[0]
            last_t = self._alone_with_last_t.get(solo.name)
            if last_t is not None:
                delta = now - last_t
                # delta plausibile (<5s) = accumulo. Delta troppo grande
                # significa che il 1v1 e' stato interrotto in mezzo -
                # non accumulo questa fetta ma riparto dal prossimo tick.
                if 0.0 < delta < 5.0:
                    self._alone_with_safe_time[solo.name] = (
                        self._alone_with_safe_time.get(solo.name, 0.0)
                        + delta
                    )
            self._alone_with_last_t[solo.name] = now
        # Fix v2.2.48: NIENTE .clear() qui (era un bug). Se ora non e' piu'
        # 1v1, il timer del player smette di aggiornarsi: il prossimo tick
        # 1v1 vedra' un delta grande e non lo conteggera' come continuita',
        # ma il bonus accumulato precedentemente resta valido. Il .clear()
        # azzerava il bonus a ogni "interruzione" del 1v1, vanificando la
        # logica safe.

    # ============================================================
    # API DI QUERY
    # ============================================================

    def follow_score(self, player_name):
        """
        "Follow score": secondi cumulati passati entro radius dal bot.
        Piu' alto = piu' segue.
        """
        return self._cumulative_near_time.get(player_name, 0.0)

    def alone_with_safe_score(self, player_name):
        """
        Secondi cumulati passati 1v1 col player SENZA morire.
        Piu' alto = piu' probabile che sia crewmate (altrimenti
        avrebbe killato in 1v1).
        """
        return self._alone_with_safe_time.get(player_name, 0.0)

    def follow_ranking(self):
        """
        Ritorna i player ordinati per follow score decrescente.
        Lista di tuple (player_name, score).
        """
        return sorted(self._cumulative_near_time.items(),
                       key=lambda kv: kv[1], reverse=True)

    def avg_distance(self, player_name):
        """Distanza media dal bot negli ultimi window_sec."""
        log = self._proximity_log.get(player_name)
        if not log:
            return None
        return sum(d for _, d in log) / len(log)

    def current_distance(self, player_name):
        """Ultima distanza nota dal bot."""
        log = self._proximity_log.get(player_name)
        if not log:
            return None
        return log[-1][1]

    def detect_groups(self, tracker, now=None):
        """
        Identifica "gruppi": insiemi di 2+ player tutti entro
        GROUP_RADIUS l'uno dall'altro contemporaneamente.

        Ritorna lista di liste (cluster).
        """
        if now is None:
            now = _time.time()
        # Solo player visibili recenti
        visible = [p for p in tracker.all_players()
                   if (not p.is_dead) and p.is_visible_now(now, 3.0)
                   and p.last_snapshot is not None]
        if len(visible) < 2:
            return []

        # Clustering greedy: per ogni player, raggruppa con tutti i
        # vicini entro GROUP_RADIUS.
        clusters = []
        assigned = set()
        for i, pa in enumerate(visible):
            if pa.name in assigned:
                continue
            cluster = [pa]
            assigned.add(pa.name)
            for pb in visible[i+1:]:
                if pb.name in assigned:
                    continue
                dist = math.hypot(pa.last_snapshot.x - pb.last_snapshot.x,
                                   pa.last_snapshot.y - pb.last_snapshot.y)
                if dist <= GROUP_RADIUS:
                    cluster.append(pb)
                    assigned.add(pb.name)
            if len(cluster) >= 2:
                clusters.append(cluster)
        return clusters

    def reset(self):
        """Reset a inizio nuova partita."""
        self._proximity_log.clear()
        self._cumulative_near_time.clear()
        self._last_seen_near_t.clear()
        self._alone_with_safe_time.clear()
        self._alone_with_last_t.clear()
