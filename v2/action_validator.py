"""Version 2 — Action validator (game rules live here, NOT in the LLM).

The validator parses the player's natural-language input into a structured
action, checks it against the game state, and returns a structured outcome.
The LLM is only used afterwards to *describe* the outcome in natural language.

This is what makes Version 2 reliable:
- The LLM cannot decide whether an action succeeds.
- Codes, keys, and win conditions are checked by Python.
- Invalid / impossible / adversarial actions are rejected before the LLM
  ever sees them.
"""

import re
from typing import Any, Dict, Optional, Tuple

from .game_state import serialize

# Action types the system understands.
ACTIONS = ("examine", "take", "use", "enter_code", "open", "look", "inventory", "help", "unknown")


def _resolve_object(text: str, config: Dict[str, Any]) -> Optional[str]:
    """Match a word/phrase in the text to a known object (using aliases)."""
    aliases = config.get("aliases", {})
    text_lower = text.lower()
    # Check longer aliases first so "book shelf" beats "book".
    for obj, alias_list in aliases.items():
        for alias in sorted(alias_list, key=len, reverse=True):
            if alias in text_lower:
                return obj
    return None


def _extract_code(text: str) -> Optional[str]:
    """Pull a 4-digit code out of the text if present."""
    match = re.search(r"\b(\d{4})\b", text)
    return match.group(1) if match else None


def _extract_item(text: str, state: Dict[str, Any], config: Dict[str, Any],
                  inventory_only: bool = True) -> Optional[str]:
    """Match an item name mentioned in the text.

    If inventory_only is True, only items currently held by the player match.
    If False, any configured item can match (used for 'take' commands where
    the player names an item they have just discovered).
    """
    text_lower = text.lower()
    item_ids = state["inventory"] if inventory_only else config["items"].keys()
    for item_id in item_ids:
        item_name = config["items"][item_id]["name"].lower()
        if item_name in text_lower or item_id in text_lower:
            return item_id
    return None


def parse_action(text: str, state: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """Convert natural language into a structured action dict.

    Returns: {"type": str, "object": str|None, "code": str|None, "item": str|None, "raw": text}
    """
    t = text.lower().strip()

    # Inventory / help
    if any(w in t for w in ("inventory", "what do i have", "what have i got", "items")):
        return {"type": "inventory", "object": None, "code": None, "item": None, "raw": text}
    if any(w in t for w in ("help", "hint", "what can i do")):
        return {"type": "help", "object": None, "code": None, "item": None, "raw": text}
    if any(w in t for w in ("look", "describe", "where am i", "room")):
        return {"type": "look", "object": None, "code": None, "item": None, "raw": text}

    obj = _resolve_object(text, config)
    code = _extract_code(text)
    item = _extract_item(text, state, config)  # inventory-only by default

    # Determine verb
    if any(w in t for w in ("examine", "look at", "inspect", "check", "read", "study")):
        return {"type": "examine", "object": obj, "code": code, "item": item, "raw": text}
    if any(w in t for w in ("take", "pick up", "grab", "collect")):
        # For 'take', the player may name an item they just discovered.
        item = _extract_item(text, state, config, inventory_only=False)
        return {"type": "take", "object": obj, "code": code, "item": item, "raw": text}
    if any(w in t for w in ("use", "try", "apply", "unlock with")):
        return {"type": "use", "object": obj, "code": code, "item": item, "raw": text}
    if any(w in t for w in ("enter", "type", "input", "code", "dial")) and code:
        return {"type": "enter_code", "object": obj, "code": code, "item": item, "raw": text}
    if any(w in t for w in ("open", "unlock")):
        return {"type": "open", "object": obj, "code": code, "item": item, "raw": text}

    # Fallback: if there's an object with no clear verb, assume examine.
    if obj:
        return {"type": "examine", "object": obj, "code": code, "item": item, "raw": text}
    return {"type": "unknown", "object": None, "code": None, "item": None, "raw": text}


def validate(action: Dict[str, Any], state: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """Validate an action against the rules and mutate state if valid.

    Returns an outcome dict:
        {"ok": bool, "message": str, "won": bool, "data": dict}
    """
    atype = action["type"]
    obj = action["object"]

    # ---- inventory ----
    if atype == "inventory":
        items = state["inventory"]
        if not items:
            return {"ok": True, "message": "Your pockets are empty.", "won": False, "data": {}}
        names = [config["items"][i]["name"] for i in items]
        return {"ok": True, "message": f"You are carrying: {', '.join(names)}.", "won": False, "data": {}}

    # ---- help ----
    if atype == "help":
        return {"ok": True, "message": (
            "You can examine objects, take items you find, use items, enter codes on locks, "
            "or open things. Try: 'examine bookshelf', 'take the key', 'enter 7391 on the drawer'."
        ), "won": False, "data": {}}

    # ---- look around ----
    if atype == "look":
        return {"ok": True, "message": config["intro"], "won": False, "data": {}}

    # ---- unknown ----
    if atype == "unknown":
        return {"ok": False, "message": "I don't understand that action. Try examining an object, taking an item, or entering a code.", "won": False, "data": {}}

    # ---- take (item-based, may not name an object) ----
    if atype == "take":
        return _handle_take(action, state, config)

    # From here on, every action needs a valid object.
    if not obj:
        return {"ok": False, "message": "There is nothing like that here.", "won": False, "data": {}}

    if obj not in config["objects"]:
        return {"ok": False, "message": f"There is no '{obj}' in the room.", "won": False, "data": {}}

    # ---- examine ----
    if atype == "examine":
        if obj not in state["examined"]:
            state["examined"].append(obj)
        msg = config["objects"][obj]["examine"]

        # Examining the bookshelf solves its puzzle (reveals numbers).
        if obj == "bookshelf" and "bookshelf" not in state["solved"]:
            state["solved"].append("bookshelf")
        # Examining the painting reveals the brass key and solves that puzzle.
        if obj == "painting" and "painting" not in state["solved"]:
            state["solved"].append("painting")
        return {"ok": True, "message": msg, "won": False, "data": {"object": obj}}

    # ---- open ----
    if atype == "open":
        if obj == "drawer":
            return _open_drawer(action, state, config)
        if obj == "door":
            return _open_door(action, state, config)
        return {"ok": False, "message": f"You can't open the {obj}.", "won": False, "data": {}}

    # ---- use (item on object) ----
    if atype == "use":
        item = action["item"]
        if not item:
            return {"ok": False, "message": "Use what? You don't have that item.", "won": False, "data": {}}
        if item not in state["inventory"]:
            return {"ok": False, "message": f"You don't have a {config['items'][item]['name']}.", "won": False, "data": {}}
        if item == "brass_key" and obj == "drawer":
            return _open_drawer(action, state, config, by_key=True)
        if item == "drawer_note" and obj == "door":
            # The note just reminds the player of the code; it doesn't auto-open the door.
            return {"ok": True, "message": "The note reads: 'The door code is 2 4 6 8.' You'll need to enter it on the keypad.", "won": False, "data": {}}
        return {"ok": False, "message": f"Using the {config['items'][item]['name']} on the {obj} does nothing.", "won": False, "data": {}}

    # ---- enter code ----
    if atype == "enter_code":
        if obj == "drawer":
            return _open_drawer(action, state, config)
        if obj == "door":
            return _open_door(action, state, config)
        return {"ok": False, "message": f"There is no code lock on the {obj}.", "won": False, "data": {}}

    return {"ok": False, "message": "That action isn't possible here.", "won": False, "data": {}}


def _handle_take(action: Dict[str, Any], state: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """Handle 'take' actions, whether the player names an object or an item."""
    obj = action.get("object")
    item = action.get("item")

    # Map of item_id -> (source_puzzle, success_message)
    item_sources = {
        "brass_key": ("painting", "You take the small brass key from behind the painting."),
        "drawer_note": ("drawer", "You pocket the folded note from the drawer."),
    }

    # If the player named an item directly (e.g. "take the brass key").
    if item and item in item_sources:
        source, msg = item_sources[item]
        if source not in state["solved"]:
            return {"ok": False, "message": f"You haven't found the {config['items'][item]['name'].lower()} yet.", "won": False, "data": {}}
        if item in state["inventory"]:
            return {"ok": False, "message": f"You already have the {config['items'][item]['name'].lower()}.", "won": False, "data": {}}
        state["inventory"].append(item)
        return {"ok": True, "message": msg, "won": False, "data": {"item": item}}

    # If the player named an object (e.g. "take from the painting").
    if obj == "painting":
        return _handle_take({"object": obj, "item": "brass_key"}, state, config)
    if obj == "drawer":
        return _handle_take({"object": obj, "item": "drawer_note"}, state, config)

    target = obj or "that"
    return {"ok": False, "message": f"There is nothing to take from the {target}.", "won": False, "data": {}}


def _open_drawer(action: Dict[str, Any], state: Dict[str, Any], config: Dict[str, Any], by_key: bool = False) -> Dict[str, Any]:
    if "drawer" in state["solved"]:
        return {"ok": True, "message": "The drawer is already open. Inside is a folded note (if you haven't taken it).", "won": False, "data": {}}

    if by_key:
        if "brass_key" not in state["inventory"]:
            return {"ok": False, "message": "You don't have a key to open the drawer.", "won": False, "data": {}}
        state["solved"].append("drawer")
        return {"ok": True, "message": "The brass key turns smoothly. The drawer creaks open. Inside is a folded note.", "won": False, "data": {}}

    code = action.get("code")
    correct = config["puzzles"]["drawer"]["code"]
    if not code:
        return {"ok": False, "message": "Enter the four-digit code on the drawer's dial to open it.", "won": False, "data": {}}
    if code != correct:
        return {"ok": False, "message": f"You dial {code}. The drawer stays firmly locked — that's not the right code.", "won": False, "data": {}}
    state["solved"].append("drawer")
    return {"ok": True, "message": f"You dial {code}. Click! The drawer unlocks and slides open. Inside is a folded note.", "won": False, "data": {}}


def _open_door(action: Dict[str, Any], state: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    if state["door_opened"]:
        return {"ok": True, "message": "The door is already open. You have escaped!", "won": True, "data": {}}

    code = action.get("code")
    correct = config["puzzles"]["door"]["code"]
    if not code:
        return {"ok": False, "message": "The door's keypad awaits a four-digit code.", "won": False, "data": {}}
    if code != correct:
        return {"ok": False, "message": f"You enter {code}. The red light flashes — wrong code. The door remains locked.", "won": False, "data": {}}
    state["door_opened"] = True
    if "door" not in state["solved"]:
        state["solved"].append("door")
    return {"ok": True, "message": f"You enter {code}. The red light turns green, and with a heavy thud the door unlocks. You step out into the light — you have ESCAPED!", "won": True, "data": {}}


def build_llm_context(action: Dict[str, Any], outcome: Dict[str, Any], state: Dict[str, Any], config: Dict[str, Any]) -> str:
    """Build a context block for the LLM that describes ONLY the validated outcome.

    The LLM is told the true outcome and the current state; its job is to
    narrate it. It is explicitly forbidden to change the outcome or invent
    new facts.
    """
    return f"""GAME STATE:
{serialize(state)}

PLAYER ACTION: {action['raw']}

VALIDATED OUTCOME (this is ground truth — do NOT contradict it):
ok={outcome['ok']}
message={outcome['message']}
won={outcome['won']}

Your job: rewrite the validated outcome as a short, atmospheric Game Master
narration (2-3 sentences). You MUST NOT:
- change whether the action succeeded
- reveal codes or clues the player has not discovered
- invent objects or items
- unlock anything the validator said stays locked

If the outcome says the action failed, narrate the failure. If it says the
player escaped, confirm the escape."""
