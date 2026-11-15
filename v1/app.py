"""Version 1 — Interactive AI Escape Room (LLM-driven).

This version hands almost all game logic to the LLM. The system prompt
contains the room description, objects, puzzles and win condition. The LLM
decides whether actions succeed, what the player finds, and when the game
is won.

Because there is no structured state or validation, this version can be
unreliable: the LLM may forget previous actions, invent objects, reveal
clues too early, or allow impossible actions.
"""

import json
import os
from pathlib import Path

import streamlit as st

# Allow importing the shared package regardless of where streamlit is run from.
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from shared.llm_client import LLMClient

CONFIG_PATH = ROOT / "shared" / "game_config.json"


def build_system_prompt(config: dict) -> str:
    """Build the Game Master system prompt from the game config."""
    objects = config["objects"]
    puzzles = config["puzzles"]
    door_code = puzzles["door"]["code"]
    drawer_code = puzzles["drawer"]["code"]

    object_descriptions = "\n".join(
        f"- {name}: {data['description']}" for name, data in objects.items()
    )

    return f"""You are the Game Master of an escape room called "{config['room_name']}".

INTRODUCTION:
{config['intro']}

THE ROOM CONTAINS THESE INTERACTIVE OBJECTS:
{object_descriptions}

PUZZLES AND SOLUTIONS (you must enforce these):
- The bookshelf, when examined, reveals four numbers: 7, 3, 9, 1 (in that order).
- The painting, when examined, reveals a small brass key hidden behind it.
- The drawer can be opened in two ways:
    (a) entering the four-digit code {drawer_code} on its dial, OR
    (b) using the brass key (which the player must first obtain from behind the painting).
  Inside the drawer is a folded note that reads: "The door code is 2 4 6 8."
- The door is the final exit. It opens ONLY when the player enters the code {door_code} on its keypad.

RULES YOU MUST FOLLOW:
- Describe the environment and respond to the player's actions in a natural, engaging way.
- Only reveal information when the player examines or interacts with the relevant object.
- The player can examine objects, collect items they find, and attempt puzzles.
- Track what the player has done and collected.
- When the player successfully opens the door with code {door_code}, declare that they have ESCAPED and the game is won.
- Do NOT reveal secret codes or solutions unless the player has legitimately discovered them.
- Keep responses concise (2-4 sentences)."""


def init_state():
    if "messages" not in st.session_state:
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        st.session_state.config = config
        st.session_state.messages = [
            {"role": "system", "content": build_system_prompt(config)},
            {"role": "assistant", "content": config["intro"]},
        ]
        st.session_state.escaped = False


def restart():
    st.session_state.clear()
    init_state()


def main():
    st.set_page_config(page_title="Escape Room — Version 1 (LLM-driven)", page_icon="🔑")
    st.title("🔑 AI Escape Room — Version 1")
    st.caption("LLM acts as Game Master. No structured state or validation.")

    init_state()

    # API key input (so the app works without a pre-set env var).
    api_key = st.sidebar.text_input("Gemini API Key", type="password",
                                    value=os.getenv("GEMINI_API_KEY", ""))
    if st.sidebar.button("🔄 Restart Game"):
        restart()
        st.rerun()

    # Show conversation.
    for msg in st.session_state.messages:
        if msg["role"] == "system":
            continue
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    if st.session_state.escaped:
        st.success("🎉 You escaped! Click Restart to play again.")
        return

    player_input = st.chat_input("What do you do?")
    if not player_input:
        return

    if not api_key:
        st.error("Please enter your Gemini API key in the sidebar.")
        return

    st.session_state.messages.append({"role": "user", "content": player_input})
    with st.chat_message("user"):
        st.write(player_input)

    with st.spinner("Game Master is thinking..."):
        try:
            client = LLMClient(api_key=api_key)
            reply = client.chat(st.session_state.messages)
        except Exception as e:
            reply = f"⚠️ LLM error: {e}"

    st.session_state.messages.append({"role": "assistant", "content": reply})
    with st.chat_message("assistant"):
        st.write(reply)

    # V1 has no structured win detection — we let the LLM declare it.
    if "escaped" in reply.lower() or "you escape" in reply.lower():
        st.session_state.escaped = True


if __name__ == "__main__":
    main()
