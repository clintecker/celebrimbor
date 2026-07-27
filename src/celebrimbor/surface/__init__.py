"""Surface inventory, role inference, and the surface map.

The completeness guarantee lives here: the harness knows every public callable
in the application, and every one of them is accounted for in a ratified map.
"""

from __future__ import annotations

from .inventory import CallableInfo, Inventory, ModuleInfo, inventory
from .map import SurfaceMap, SurfaceRow, load_map, render_map, write_map

__all__ = [
    "CallableInfo",
    "Inventory",
    "ModuleInfo",
    "SurfaceMap",
    "SurfaceRow",
    "inventory",
    "load_map",
    "render_map",
    "write_map",
]
