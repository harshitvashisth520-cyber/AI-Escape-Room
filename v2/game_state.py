"""Version 2 — Structured game state.

The state is a plain Python dict that tracks:
- which objects have been examined
- which puzzles have been solved
- the player's inventory
- whether the door has been opened (win)

All mutations go through the methods below so the state stays consistent.
"""

from copy import deepcopy
from typing import Any, Dict, List


def initial_state(config: Dict[str, Any]) -> Dict[str, Any]:
    """Return a fresh game state derived from the config."""
    return {
        "examined": [],          # list of object names examined
        "solved": [],            # list of puzzle names solved
        "inventory": [],         # list of item ids collected
        "door_opened": False,
        "history": [],           # list of (player_action, outcome) for the LLM
    }


def serialize(state: Dict[str, Any]) -> str:
    """Return a compact human/LLM-readable summary of the state."""
    lines = [
        f"Examined: {state['examined'] or 'none'}",
        f"Solved: {state['solved'] or 'none'}",
        f"Inventory: {state['inventory'] or 'empty'}",
        f"Door opened: {state['door_opened']}",
    ]
    return "\n".join(lines)
