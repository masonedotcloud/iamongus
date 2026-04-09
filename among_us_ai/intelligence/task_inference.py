"""
TaskInference: deduce quali task ha probabilmente fatto un player
in base alla sua posizione e tempo di fermata.

Logica:
- Se un player si ferma per > N s entro radius R da una task
  registrata, probabilmente l'ha fatta.
- Multiple fermate vicino alla stessa task entro un range temporale
  contano come UNA sola task (no doppio conteggio).

Note importanti:
- Il "task inferita" e' un'EURISTICA, non una certezza. Un player
  fermo vicino a una task potrebbe semplicemente passare di li' o
  aspettare.
- Le task con cooldown interno (Submit Scan, Empty Garbage) richiedono
  fermata piu' lunga e vengono pesate di piu'.
"""

import math
import time as _time


# Configurazione default
TASK_RADIUS = 0.8           # entro quanto considerare "alla task" (stretto:
                            # il player deve essere praticamente sul punto)
MIN_STOP_DURATION = 1.5     # fermo per almeno N s per inferire task
DEDUP_WINDOW_SEC = 30.0     # stessa task < N s = una sola task


class InferredTask:
    """Una task probabilmente fatta da un player."""

    __slots__ = ('t', 'task_id', 'task_name', 'pos', 'duration', 'confidence')

    def __init__(self, t, task_id, task_name, pos, duration, confidence):
        self.t = t              # timestamp di inferenza
        self.task_id = task_id  # id task registrata
        self.task_name = task_name
        self.pos = pos          # (x, y) del player al momento
        self.duration = duration  # quanto tempo e' rimasto fermo
        self.confidence = confidence  # 0-1, quanto sono sicuro

    def __repr__(self):
        return (f"<InferredTask '{self.task_name}' "
                f"t={self.t:.0f} dur={self.duration:.1f}s "
                f"conf={self.confidence:.2f}>")


class TaskInference:
    """
    Inferisce task fatte dai player guardando le loro fermate.

    Usage:
        ti = TaskInference(task_list_with_pos)  # da task_mgr
        ti.update(tracker, now)
        ti.tasks_of(player_name) -> list[InferredTask]
    """

    def __init__(self, task_list=None):
        """
        :param task_list: lista di dict con 'id', 'nome', 'x', 'y',
            'lunghezza' (per pesare il conteggio).
        """
        self.task_list = task_list or []
        # player_name -> list of InferredTask
        self._inferred = {}

    def set_task_list(self, task_list):
        """Aggiorna la lista delle task (es. dopo reload)."""
        self.task_list = task_list

    # ============================================================
    # UPDATE
    # ============================================================

    def update(self, tracker, now=None):
        """
        Per ogni player, vede se sta facendo una task in base alla
        sua posizione + fermata.
        """
        if now is None:
            now = _time.time()
        for player in tracker.all_players():
            if player.is_dead:
                continue
            if not player.last_snapshot:
                continue
            # Per inferire una task il player deve essere FERMO da N s
            stop_sec = player.stationary_for_seconds()
            if stop_sec < MIN_STOP_DURATION:
                continue
            # Trova task vicina alla posizione attuale
            lp = player.last_snapshot
            best_task = None
            best_dist = float('inf')
            for task in self.task_list:
                dist = math.hypot(lp.x - task.get('x', 0),
                                   lp.y - task.get('y', 0))
                if dist > TASK_RADIUS:
                    continue
                if dist < best_dist:
                    best_dist = dist
                    best_task = task
            if not best_task:
                continue
            # Anti-duplicato: stessa task nei ultimi DEDUP_WINDOW_SEC?
            past = self._inferred.get(player.name, [])
            already = any(
                inf.task_id == best_task.get('id')
                and (lp.t - inf.t) < DEDUP_WINDOW_SEC
                for inf in past
            )
            if already:
                continue
            # Confidence: pondera in base alla durata della fermata e
            # alla lunghezza della task.
            lung = best_task.get('lunghezza', 'Short')
            expected = {'Long': 5.0, 'Common': 2.0, 'Short': 1.5,
                        'N/A': 1.5}.get(lung, 2.0)
            confidence = min(1.0, stop_sec / expected)
            inferred = InferredTask(
                t=lp.t,
                task_id=best_task.get('id'),
                task_name=best_task.get('nome', '?'),
                pos=(lp.x, lp.y),
                duration=stop_sec,
                confidence=confidence,
            )
            self._inferred.setdefault(player.name, []).append(inferred)

    # ============================================================
    # API DI QUERY
    # ============================================================

    def tasks_of(self, player_name):
        """Lista delle task inferite per un player."""
        return list(self._inferred.get(player_name, []))

    def task_count(self, player_name):
        """Quante task abbiamo inferito."""
        return len(self._inferred.get(player_name, []))

    def reset(self):
        """Reset a inizio nuova partita."""
        self._inferred.clear()
