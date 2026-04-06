"""
PlayerTracker: storico posizioni di ogni player.

Componente di "intelligence": traccia in modo persistente la cronologia
di ogni player rilevato, anche dopo che esce dal raggio di vista.

Per ogni player conserva:
- Lista di snapshot (timestamp, x, y, stanza, is_dead)
- Stato corrente (visibile/non visibile da X secondi)
- Statistiche aggregate (tempo totale visto, distanza percorsa, ecc.)

Il tracker viene alimentato dal sistema YOLO esistente:
chi rileva i player chiama `tracker.observe(name, x, y, time, is_dead, color)`
e il tracker fa tutto il resto.
"""

import math
import time as _time
from collections import deque


# Default config (override-able tramite costruttore)
HISTORY_MAX_SNAPSHOTS = 500       # max snapshot per player (rolling)
HISTORY_MAX_AGE_SEC   = 600.0     # snapshot piu' vecchi vengono scartati (10 min)
STATIONARY_THRESHOLD_DIST = 0.5   # distanza per dire "fermo" fra 2 snapshot vicini
STATIONARY_TIME_DELTA_SEC = 0.3   # solo confronti snapshot con questo gap min


class PlayerSnapshot:
    """Un singolo osservazione di un player in un momento dato."""

    __slots__ = ('t', 'x', 'y', 'stanza', 'is_dead')

    def __init__(self, t, x, y, stanza=None, is_dead=False):
        self.t = t                # timestamp (time.time())
        self.x = x
        self.y = y
        self.stanza = stanza      # nome della stanza (o None se non noto)
        self.is_dead = is_dead

    def __repr__(self):
        st = self.stanza or '?'
        d = ' [MORTO]' if self.is_dead else ''
        return f"<Snap t={self.t:.1f} ({self.x:.1f},{self.y:.1f}) {st}{d}>"


class PlayerInfo:
    """Tutto cio' che sappiamo su un singolo player."""

    def __init__(self, name, color):
        self.name = name              # nome identificativo (es. "Rosso")
        self.color = color            # (r, g, b) per UI

        # Storia rolling (deque per O(1) append/popleft)
        self.history = deque(maxlen=HISTORY_MAX_SNAPSHOTS)

        # Snapshot piu' recente per accesso O(1)
        self.last_snapshot = None

        # Flag: e' attualmente visibile (rilevato negli ultimi 2s)?
        self._last_observation_t = None

        # Stato morte (sticky: una volta morto, resta morto)
        self.is_dead = False
        self.died_at = None      # timestamp di prima rilevazione "is_dead=True"
        self.died_pos = None     # (x, y) dove e' stato visto morto

        # Cache: invalidata ad ogni `observe()`. Per metriche derivate.
        self._cache_invalidated = True

    # ============================================================
    # ALIMENTAZIONE
    # ============================================================

    def observe(self, t, x, y, stanza=None, is_dead=False, color=None):
        """
        Aggiunge un'osservazione. Chiamato dal sistema YOLO ad ogni scan.
        """
        snap = PlayerSnapshot(t, x, y, stanza=stanza, is_dead=is_dead)
        self.history.append(snap)
        self.last_snapshot = snap
        self._last_observation_t = t
        self._cache_invalidated = True

        # Sticky death: una volta morto, resta morto. Memorizziamo
        # dove e quando.
        if is_dead and not self.is_dead:
            self.is_dead = True
            self.died_at = t
            self.died_pos = (x, y)

        # Aggiornamento colore (se cambia es. da Unknown a Rosso)
        if color is not None:
            self.color = color

    # ============================================================
    # PROPRIETA' SEMPLICI
    # ============================================================

    def is_visible_now(self, now=None, max_age=2.0):
        """True se rilevato negli ultimi `max_age` secondi."""
        if self._last_observation_t is None:
            return False
        if now is None:
            now = _time.time()
        return (now - self._last_observation_t) <= max_age

    def seconds_since_last_seen(self, now=None):
        """Quanto tempo e' passato dall'ultima osservazione."""
        if self._last_observation_t is None:
            return float('inf')
        if now is None:
            now = _time.time()
        return now - self._last_observation_t

    def get_last_n_positions(self, n=3):
        """Ritorna le ultime n posizioni (piu' recenti per prima)."""
        if not self.history:
            return []
        return list(reversed(list(self.history)[-n:]))

    # ============================================================
    # METRICHE DERIVATE
    # ============================================================

    def stationary_time(self, window_sec=10.0, now=None):
        """
        Quanti secondi (negli ultimi `window_sec`) il player e' rimasto
        fermo (movimento sotto soglia). Utile per inferire "sta facendo
        una task".
        """
        if now is None:
            now = _time.time()
        if len(self.history) < 2:
            return 0.0

        total_stationary = 0.0
        snaps = [s for s in self.history if (now - s.t) <= window_sec]
        for i in range(1, len(snaps)):
            a = snaps[i - 1]
            b = snaps[i]
            dt = b.t - a.t
            if dt < STATIONARY_TIME_DELTA_SEC:
                continue
            dist = math.hypot(b.x - a.x, b.y - a.y)
            if dist < STATIONARY_THRESHOLD_DIST:
                total_stationary += dt
        return total_stationary

    def distance_traveled(self, window_sec=10.0, now=None):
        """Distanza totale percorsa negli ultimi `window_sec`."""
        if now is None:
            now = _time.time()
        if len(self.history) < 2:
            return 0.0
        snaps = [s for s in self.history if (now - s.t) <= window_sec]
        tot = 0.0
        for i in range(1, len(snaps)):
            tot += math.hypot(snaps[i].x - snaps[i-1].x,
                              snaps[i].y - snaps[i-1].y)
        return tot

    def is_currently_stationary(self, threshold_sec=1.0):
        """True se non si muove da almeno `threshold_sec` secondi."""
        if len(self.history) < 2:
            return False
        last = self.history[-1]
        for snap in reversed(self.history):
            if last.t - snap.t > threshold_sec:
                return math.hypot(last.x - snap.x, last.y - snap.y) < STATIONARY_THRESHOLD_DIST
        return False

    def stationary_for_seconds(self):
        """
        Da quanti secondi consecutivi il player e' fermo (sotto soglia
        di movimento). 0 se attualmente in movimento.
        """
        if len(self.history) < 2:
            return 0.0
        last = self.history[-1]
        accumulated = 0.0
        for snap in reversed(list(self.history)[:-1]):
            if math.hypot(last.x - snap.x, last.y - snap.y) > STATIONARY_THRESHOLD_DIST:
                break
            accumulated = last.t - snap.t
        return accumulated

    # ============================================================
    # SERIALIZZAZIONE LEGGERA (per UI)
    # ============================================================

    def to_brief_dict(self, now=None):
        """
        Snapshot leggero per la UI. Niente liste lunghe.
        """
        if now is None:
            now = _time.time()
        return {
            'name': self.name,
            'color': self.color,
            'is_dead': self.is_dead,
            'visible_now': self.is_visible_now(now),
            'seconds_since_seen': self.seconds_since_last_seen(now),
            'last_pos': ((self.last_snapshot.x, self.last_snapshot.y)
                         if self.last_snapshot else None),
            'last_stanza': (self.last_snapshot.stanza
                            if self.last_snapshot else None),
        }


class PlayerTracker:
    """
    Tracker centrale per tutti i player.

    Storico persistente: i player rilevati restano qui anche se non
    li vediamo piu', cosi' possiamo mostrare "visto X minuti fa in
    stanza Y".

    Cleanup: snapshot piu' vecchi di `HISTORY_MAX_AGE_SEC` vengono
    eliminati periodicamente (chiama `prune()` dal loop principale).
    """

    def __init__(self):
        # name (string) -> PlayerInfo
        # Usiamo il nome come chiave perche' YOLO assegna nomi
        # univoci per colore (es. "Rosso", "Blu"). Player "Unknown"
        # vengono raggruppati separatamente per colore (chiave =
        # tupla RGB).
        self._players = {}

    # ============================================================
    # API DI ALIMENTAZIONE
    # ============================================================

    def observe(self, name, x, y, color=(128, 128, 128),
                 t=None, stanza=None, is_dead=False):
        """
        Registra un'osservazione di un player.
        Chiamato dal sistema YOLO esistente (vedi yolo_scanner.py).
        """
        if t is None:
            t = _time.time()
        key = self._key_for(name, color)
        info = self._players.get(key)
        if info is None:
            info = PlayerInfo(name=name, color=color)
            self._players[key] = info
        info.observe(t, x, y, stanza=stanza, is_dead=is_dead, color=color)

    def _key_for(self, name, color):
        """
        Chiave per identificare un player nel dict.
        - Player con nome noto (es. "Rosso"): usa il nome
        - Player "Unknown": usa tupla colore RGB (piu' robusto fra scan)
        """
        if name and name != 'Unknown':
            return name
        return ('Unknown', color)

    # ============================================================
    # API DI QUERY
    # ============================================================

    def all_players(self):
        """Ritorna tutti i PlayerInfo conosciuti."""
        return list(self._players.values())

    def get(self, name_or_key):
        """Cerca per nome (o chiave Unknown-colore)."""
        return self._players.get(name_or_key)

    def visible_players(self, now=None, max_age=2.0):
        """Player rilevati negli ultimi `max_age` secondi."""
        return [p for p in self._players.values()
                if p.is_visible_now(now, max_age)]

    def dead_players(self):
        """Player marcati come morti (con cadavere visto)."""
        return [p for p in self._players.values() if p.is_dead]

    def count(self):
        return len(self._players)

    # ============================================================
    # MANUTENZIONE
    # ============================================================

    def prune(self, max_age=HISTORY_MAX_AGE_SEC, now=None):
        """
        Rimuove snapshot piu' vecchi di `max_age` da ogni player.
        Da chiamare ogni tot dal loop principale (es. ogni 5 s).
        Player senza snapshot rimasti vengono comunque conservati
        (con last_snapshot=None) per la cronologia.
        """
        if now is None:
            now = _time.time()
        for p in self._players.values():
            # Rimuovi snapshot vecchi dall'inizio della deque
            while p.history and (now - p.history[0].t) > max_age:
                p.history.popleft()

    def reset(self):
        """Cancella tutti i tracker. Da chiamare a inizio nuova partita."""
        self._players.clear()
