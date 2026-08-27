from __future__ import annotations

from pathlib import Path
import tempfile

import cv2
import streamlit as st

from snooker_vision.application import P0Application
from snooker_vision.config import load_config
from snooker_vision.demo import run_recorded_event_demo
from snooker_vision.domain.models import SystemStatus
from snooker_vision.input import FrameSource, FrameSourceError
from snooker_vision.logging_config import configure_logging
from snooker_vision.scoring import PlayerSwitchLocked


st.set_page_config(page_title="Snooker Vision P0", layout="wide")


def _new_application() -> P0Application:
    config = load_config()
    configure_logging(str(config["app"]["log_level"]), str(config["app"]["log_file"]))
    return P0Application(config)


if "p0_app" not in st.session_state:
    st.session_state.p0_app = _new_application()
if "frame_source" not in st.session_state:
    st.session_state.frame_source = None
if "last_frame" not in st.session_state:
    st.session_state.last_frame = None

app: P0Application = st.session_state.p0_app

st.title("斯诺克视觉自动计分系统 — P0")

with st.sidebar:
    st.subheader("Input & Calibration")
    source_text = st.text_input("Video path or camera index", value="0")
    calibration_path = st.text_input("Calibration JSON", value="config/calibration.json")
    uploaded = st.file_uploader("Optional video upload", type=["mp4", "avi", "mov", "mkv"])
    if uploaded is not None:
        suffix = Path(uploaded.name).suffix
        temp_path = Path(tempfile.gettempdir()) / f"snooker_vision_upload{suffix}"
        temp_path.write_bytes(uploaded.getbuffer())
        source_text = str(temp_path)
        st.caption(f"Uploaded source: {temp_path}")
    if st.button("Open source", use_container_width=True):
        try:
            if st.session_state.frame_source is not None:
                st.session_state.frame_source.release()
            app.load_calibration(calibration_path)
            st.session_state.frame_source = FrameSource(source_text).open()
            st.success("Source and calibration ready")
        except Exception as exc:
            st.session_state.frame_source = None
            st.error(str(exc))
    st.divider()
    if st.button("Run deterministic P0 demo", use_container_width=True):
        st.session_state.p0_app = _new_application()
        app = st.session_state.p0_app
        result = run_recorded_event_demo(app)
        st.success(f"Demo: 0 → {result['after_red']} → {result['after_black']} → {result['after_undo']}")


def process_frames(count: int) -> None:
    source: FrameSource | None = st.session_state.frame_source
    if source is None:
        st.error("Open a source first")
        return
    for _ in range(count):
        packet = source.read()
        if packet is None:
            app.status = SystemStatus.CAMERA_ERROR
            app.message = "Camera disconnected or video ended"
            st.warning(app.message)
            break
        app.process_frame(packet.frame, packet.timestamp, packet.frame_index)
        st.session_state.last_frame = packet.frame


control_a, control_b, control_c, control_d = st.columns(4)
with control_a:
    if st.button("Process next frame", use_container_width=True):
        process_frames(1)
with control_b:
    if st.button("Process 100 frames", use_container_width=True):
        process_frames(100)
with control_c:
    if st.button("Switch Player", use_container_width=True):
        try:
            app.switch_player()
        except PlayerSwitchLocked as exc:
            st.warning(str(exc))
with control_d:
    if st.button("Undo", use_container_width=True):
        app.undo()

view = app.view_state()
score_a, current, score_b = st.columns([2, 1, 2])
score_a.metric("Player A", view.scoreboard.player_a_score)
current.metric("Current Player", view.scoreboard.current_player.value.replace("PLAYER_", ""))
score_b.metric("Player B", view.scoreboard.player_b_score)

status_a, status_b, status_c = st.columns(3)
status_a.metric("System State", view.system_status.value)
status_b.metric("Motion", view.motion)
status_c.metric("Current Break", view.scoreboard.current_break)
st.info(view.message)

video_col, event_col = st.columns([3, 2])
with video_col:
    if st.session_state.last_frame is not None:
        st.image(cv2.cvtColor(st.session_state.last_frame, cv2.COLOR_BGR2RGB), caption="Latest input frame")
    else:
        st.caption("No frame processed yet")
with event_col:
    st.subheader("Last Event")
    st.write("Last Shot", view.last_shot.shot_id if view.last_shot else "—")
    st.write("Last Potted Ball", view.last_pot.ball_color.value if view.last_pot else "—")
    st.write("Score Delta", view.last_score_event.score_delta if view.last_score_event else 0)
    st.write("Confidence", view.last_pot.confidence if view.last_pot else "—")
    st.write("Review Status", "REQUIRED" if view.review_events else "CLEAR")

if view.review_events:
    st.subheader("Pot candidates requiring review")
    for pending in view.review_events:
        left, middle, right = st.columns([3, 1, 1])
        left.write(f"{pending.ball_color.value} ×{pending.count} — confidence {pending.confidence:.2f}")
        if middle.button("Confirm", key=f"confirm-{pending.event_id}"):
            app.confirm_pot(pending.event_id)
            st.rerun()
        if right.button("Reject", key=f"reject-{pending.event_id}"):
            app.reject_pot(pending.event_id)
            st.rerun()
