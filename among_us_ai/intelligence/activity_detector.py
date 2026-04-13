"""
ActivityDetector: rileva eventi sospetti dai movimenti dei player.

Lavora sopra `PlayerTracker` per produrre EVENTI (non solo dati):
- VENT_USE: player sparito + ricomparso lontano in poco tempo
  (= teletrasporto, sintomo di vent. Funziona SENZA bisogno di
   conoscere le posizioni delle vent: si basa solo sul gap di moto.)
- STOP: player fermo per >N secondi in un punto
- NEAR_BODY: player visto vicino a un cadavere
- SUDDEN_DISAPPEAR: player era visibile vicino al bot, e' sparito
  all'improvviso senza muoversi via (sospetto: kill+vent)
- ERRATIC_MOVE: movimento strano (es. avanti-indietro)

Ogni evento ha timestamp, tipo, player, posizione e "evidence"
(dati a supporto per debug).
"""

import math
import time as _time
from collections import defaultdict


# Configurazione default (override-able)
VENT_TELEPORT_MIN_DIST = 8.0   # distanza minima per dire "teletrasporto"
VENT_TELEPORT_MAX_TIME = 3.0   # se sparisce > ricompare entro N s = vent
NEAR_BODY_RADIUS = 3.0          # entro N unita' dal cadavere
STOP_MIN_DURATION = 1.5         # fermo per almeno N s = "stop event"

# Parametri per SUDDEN_DISAPPEAR (sparizione improvvisa).
# Il player era visibile e vicino al bot, poi all'improvviso non lo
# vedo piu', SENZA che si stesse muovendo verso il bordo del raggio
# di vista (cioe' non e' "lo perdo perche' si e' allontanato").
NEAR_BOT_RADIUS = 5.0          # distanza max dal bot per dire "era vicino"
DISAPPEAR_GAP_SEC = 2.0        # non visto da >N s = sparito
DISAPPEAR_MAX_GAP_SEC = 8.0    # se non lo vedo da troppo, non e' piu' "improvviso"
DISAPPEAR_MAX_SPEED = 1.5      # velocita' media bassa (u/s) prima della sparizione

# Tipi di eventi
EV_VENT_USE         = 'VENT_USE'
EV_STOP             = 'STOP'
EV_NEAR_BODY        = 'NEAR_BODY'
EV_SUDDEN_DISAPPEAR = 'SUDDEN_DISAPPEAR'
EV_ERRATIC_MOVE     = 'ERRATIC_MOVE'


class ActivityEvent:
    """Un singolo evento rilevato."""

    __slots__ = ('t', 'type', 'player', 'pos', 'evidence')

    def __init__(self, t, type_, player_name, pos, evidence=None):
        self.t = t
        self.type = type_
        self.player = player_name
        self.pos = pos               # (x, y)
        self.evidence = evidence or {}  # dict di supporto

    def __repr__(self):
        return f"<{self.type} {self.player} @{self.t:.1f} pos={self.pos}>"


class ActivityDetector:
    """
    Analizza il PlayerTracker per rilevare eventi sospetti.

    Mantiene una lista di eventi storici. Chiamare `update()` da loop
    principale per analizzare lo stato attuale e generare nuovi eventi.
    """

    def __init__(self):
        self.events = []  # lista di ActivityEvent (rolling, max 500)
        self.events_max = 500

        # Cache LRU per evitare di registrare lo stesso evento piu' volte.
        # USO UN DICT (insertion-ordered in Python 3.7+) cosi' quando faccio
        # l'eviction posso tenere gli N piu' RECENTI in modo deterministico.
        # Un set Python non garantirebbe l'ordine -> eviction casuale -> stessi
        # eventi rigenerati piu' volte (BUG osservato: score sale a step
        # quando un player resta troppo a lungo nel tracker).
        self._recent_event_keys = {}
        self._recent_keys_max = 500

        # Stato persistente per SUDDEN_DISAPPEAR: tiene traccia di quali
        # "sessioni di sparizione" (identificate dal timestamp dell'ultimo
        # avvistamento del player) abbiamo gia' segnalato. Resta in memoria
        # finche' il tracker stesso non viene resettato: quindi l'evento
        # viene generato UNA SOLA VOLTA per sparizione, anche se la cache
        # generica viene compattata.
        self._reported_disappear_sessions = set()

    # ============================================================
    # PUBLIC API
    # ============================================================

    def update(self, tracker, dead_bodies=None, bot_pos=None, now=None):
        """
        Analizza lo stato del tracker e genera nuovi eventi.

        :param tracker: istanza di PlayerTracker
        :param dead_bodies: lista di (x, y) di cadaveri noti.
            Se None, viene preso da `tracker.dead_players()`.
        :param bot_pos: tupla (x, y) del bot. Necessario per il detector
            SUDDEN_DISAPPEAR (serve sapere se il player era "vicino a me"
            prima di sparire). Se None, quel detector e' saltato.
        :param now: timestamp corrente (default: time.time())
        """
        if now is None:
            now = _time.time()

        if dead_bodies is None:
            dead_bodies = [(p.died_pos[0], p.died_pos[1])
                            for p in tracker.dead_players()
                            if p.died_pos is not None]

        for player in tracker.all_players():
            if player.is_dead:
                continue
            self._check_vent_use(player, now)
            self._check_stop(player, now)
            self._check_near_body(player, dead_bodies, now)
            if bot_pos is not None:
                self._check_sudden_disappear(player, bot_pos, now)

    def get_events(self, player_name=None, type_=None, since=None):
        """
        Filtra gli eventi storici.

        :param player_name: solo eventi di questo player
        :param type_: solo eventi di questo tipo (EV_VENT_USE, ecc.)
        :param since: solo eventi piu' recenti di questo timestamp
        """
        result = self.events
        if player_name is not None:
            result = [e for e in result if e.player == player_name]
        if type_ is not None:
            result = [e for e in result if e.type == type_]
        if since is not None:
            result = [e for e in result if e.t >= since]
        return result

    def count_events(self, player_name, type_, since=None):
        """Conta gli eventi di un tipo per un player."""
        return len(self.get_events(player_name, type_, since))

    def reset(self):
        """Cancella tutti gli eventi. A inizio nuova partita."""
        self.events.clear()
        self._recent_event_keys.clear()
        self._reported_disappear_sessions.clear()

    # ============================================================
    # DETECTOR INTERNI
    # ============================================================

    def _check_vent_use(self, player, now):
        """
        Rileva "uso vent": player sparito in pos A, ricomparso lontano
        in pos B in <VENT_TELEPORT_MAX_TIME s, con dist(A,B) >
        VENT_TELEPORT_MIN_DIST.
        """
        if len(player.history) < 2:
            return
        # Cerco un "gap" nella storia: 2 snapshot consecutivi con dt > 0.5s
        # e distanza grande. Quello e' il sintomo di vent.
        snaps = list(player.history)
        # Guardo solo gli ultimi 5 snapshot per non rifare lavoro vecchio
        recent = snaps[-5:]
        for i in range(1, len(recent)):
            a = recent[i - 1]
            b = recent[i]
            dt = b.t - a.t
            if dt < 0.4 or dt > VENT_TELEPORT_MAX_TIME:
                continue
            dist = math.hypot(b.x - a.x, b.y - a.y)
            if dist < VENT_TELEPORT_MIN_DIST:
                continue
            # Anti-duplicato: stesso evento (timestamp grezzo)
            key = (EV_VENT_USE, player.name, int(b.t))
            if key in self._recent_event_keys:
                continue
            self._recent_event_keys[key] = True
            self._add_event(ActivityEvent(
                t=b.t, type_=EV_VENT_USE,
                player_name=player.name, pos=(b.x, b.y),
                evidence={'from': (a.x, a.y), 'to': (b.x, b.y),
                          'dt': dt, 'dist': dist},
            ))

    def _check_stop(self, player, now):
        """
        Rileva "stop event": player fermo per >STOP_MIN_DURATION s.
        Genera UN evento per ogni "sessione di stop", non uno per scan.
        """
        if not player.last_snapshot:
            return
        stationary_sec = player.stationary_for_seconds()
        if stationary_sec < STOP_MIN_DURATION:
            return
        # Anti-duplicato: stesso player, stessa posizione (grossolana)
        lp = player.last_snapshot
        key = (EV_STOP, player.name,
               int(lp.x * 2) / 2,  # arrotondo a 0.5
               int(lp.y * 2) / 2)
        if key in self._recent_event_keys:
            return
        self._recent_event_keys[key] = True
        self._add_event(ActivityEvent(
            t=lp.t, type_=EV_STOP,
            player_name=player.name, pos=(lp.x, lp.y),
            evidence={'duration': stationary_sec},
        ))

    def _check_near_body(self, player, dead_bodies, now):
        """
        Rileva "vicino a cadavere": player visto entro NEAR_BODY_RADIUS
        da una posizione marcata come cadavere.
        """
        if not player.last_snapshot or not dead_bodies:
            return
        lp = player.last_snapshot
        for body_pos in dead_bodies:
            dist = math.hypot(lp.x - body_pos[0], lp.y - body_pos[1])
            if dist > NEAR_BODY_RADIUS:
                continue
            key = (EV_NEAR_BODY, player.name,
                   round(body_pos[0]), round(body_pos[1]),
                   int(lp.t))
            if key in self._recent_event_keys:
                continue
            self._recent_event_keys[key] = True
            self._add_event(ActivityEvent(
                t=lp.t, type_=EV_NEAR_BODY,
                player_name=player.name, pos=(lp.x, lp.y),
                evidence={'body_pos': body_pos, 'dist': dist},
            ))
            break

    def _check_sudden_disappear(self, player, bot_pos, now):
        """
        Rileva "sparizione improvvisa": il player era visibile e vicino
        al bot, poi all'improvviso non lo vedo piu' SENZA che si stesse
        allontanando con movimento normale (= non e' "uscito dalla mia
        vista").

        Logica:
        1. Ultimo avvistamento entro NEAR_BOT_RADIUS dal bot
        2. Sono passati >DISAPPEAR_GAP_SEC senza piu' vederlo
        3. Sono passati <DISAPPEAR_MAX_GAP_SEC (sennò non e' "improvviso",
           magari era fuori vista da troppo)
        4. La velocita' media negli ultimi snapshot era bassa (<DISAPPEAR_MAX_SPEED).
           Cosi' distinguiamo "sparizione improvvisa" da "lo perdo perche'
           sta correndo via dal mio raggio".
        """
        if not player.last_snapshot:
            return
        # Tempo trascorso dall'ultimo avvistamento
        gap = now - player._last_observation_t
        if gap < DISAPPEAR_GAP_SEC:
            return  # ancora "visibile" o appena uscito
        if gap > DISAPPEAR_MAX_GAP_SEC:
            return  # troppo tempo passato, non e' piu' "improvviso"

        # Ultima posizione vista
        lp = player.last_snapshot
        dist_da_bot = math.hypot(lp.x - bot_pos[0], lp.y - bot_pos[1])
        if dist_da_bot > NEAR_BOT_RADIUS:
            return  # non era vicino a me al momento dell'ultimo avvistamento

        # Velocita' media ultimi snapshot: se si stava muovendo veloce,
        # potrebbe essere semplicemente uscito dal raggio di vista.
        snaps = list(player.history)
        if len(snaps) >= 2:
            recent = snaps[-3:]  # ultimi 2-3 snapshot
            total_dist = 0.0
            total_dt = 0.0
            for i in range(1, len(recent)):
                a = recent[i - 1]
                b = recent[i]
                dt = b.t - a.t
                if dt <= 0:
                    continue
                total_dist += math.hypot(b.x - a.x, b.y - a.y)
                total_dt += dt
            avg_speed = (total_dist / total_dt) if total_dt > 0 else 0.0
            if avg_speed > DISAPPEAR_MAX_SPEED:
                # Si stava muovendo veloce: probabilmente uscito dal raggio
                return

        # Anti-duplicato STRONG: una "sessione di sparizione" e' identificata
        # dal timestamp dell'ultimo avvistamento. Uso un set DEDICATO che
        # NON viene mai evettato (a differenza della cache generica) cosi'
        # ogni sparizione genera UN solo evento per tutta la durata della
        # partita.
        # Floor a 0.5s di granularita' per essere robusti a noise nei
        # timestamp YOLO.
        session_id = (player.name, round(lp.t * 2) / 2)
        if session_id in self._reported_disappear_sessions:
            return
        self._reported_disappear_sessions.add(session_id)
        self._add_event(ActivityEvent(
            t=now, type_=EV_SUDDEN_DISAPPEAR,
            player_name=player.name, pos=(lp.x, lp.y),
            evidence={
                'last_pos': (lp.x, lp.y),
                'bot_pos': bot_pos,
                'dist_da_bot': dist_da_bot,
                'gap_sec': gap,
            },
        ))

    # ============================================================
    # HELPER
    # ============================================================

    def _add_event(self, ev):
        """Aggiunge un evento con cap di rolling."""
        self.events.append(ev)
        if len(self.events) > self.events_max:
            # Rimuovo i piu' vecchi
            self.events = self.events[-self.events_max:]
        # Manutenzione anti-duplicati: limita la cache (LRU corretto).
        # Il dict in Python 3.7+ garantisce insertion order, quindi quando
        # supero il cap posso scartare le chiavi PIU' VECCHIE (non a caso
        # come faceva il vecchio set, che causava la rigenerazione dello
        # stesso evento a step).
        while len(self._recent_event_keys) > self._recent_keys_max:
            # popitem(last=False) toglie l'item piu' vecchio
            # Equivalente per dict normale: iter + next
            oldest_key = next(iter(self._recent_event_keys))
            del self._recent_event_keys[oldest_key]
