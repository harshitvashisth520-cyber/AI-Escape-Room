"""Version 2 — Reliable AI Escape Room (validated state + LLM narration).

Architecture:
  Player input
      |
      v
  parse_action()  -> structured action
      |
      v
  validate()      -> Python decides success/failure, mutates state
      |
      v
  LLM narrates ONLY the validated outcome (cannot change the result)

The LLM never decides whether an action succeeds. All game rules (codes,
keys, inventory, win condition) live in action_validator.py.
"""

import json
import os
from pathlib import Path

import streamlit as st

import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from shared.llm_client import LLMClient
from v2.game_state import initial_state, serialize
from v2.action_validator import parse_action, validate, build_llm_context

CONFIG_PATH = ROOT / "shared" / "game_config.json"


def init_state():
    if "config" not in st.session_state:
        st.session_state.config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if "state" not in st.session_state:
        st.session_state.state = initial_state(st.session_state.config)
    if "messages" not in st.session_state:
        st.session_state.messages = [
            {"role": "assistant", "content": st.session_state.config["intro"]}
        ]
    if "escaped" not in st.session_state:
        st.session_state.escaped = False


def restart():
    st.session_state.clear()
    init_state()


def main():
    st.set_page_config(page_title="Escape Room — Version 2 (Validated)", page_icon="🛡️")
    st.title("🛡️ AI Escape Room — Version 2")
    st.caption("Python validates all actions; LLM only narrates the outcome.")

    init_state()

    api_key = st.sidebar.text_input("Gemini API Key", type="password",
                                    value=os.getenv("GEMINI_API_KEY", ""))
    use_llm = st.sidebar.checkbox("Use LLM narration (uncheck for raw validator output)", value=True)

    col1, col2 = st.sidebar.columns(2)
    if col1.button("🔄 Restart"):
        restart()
        st.rerun()

    # Live state panel (so the player can see the structured state).
    st.sidebar.markdown("### 📊 Game State")
    st.sidebar.code(serialize(st.session_state.state), language="text")

    # Conversation.
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    if st.session_state.escaped:
        st.success("🎉 You escaped! Click Restart to play again.")
        return

    player_input = st.chat_input("What do you do?")
    if not player_input:
        return

    st.session_state.messages.append({"role": "user", "content": player_input})
    with st.chat_message("user"):
        st.write(player_input)

    # --- VALIDATION (Python, not the LLM) ---
    action = parse_action(player_input, st.session_state.state, st.session_state.config)
    outcome = validate(action, st.session_state.state, st.session_state.config)

    # --- NARRATION (LLM, but only of the validated outcome) ---
    narration = outcome["message"]
    if use_llm and api_key:
        with st.spinner("Game Master is narrating..."):
            try:
                client = LLMClient(api_key=api_key)
                context = build_llm_context(
                    action, outcome, st.session_state.state, st.session_state.config
                )
                narration = client.generate(context, temperature=0.6)
            except Exception as e:
                narration = outcome["message"]  # fall back to raw message
                st.sidebar.warning(f"LLM narration failed, using raw output: {e}")
    elif not api_key:
        st.sidebar.info("No API key — showing raw validator output.")

    st.session_state.messages.append({"role": "assistant", "content": narration})
    with st.chat_message("assistant"):
        st.write(narration)

    if outcome.get("won"):
        st.session_state.escaped = True
        st.success("🎉 You escaped the locked library!")


if __name__ == "__main__":
    main()
