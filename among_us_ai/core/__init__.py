"""Configurazione, dipendenze e utilities geometriche di base."""

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
