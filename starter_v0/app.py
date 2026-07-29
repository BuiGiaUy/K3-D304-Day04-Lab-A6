"""Streamlit UI cho Research Agent (Day 04 Lab).

UI này KHÔNG tự viết agent loop riêng — nó tái sử dụng `run_model_tool_loop` trong
`chat.py`, nên UI, CLI (`chat.py`) và eval (`run_eval.py`) dùng chung system prompt,
tool declarations và cách log transcript.

Chạy:  streamlit run app.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from chat import now_iso, run_model_tool_loop, safe_slug, trim_history, write_transcript
from providers import make_provider
from tools import load_tool_declarations, to_openai_tools
from versioning import artifact_version_dict, build_artifact_version

ARTIFACTS_DIR = ROOT / "artifacts"
TRANSCRIPTS_DIR = ROOT / "transcripts"

st.set_page_config(page_title="Research Agent — Day04 Lab", page_icon="🔎", layout="wide")


@st.cache_resource
def get_provider(name: str) -> Any:
    return make_provider(name)


def load_artifacts(prompt_path: Path, tools_path: Path) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    """Đọc lại mỗi lần chạy — team sửa prompt/tools liên tục và cần thấy hiệu lực ngay."""
    system_prompt = prompt_path.read_text(encoding="utf-8")
    declarations = load_tool_declarations(tools_path)
    return system_prompt, declarations, to_openai_tools(declarations)


def json_block(value: Any, max_chars: int = 4000) -> str:
    text = json.dumps(value, ensure_ascii=False, indent=2, default=str)
    return text if len(text) <= max_chars else text[:max_chars] + "\n...<truncated>"


def render_tool_events(rounds: list[dict[str, Any]]) -> None:
    """Trace bắt buộc trên UI: tool name, args, round, status, result/error."""
    for round_record in rounds:
        index = round_record.get("round")
        calls = round_record.get("tool_calls") or []
        if not calls:
            st.caption(f"Round {index} — không gọi tool, agent trả lời trực tiếp.")
            continue
        for event in round_record.get("tool_results") or []:
            result = event.get("result")
            has_error = isinstance(result, dict) and (result.get("error") or result.get("status") == "needs_confirmation")
            icon = "⚠️" if has_error else "✅"
            name = event.get("tool")
            with st.expander(f"{icon} Round {index} · `{name}`", expanded=has_error):
                st.markdown("**Arguments**")
                st.code(json_block(event.get("args")), language="json")
                st.markdown("**Result**")
                if isinstance(result, dict) and result.get("error"):
                    st.error(f"{result.get('error')}: {result.get('message', '')}")
                st.code(json_block(result), language="json")


# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("Cấu hình")
    provider_name = st.selectbox("Provider", ["gemini", "openrouter", "openai", "anthropic"], index=0)
    version_label = st.text_input("Version label", value="v0", help="Nhãn artifact, ví dụ v0/v1/v2/v3.")
    model_override = st.text_input("Model (để trống = mặc định)", value="")
    history_window = st.number_input("History window", 1, 20, 5)
    max_tool_rounds = st.number_input("Max tool rounds", 1, 10, 4)

    prompt_path = ARTIFACTS_DIR / "system_prompt.md"
    tools_path = ARTIFACTS_DIR / "tools.yaml"
    system_prompt, declarations, openai_tools = load_artifacts(prompt_path, tools_path)
    artifact_version = build_artifact_version(version_label, prompt_path, tools_path)

    st.divider()
    st.subheader("Artifact đang chạy")
    st.code(artifact_version.artifact_version, language="text")
    st.caption(f"prompt_hash `{artifact_version.prompt_hash[:12]}` · tools_hash `{artifact_version.tools_hash[:12]}`")
    st.caption(f"{len(declarations)} tool: " + ", ".join(item["name"] for item in declarations))

    if st.button("🔄 Bắt đầu phiên mới", use_container_width=True):
        for key in ("history", "turns", "transcript", "transcript_path"):
            st.session_state.pop(key, None)
        st.rerun()

# --------------------------------------------------- transcript / session state
session_key = f"{version_label}|{provider_name}|{model_override}"
if st.session_state.get("session_key") != session_key:
    st.session_state["session_key"] = session_key
    st.session_state.pop("transcript", None)
    st.session_state.pop("transcript_path", None)
    st.session_state["history"] = []
    st.session_state["turns"] = []

provider = get_provider(provider_name)
selected_model = model_override.strip() or getattr(provider, "default_model", None)

if "transcript" not in st.session_state:
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
    transcript_id = "_".join([safe_slug(version_label), safe_slug(provider_name), "ui", timestamp])
    st.session_state["transcript_path"] = TRANSCRIPTS_DIR / f"{transcript_id}.transcript.json"
    st.session_state["transcript"] = {
        "transcript_id": transcript_id,
        **artifact_version_dict(artifact_version),
        "provider": provider_name,
        "model": selected_model,
        "surface": "streamlit_ui",
        "system_prompt": str(prompt_path),
        "tools": str(tools_path),
        "history_window": int(history_window),
        "max_tool_rounds": int(max_tool_rounds),
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "turns": [],
    }

# ---------------------------------------------------------------- main
st.title("🔎 Research Agent")
st.caption(
    f"provider **{provider_name}** · model **{selected_model}** · artifact **{artifact_version.artifact_version}**"
)

for turn in st.session_state["turns"]:
    with st.chat_message("user"):
        st.write(turn["user"])
    with st.chat_message("assistant"):
        if turn.get("status") == "provider_error":
            st.error(turn.get("error"))
        else:
            st.write(turn.get("assistant_text") or "")
            if turn.get("status") == "waiting_for_user":
                st.info("Agent đang chờ bạn bổ sung thông tin.")
            render_tool_events(turn.get("rounds") or [])

if user_text := st.chat_input("Nhập yêu cầu research..."):
    with st.chat_message("user"):
        st.write(user_text)

    messages = [
        {"role": "system", "content": system_prompt},
        *trim_history(st.session_state["history"], int(history_window)),
        {"role": "user", "content": user_text},
    ]
    turn_record: dict[str, Any] = {
        "turn_index": len(st.session_state["turns"]) + 1,
        "started_at": now_iso(),
        "user": user_text,
        "status": "started",
        "assistant_text": None,
        "rounds": [],
        "tool_events": [],
    }

    with st.chat_message("assistant"):
        with st.spinner("Agent đang chọn tool và chạy..."):
            try:
                result = run_model_tool_loop(
                    provider=provider,
                    messages=messages,
                    tools=openai_tools,
                    model=model_override.strip() or None,
                    max_tool_rounds=int(max_tool_rounds),
                )
                turn_record.update(result)
                assistant_text = result["assistant_text"]
                st.write(assistant_text)
                if result["status"] == "waiting_for_user":
                    st.info("Agent đang chờ bạn bổ sung thông tin.")
                elif result["status"] == "max_tool_rounds":
                    st.warning(f"Dừng sau {max_tool_rounds} tool round.")
                render_tool_events(result["rounds"])
                st.session_state["history"].append({"role": "user", "content": user_text})
                st.session_state["history"].append({"role": "assistant", "content": assistant_text})
            except Exception as exc:
                turn_record.update({"status": "provider_error", "error": f"{type(exc).__name__}: {exc}"})
                st.error(turn_record["error"])

    turn_record["ended_at"] = now_iso()
    st.session_state["turns"].append(turn_record)
    st.session_state["transcript"]["turns"].append(turn_record)
    write_transcript(st.session_state["transcript_path"], st.session_state["transcript"])

if st.session_state["turns"]:
    st.divider()
    st.caption(f"Transcript: `{st.session_state['transcript_path'].relative_to(ROOT)}`")
    with st.expander("Xem transcript JSON (evidence để nộp)"):
        st.code(json_block(st.session_state["transcript"], max_chars=20000), language="json")
