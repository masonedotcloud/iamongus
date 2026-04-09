"""
intelligence: sistema di analisi dei player in tempo reale.

Sottopackage MODULARE che NON tocca il resto del bot: si alimenta
delle detection esistenti (`yolo_scanner`) e produce informazioni
strategiche per il giocatore.

Componenti:
- PlayerTracker: storia delle posizioni di ogni player visto
- ActivityDetector: rileva eventi sospetti (vent, fermate, ecc.)
- ProximityAnalyzer: misura chi mi segue di piu'
- TaskInference: deduce task fatte dai player
- SuspicionAnalyzer: combina tutto in uno score 0-100% di sospettosita'

Uso tipico:
    from among_us_ai.intelligence import (
        PlayerTracker, ActivityDetector,
        ProximityAnalyzer, TaskInference, SuspicionAnalyzer
    )

    tracker = PlayerTracker()
    activity = ActivityDetector()
    proximity = ProximityAnalyzer()
    task_inf = TaskInference(task_list=[...])
    suspicion = SuspicionAnalyzer()

    # Loop:
    tracker.observe(name="Rosso", x=10, y=20, color=(255,0,0))
    activity.update(tracker)
    proximity.update(tracker, bot_pos=(0, 0))
    task_inf.update(tracker)
    scores = suspicion.analyze_all(tracker, activity, proximity, task_inf)
    # scores[0].player_name, scores[0].score, scores[0].factors
"""

from .player_tracker import (
    PlayerTracker, PlayerInfo, PlayerSnapshot,
)
from .activity_detector import (
    ActivityDetector, ActivityEvent,
    EV_VENT_USE, EV_STOP, EV_NEAR_BODY, EV_ERRATIC_MOVE,
)
from .proximity_analyzer import (
    ProximityAnalyzer,
)
from .task_inference import (
    TaskInference, InferredTask,
)
from .suspicion_analyzer import (
    SuspicionAnalyzer, SuspicionScore,
)

__all__ = [
    # Tracker
    'PlayerTracker', 'PlayerInfo', 'PlayerSnapshot',
    # Activity
    'ActivityDetector', 'ActivityEvent',
    'EV_VENT_USE', 'EV_STOP', 'EV_NEAR_BODY', 'EV_ERRATIC_MOVE',
    # Proximity
    'ProximityAnalyzer',
    # Task
    'TaskInference', 'InferredTask',
    # Suspicion
    'SuspicionAnalyzer', 'SuspicionScore',
]
