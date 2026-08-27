from __future__ import annotations

from pathlib import Path
import tempfile

import cv2
import streamlit as st

from snooker_vision.application import P1Application
from snooker_vision.config import load_config
from snooker_vision.domain.models import FrameStatus, MatchStatus, SystemStatus, event_to_dict
from snooker_vision.input import FrameSource, FrameSourceError
from snooker_vision.logging_config import configure_logging
from snooker_vision.rules import RulesError


st.set_page_config(page_title="Snooker Vision P1", layout="wide")


def _new_application() -> P1Application:
    config = load_config()
    configure_logging(str(config["app"]["log_level"]), str(config["app"]["log_file"]))
    storage_dir = Path("data/processed/p1-active-match")
    snapshot_path = storage_dir / "active-match.json"
    event_log_path = storage_dir / "match-events.jsonl"
    if snapshot_path.exists():
        try:
            return P1Application.restore(config, snapshot_path, event_log_path)
        except (OSError, ValueError):
            pass
    return P1Application(config, storage_dir)


if "p1_app" not in st.session_state:
    st.session_state.p1_app = _new_application()
if "frame_source" not in st.session_state:
    st.session_state.frame_source = None
if "last_frame" not in st.session_state:
    st.session_state.last_frame = None

app: P1Application = st.session_state.p1_app

st.title("斯诺克视觉自动计分系统 — P1 完整规则")

with st.sidebar:
    st.subheader("Match")
    player_a_name = st.text_input("Player A", value="Player A")
    player_b_name = st.text_input("Player B", value="Player B")
    best_of = st.selectbox("Format", options=[1, 3, 5, 7, 9], index=1, format_func=lambda value: f"Best of {value}")
    if st.button("New Match", use_container_width=True):
        try:
            app.new_match(player_a_name, player_b_name, best_of=best_of)
            st.success("Match created")
        except Exception as exc:
            st.error(str(exc))
    match = app.view_state().match
    can_start = match is not None and match.status is not MatchStatus.FINISHED and (
        match.current_frame.status in (FrameStatus.NOT_STARTED, FrameStatus.FINISHED)
    )
    if st.button("Start / Next Frame", use_container_width=True, disabled=not can_start):
        try:
            app.start_frame()
            st.success("Frame started")
        except RulesError as exc:
            st.error(str(exc))
    st.divider()
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


control_a, control_b, control_c = st.columns(3)
with control_a:
    if st.button("Process next frame", use_container_width=True):
        process_frames(1)
with control_b:
    if st.button("Process 100 frames", use_container_width=True):
        process_frames(100)
with control_c:
    if st.button("Undo", use_container_width=True):
        app.undo()

view = app.view_state()
score_a, current, score_b = st.columns([2, 1, 2])
score_a.metric("Player A", view.scoreboard.player_a_score)
current.metric("Current Player", view.scoreboard.current_player.value.replace("PLAYER_", ""))
score_b.metric("Player B", view.scoreboard.player_b_score)

status_a, status_b, status_c, status_d = st.columns(4)
status_a.markdown(f"**System State**  \n`{view.system_status.value}`")
status_b.markdown(f"**Motion**  \n`{view.motion}`")
status_c.metric("Current Break", view.scoreboard.current_break)
if view.match is not None:
    status_d.metric("Frame Wins", f"{view.match.player_a_frames} : {view.match.player_b_frames}")
else:
    status_d.metric("Frame Wins", "—")
st.info(view.message)

if view.match is not None:
    frame = view.match.current_frame
    rule_a, rule_b, rule_c, rule_d = st.columns(4)
    rule_a.metric("Frame", frame.frame_number)
    rule_b.markdown(f"**Rule Phase**  \n`{frame.phase.value}`")
    expected_ball = frame.expected_ball.value if frame.expected_ball else "—"
    rule_c.markdown(f"**Expected Ball**  \n`{expected_ball}`")
    rule_d.metric("Reds Remaining", frame.remaining_reds)
    if frame.pending_respots:
        st.warning("Pending respot: " + ", ".join(color.value for color in frame.pending_respots))
        for color in dict.fromkeys(frame.pending_respots):
            if st.button(f"Confirm {color.value} respotted", key=f"respot-{color.value}"):
                app.complete_respot(color)
                st.rerun()

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
    st.write("Rule Decision", view.last_rule_decision.status.value if view.last_rule_decision else "—")
    st.write("Score Delta", view.last_rule_decision.points if view.last_rule_decision else 0)
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

if view.pending_fouls:
    st.subheader("Possible fouls requiring referee confirmation")
    for foul in view.pending_fouls:
        left, confirm, cancel = st.columns([4, 1, 1])
        left.write(
            f"{foul.shot.shot_id}: {', '.join(foul.reasons)} — proposed penalty {foul.penalty_points}"
        )
        if confirm.button("Confirm Foul", key=f"confirm-foul-{foul.event_id}"):
            app.confirm_foul(foul.event_id)
            st.rerun()
        if cancel.button("Cancel", key=f"cancel-foul-{foul.event_id}"):
            app.cancel_foul(foul.event_id)
            st.rerun()

if view.rule_events:
    st.subheader("Match Event Log")
    rows = [dict(event_to_dict(event)) for event in view.rule_events[-25:]]
    st.dataframe(rows, use_container_width=True, hide_index=True)
