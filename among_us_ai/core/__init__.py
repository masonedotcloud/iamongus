"""
core: fondamenta del pacchetto.

Espone:
- :class:`GPSConfig`  : costanti globali (timing, soglie, modalita' esec, ecc.)
- :class:`Colors`     : palette UI (DPG)
- ``stop_flag``       : flag condiviso fra bot principale e subprocess delle task
- ``hex_to_rgba`` & friends : helper geometrici/colore riusati da UI ed esecuzione
- ``WIN_OK``          : flag che indica se le dipendenze Win32 sono disponibili

Tutto il resto del package importa da qui senza creare cicli.
"""

from . import stop_flag
from .config import GPSConfig, Colors, MAX_PREVIEW_W, MAX_PREVIEW_H
from .geometry import (
    hex_to_rgba,
    get_client_rect,
    point_in_polygon,
    random_point_in_rect,
    random_point_in_poly,
)
from .win_deps import WIN_OK

__all__ = [
    "GPSConfig", "Colors", "MAX_PREVIEW_W", "MAX_PREVIEW_H",
    "hex_to_rgba", "get_client_rect", "point_in_polygon",
    "random_point_in_rect", "random_point_in_poly",
    "WIN_OK", "stop_flag",
]
