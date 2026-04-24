"""
game_io: lettura della memoria RAM di Among Us via ``pymem``.

Espone tre reader, tutti basati sulla stessa istanza di Pymem:

- :class:`AmongUsMemoryReader`    : posizione (x, y) del giocatore locale
- :class:`AmongUsTaskReader`      : lista task del giocatore (tipo, progress, done)
- :class:`AmongUsGameStateReader` : stato di alto livello del gioco
                                    (in_game, voting, dead, impostor, ecc.)

Tutti richiedono Windows + ``pymem`` installato + Among Us in esecuzione.
"""

from .memory_reader import (
    AmongUsMemoryReader,
    AmongUsTaskReader,
    AmongUsGameStateReader,
)

__all__ = [
    "AmongUsMemoryReader",
    "AmongUsTaskReader",
    "AmongUsGameStateReader",
]
