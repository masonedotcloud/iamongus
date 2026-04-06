"""
ActivityDetector: rileva eventi sospetti dai movimenti dei player.

Lavora sopra `PlayerTracker` per produrre EVENTI (non solo dati):
- VENT_USE: player sparito + ricomparso lontano in poco tempo
  (= teletrasporto, sintomo di vent. Funziona SENZA bisogno di
   conoscere le posizioni delle vent: si basa solo sul gap di moto.)
- STOP: player fermo per >N secondi in un punto
- NEAR_BODY: player visto vicino a un cadavere
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

# Tipi di eventi
EV_VENT_USE     = 'VENT_USE'
EV_STOP         = 'STOP'
EV_NEAR_BODY    = 'NEAR_BODY'
EV_ERRATIC_MOVE = 'ERRATIC_MOVE'


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

        # Stato per evitare di registrare lo stesso evento piu' volte:
        # set di chiavi (event_type, player, timestamp_grosso, ...)
        self._recent_event_keys = set()
        self._recent_keys_max = 200

    # ============================================================
    # PUBLIC API
    # ============================================================

    def update(self, tracker, dead_bodies=None, now=None):
        """
        Analizza lo stato del tracker e genera nuovi eventi.

        :param tracker: istanza di PlayerTracker
        :param dead_bodies: lista di (x, y) di cadaveri noti.
            Se None, sviluppato in modo che `tracker.dead_players()`
            sia usato come sorgente alternativa.
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
            self._recent_event_keys.add(key)
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
        self._recent_event_keys.add(key)
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
            self._recent_event_keys.add(key)
            self._add_event(ActivityEvent(
                t=lp.t, type_=EV_NEAR_BODY,
                player_name=player.name, pos=(lp.x, lp.y),
                evidence={'body_pos': body_pos, 'dist': dist},
            ))
            break

    # ============================================================
    # HELPER
    # ============================================================

    def _add_event(self, ev):
        """Aggiunge un evento con cap di rolling."""
        self.events.append(ev)
        if len(self.events) > self.events_max:
            # Rimuovo i piu' vecchi
            self.events = self.events[-self.events_max:]
        # Manutenzione anti-duplicati: limita la cache
        if len(self._recent_event_keys) > self._recent_keys_max:
            # Mantieni solo gli ultimi (set non ha ordinamento, quindi
            # ricreo svuotando il piu' vecchio - approssimazione)
            keys = list(self._recent_event_keys)
            self._recent_event_keys = set(keys[-self._recent_keys_max // 2:])
