from __future__ import annotations

from collections import Counter
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from snooker_vision.domain.models import (
    BallColor,
    FrameState,
    FrameStatus,
    MatchEvent,
    MatchEventType,
    MatchStatus,
    Player,
    RuleDecisionStatus,
    RulePhase,
    ShotOutcome,
)
from snooker_vision.rules import (
    EventLog,
    InvalidRespot,
    MatchInProgress,
    MatchNotReady,
    PendingDecision,
    RuleStateConflict,
    SnookerRulesEngine,
    UnknownFoul,
)
from tests.acceptance.excel_cases import (
    ExcelCase,
    load_p1_cases,
    load_p1_traceability_counts,
)


CASES = load_p1_cases()
DATA_REQUIRED_CASES = {
    "TC-P1-US09-01",
    "TC-P1-US09-02",
    "TC-P1-US09-03",
    "TC-P1-US09-04",
    "TC-P1-US09-05",
}


def suffix(case: ExcelCase) -> str:
    return case.test_case_id[-2:]


def started(best_of: int = 3, event_log: EventLog | None = None) -> SnookerRulesEngine:
    engine = SnookerRulesEngine(event_log)
    engine.new_match("Alice", "Bob", best_of=best_of, match_id="acceptance")
    engine.start_frame()
    return engine


def shot(
    engine: SnookerRulesEngine,
    shot_id: str,
    *colors: BallColor,
    confirmed: bool = True,
    nominated: BallColor | None = None,
) -> ShotOutcome:
    return ShotOutcome(
        shot_id,
        engine.state.current_frame.current_player,
        tuple(colors),
        nominated_color=nominated,
        confirmed=confirmed,
        confidence=1.0 if confirmed else 0.5,
    )


def enter_clearance(engine: SnookerRulesEngine) -> None:
    engine.process_shot(shot(engine, "all-reds", *((BallColor.RED,) * 15)))
    engine.process_shot(shot(engine, "last-red-color", BallColor.BLACK))
    engine.complete_respot(BallColor.BLACK)
    assert engine.state.current_frame.phase is RulePhase.CLEARANCE


def advance_clearance(engine: SnookerRulesEngine, through: BallColor | None = None) -> None:
    enter_clearance(engine)
    for color in (
        BallColor.YELLOW,
        BallColor.GREEN,
        BallColor.BROWN,
        BallColor.BLUE,
        BallColor.PINK,
        BallColor.BLACK,
    ):
        engine.process_shot(shot(engine, f"clear-{color.value}", color))
        if color is through:
            return


def award_frame(engine: SnookerRulesEngine, winner: Player) -> None:
    if engine.state.current_frame.current_player is not winner:
        engine.process_shot(shot(engine, f"switch-{engine.state.current_frame.frame_number}"))
    engine.process_shot(shot(engine, f"frame-score-{engine.state.current_frame.frame_number}", BallColor.RED))
    engine.end_frame()


def foul_candidate(
    engine: SnookerRulesEngine, shot_id: str = "foul", color: BallColor = BallColor.WHITE
):
    decision = engine.process_shot(shot(engine, shot_id, color))
    assert decision.status is RuleDecisionStatus.FOUL_CANDIDATE
    assert decision.foul_event_id is not None
    return decision


def run_us01(case: ExcelCase, tmp_path) -> None:
    code = suffix(case)
    engine = SnookerRulesEngine()
    if code == "02":
        state = engine.new_match("", "", match_id="m")
        assert state.player_a.display_name == "Player A"
        assert state.player_b.display_name == "Player B"
    elif code == "03":
        state = engine.new_match("Alex", "Alex", match_id="m")
        assert state.player_a.player_id != state.player_b.player_id
    elif code == "04":
        engine.new_match(match_id="m")
        engine.start_frame()
        with pytest.raises(MatchInProgress):
            engine.new_match(match_id="other")
    elif code == "05":
        engine.new_match(match_id="m")
        first = engine.start_frame()
        assert engine.start_frame() is first
    elif code == "06":
        for value in (0, 2, -1, 36):
            with pytest.raises(ValueError):
                SnookerRulesEngine().new_match(best_of=value, match_id=f"bad-{value}")
    else:
        state = engine.new_match("Alice", "Bob", best_of=3, match_id="m")
        assert state.current_frame.player_a_score == state.current_frame.player_b_score == 0
        assert state.current_frame.remaining_reds == 15
        assert state.current_frame.frame_number == 1
        assert state.current_frame.phase is RulePhase.EXPECT_RED
        assert state.current_frame.current_player is Player.PLAYER_A


def run_us02(case: ExcelCase, tmp_path) -> None:
    code = suffix(case)
    engine = started()
    if code == "01":
        decision = engine.process_shot(shot(engine, "red", BallColor.RED))
        assert decision.points == 1 and engine.state.current_frame.phase is RulePhase.EXPECT_COLOR
    elif code == "02":
        engine.process_shot(shot(engine, "miss"))
        assert engine.state.current_frame.current_player is Player.PLAYER_B
    elif code == "03":
        assert foul_candidate(engine, color=BallColor.YELLOW).penalty_points == 4
    elif code == "04":
        foul_candidate(engine, color=BallColor.WHITE)
    elif code == "05":
        result = engine.process_shot(shot(engine, "two", BallColor.RED, BallColor.RED))
        assert result.points == 2 and engine.state.current_frame.remaining_reds == 13
    elif code == "06":
        engine.process_shot(shot(engine, "fourteen", *((BallColor.RED,) * 14)))
        engine.process_shot(shot(engine, "color", BallColor.BLACK))
        engine.complete_respot(BallColor.BLACK)
        engine.process_shot(shot(engine, "last", BallColor.RED))
        assert engine.state.current_frame.remaining_reds == 0
        assert engine.state.current_frame.phase is RulePhase.EXPECT_COLOR
    else:
        with pytest.raises(ValueError):
            replace(FrameState(1), remaining_reds=0)


def run_us03(case: ExcelCase, tmp_path) -> None:
    code = suffix(case)
    engine = started()
    engine.process_shot(shot(engine, "red", BallColor.RED))
    colors = {
        "01": (BallColor.YELLOW, 2),
        "02": (BallColor.GREEN, 3),
        "03": (BallColor.BROWN, 4),
        "04": (BallColor.BLUE, 5),
        "05": (BallColor.PINK, 6),
        "06": (BallColor.BLACK, 7),
    }
    if code in colors:
        color, points = colors[code]
        result = engine.process_shot(shot(engine, f"color-{code}", color))
        assert result.points == points and engine.state.current_frame.phase is RulePhase.EXPECT_RED
    elif code == "07":
        engine.process_shot(shot(engine, "miss"))
        assert engine.state.current_frame.current_player is Player.PLAYER_B
    elif code == "08":
        result = engine.process_shot(shot(engine, "many", BallColor.BLUE, BallColor.PINK))
        assert result.status is RuleDecisionStatus.FOUL_CANDIDATE
    else:
        result = engine.process_shot(shot(engine, "white-color", BallColor.BLACK, BallColor.WHITE))
        assert result.status is RuleDecisionStatus.FOUL_CANDIDATE and result.points == 0


def run_us04(case: ExcelCase, tmp_path) -> None:
    code = suffix(case)
    colors = {
        "01": (BallColor.BLACK,),
        "02": (BallColor.YELLOW,),
        "03": (BallColor.GREEN, BallColor.BROWN, BallColor.BLUE, BallColor.PINK),
    }
    if code in colors:
        for index, color in enumerate(colors[code]):
            engine = started()
            engine.process_shot(shot(engine, f"red-{index}", BallColor.RED))
            before_events = len(engine.events)
            engine.process_shot(shot(engine, f"color-{index}", color))
            assert color in engine.state.current_frame.pending_respots
            engine.complete_respot(color)
            assert engine.state.current_frame.pending_respots == ()
            assert len([event for event in engine.events[before_events:] if event.event_type is MatchEventType.SCORE]) == 1
    else:
        engine = started()
        engine.process_shot(shot(engine, "red", BallColor.RED))
        engine.process_shot(shot(engine, "black", BallColor.BLACK))
        if code == "04":
            with pytest.raises(PendingDecision):
                engine.process_shot(shot(engine, "too-soon", BallColor.RED))
        elif code == "05":
            score_events = len([event for event in engine.events if event.event_type is MatchEventType.SCORE])
            engine.complete_respot(BallColor.BLACK)
            assert len([event for event in engine.events if event.event_type is MatchEventType.SCORE]) == score_events
        elif code == "06":
            with pytest.raises(InvalidRespot):
                engine.complete_respot(BallColor.BLACK, observed_color=BallColor.PINK)
        else:
            engine.undo()
            assert engine.state.current_frame.phase is RulePhase.EXPECT_COLOR
            assert engine.state.current_frame.player_a_score == 1


def run_us05(case: ExcelCase, tmp_path) -> None:
    code = suffix(case)
    engine = started()
    if code == "01":
        engine.process_shot(shot(engine, "red", BallColor.RED))
        assert engine.state.current_frame.remaining_reds == 14
    elif code == "02":
        engine.process_shot(shot(engine, "all", *((BallColor.RED,) * 15)))
        assert engine.state.current_frame.remaining_reds == 0
    elif code == "03":
        engine.process_shot(shot(engine, "two", BallColor.RED, BallColor.RED))
        assert engine.state.current_frame.remaining_reds == 13
    elif code in {"04", "06"}:
        with pytest.raises(ValueError):
            FrameState(1, remaining_reds=16)
    elif code == "05":
        with pytest.raises(RuleStateConflict):
            engine.process_shot(shot(engine, "underflow", *((BallColor.RED,) * 16)))
    else:
        engine.process_shot(shot(engine, "red", BallColor.RED))
        engine.undo()
        assert engine.state.current_frame.remaining_reds == 15


def run_us06(case: ExcelCase, tmp_path) -> None:
    code = suffix(case)
    engine = started(best_of=1)
    transitions = {
        "01": (BallColor.YELLOW, BallColor.GREEN),
        "02": (BallColor.GREEN, BallColor.BROWN),
        "03": (BallColor.BROWN, BallColor.BLUE),
        "04": (BallColor.BLUE, BallColor.PINK),
        "05": (BallColor.PINK, BallColor.BLACK),
    }
    if code in transitions:
        color, expected = transitions[code]
        preceding = list((BallColor.YELLOW, BallColor.GREEN, BallColor.BROWN, BallColor.BLUE, BallColor.PINK))
        enter_clearance(engine)
        for item in preceding[: preceding.index(color)]:
            engine.process_shot(shot(engine, f"pre-{item.value}", item))
        engine.process_shot(shot(engine, f"target-{color.value}", color))
        assert engine.state.current_frame.expected_ball is expected
    elif code == "06":
        advance_clearance(engine)
        assert engine.state.current_frame.status is FrameStatus.FINISHED
    elif code == "07":
        enter_clearance(engine)
        assert engine.process_shot(shot(engine, "wrong", BallColor.GREEN)).status is RuleDecisionStatus.FOUL_CANDIDATE
        assert engine.state.current_frame.expected_ball is BallColor.YELLOW
    elif code == "08":
        enter_clearance(engine)
        engine.process_shot(shot(engine, "miss"))
        assert engine.state.current_frame.expected_ball is BallColor.YELLOW
        assert engine.state.current_frame.current_player is Player.PLAYER_B
    elif code == "09":
        enter_clearance(engine)
        engine.process_shot(shot(engine, "yellow", BallColor.YELLOW))
        with pytest.raises(InvalidRespot):
            engine.complete_respot(BallColor.YELLOW)
    else:
        enter_clearance(engine)
        before = engine.state
        engine.process_shot(shot(engine, "yellow", BallColor.YELLOW))
        engine.undo()
        assert engine.state == before


def run_us07(case: ExcelCase, tmp_path) -> None:
    code = suffix(case)
    engine = started()
    if code == "01":
        engine.process_shot(shot(engine, "a-miss"))
        assert engine.state.current_frame.current_player is Player.PLAYER_B
    elif code == "02":
        engine.process_shot(shot(engine, "a-miss"))
        engine.process_shot(shot(engine, "b-miss"))
        assert engine.state.current_frame.current_player is Player.PLAYER_A
    elif code == "03":
        engine.process_shot(shot(engine, "red", BallColor.RED))
        assert engine.state.current_frame.current_player is Player.PLAYER_A
    elif code == "04":
        before = engine.state
        ShotOutcome("in-progress", Player.PLAYER_A)
        assert engine.state == before
    elif code == "05":
        result = engine.process_shot(shot(engine, "uncertain", confirmed=False))
        assert result.status is RuleDecisionStatus.REVIEW_REQUIRED
        assert engine.state.current_frame.current_player is Player.PLAYER_A
    elif code == "06":
        candidate = foul_candidate(engine)
        engine.confirm_foul(candidate.foul_event_id)
        assert engine.state.current_frame.current_player is Player.PLAYER_B
    else:
        engine.process_shot(shot(engine, "false-miss"))
        engine.undo()
        assert engine.state.current_frame.current_player is Player.PLAYER_A


def run_us08(case: ExcelCase, tmp_path) -> None:
    code = suffix(case)
    engine = started()
    engine.process_shot(shot(engine, "red-1", BallColor.RED))
    if code in {"01", "03", "04"}:
        engine.process_shot(shot(engine, "black", BallColor.BLACK))
        assert engine.state.current_frame.current_player is Player.PLAYER_A
    elif code == "02":
        engine.process_shot(shot(engine, "blue", BallColor.BLUE))
        engine.complete_respot(BallColor.BLUE)
        engine.process_shot(shot(engine, "red-2", BallColor.RED))
        assert engine.state.current_frame.current_player is Player.PLAYER_A
    elif code == "05":
        engine.process_shot(shot(engine, "color-miss"))
        assert engine.state.current_frame.current_player is Player.PLAYER_B
    else:
        candidate = engine.process_shot(shot(engine, "white", BallColor.WHITE))
        engine.confirm_foul(candidate.foul_event_id)
        assert engine.state.current_frame.current_player is Player.PLAYER_B


def run_us09(case: ExcelCase, tmp_path) -> None:
    engine = started()
    decision = engine.process_shot(shot(engine, "white-target", BallColor.WHITE, BallColor.RED))
    assert decision.status is RuleDecisionStatus.FOUL_CANDIDATE
    assert "CUE_BALL_POTTED" in engine.pending_fouls[0].reasons


def run_us10(case: ExcelCase, tmp_path) -> None:
    code = suffix(case)
    engine = started()
    if code == "01":
        foul_candidate(engine, color=BallColor.WHITE)
    elif code == "02":
        foul_candidate(engine, color=BallColor.YELLOW)
    elif code == "03":
        enter_clearance(engine)
        assert engine.process_shot(shot(engine, "wrong", BallColor.GREEN)).status is RuleDecisionStatus.FOUL_CANDIDATE
    elif code == "04":
        result = engine.process_shot(shot(engine, "occlusion-review", confirmed=False))
        assert result.status is RuleDecisionStatus.REVIEW_REQUIRED and not engine.pending_fouls
    elif code == "05":
        assert engine.process_shot(shot(engine, "red", BallColor.RED)).status is RuleDecisionStatus.LEGAL
    elif code == "06":
        engine.process_shot(shot(engine, "red", BallColor.RED))
        assert engine.process_shot(shot(engine, "black", BallColor.BLACK)).status is RuleDecisionStatus.LEGAL
    else:
        decision = engine.process_shot(shot(engine, "aggregate", BallColor.WHITE, BallColor.BLACK))
        assert decision.status is RuleDecisionStatus.FOUL_CANDIDATE and len(engine.pending_fouls) == 1


def run_us11(case: ExcelCase, tmp_path) -> None:
    code = suffix(case)
    color = {"02": BallColor.BLUE, "03": BallColor.PINK, "04": BallColor.BLACK}.get(code, BallColor.YELLOW)
    engine = started()
    if code == "05":
        decision = engine.process_shot(shot(engine, "multi", BallColor.WHITE, BallColor.BLACK))
    else:
        decision = foul_candidate(engine, color=color)
    before_a = engine.state.current_frame.player_a_score
    confirmed = engine.confirm_foul(decision.foul_event_id)
    expected = {BallColor.YELLOW: 4, BallColor.BLUE: 5, BallColor.PINK: 6, BallColor.BLACK: 7}[color]
    if code == "05":
        expected = 7
    if code == "01":
        assert confirmed.penalty_points == 4
    elif code in {"02", "03", "04"}:
        assert confirmed.penalty_points == expected
    elif code == "06":
        assert engine.state.current_frame.player_a_score == before_a
    elif code == "07":
        assert engine.state.current_frame.player_b_score == expected
    elif code == "08":
        again = engine.confirm_foul(decision.foul_event_id)
        assert again is confirmed and engine.state.current_frame.player_b_score == expected
    else:
        assert engine.state.current_frame.player_b_score == 7


def run_us12(case: ExcelCase, tmp_path) -> None:
    code = suffix(case)
    engine = started()
    candidate = foul_candidate(engine)
    foul_id = candidate.foul_event_id
    if code == "01":
        engine.confirm_foul(foul_id)
        assert engine.state.current_frame.player_b_score == 4
    elif code == "02":
        before = engine.state
        engine.cancel_foul(foul_id)
        assert engine.state == before
    elif code in {"03", "07"}:
        first = engine.confirm_foul(foul_id)
        second = engine.confirm_foul(foul_id)
        assert first is second and engine.state.current_frame.player_b_score == 4
    elif code == "04":
        before = engine.state
        engine.confirm_foul(foul_id)
        engine.undo()
        assert engine.state == before
    elif code == "05":
        engine.cancel_foul(foul_id)
        repeated = engine.process_shot(shot(engine, "foul", BallColor.WHITE))
        assert repeated.foul_event_id != foul_id
    else:
        engine.cancel_foul(foul_id)
        with pytest.raises(UnknownFoul):
            engine.confirm_foul("missing")


def run_us13(case: ExcelCase, tmp_path) -> None:
    code = suffix(case)
    log_path = tmp_path / f"{case.test_case_id}.jsonl"
    snapshot = tmp_path / f"{case.test_case_id}.json"
    engine = SnookerRulesEngine(EventLog(log_path))
    engine.new_match(match_id="acceptance")
    if code == "01":
        assert engine.state.current_frame.status is FrameStatus.NOT_STARTED
        engine.start_frame()
        assert engine.state.current_frame.status is FrameStatus.PLAYING
        return
    engine.start_frame()
    engine.process_shot(shot(engine, "red", BallColor.RED))
    if code == "02":
        assert engine.events[-1].frame_number == 1 and engine.events[-1].shot_id == "red"
    elif code == "03":
        engine.end_frame()
        assert engine.state.current_frame.status is FrameStatus.FINISHED
    elif code == "04":
        engine.end_frame()
        with pytest.raises(MatchNotReady):
            engine.process_shot(ShotOutcome("late", Player.PLAYER_A, (BallColor.RED,)))
    elif code == "05":
        engine.end_frame()
        engine.undo()
        assert engine.state.current_frame.status is FrameStatus.PLAYING
    else:
        engine.save_snapshot(snapshot)
        restored = SnookerRulesEngine.load_snapshot(snapshot, log_path)
        assert restored.state == engine.state
        assert restored.state.current_frame.current_player == engine.state.current_frame.current_player


def run_us14(case: ExcelCase, tmp_path) -> None:
    code = suffix(case)
    engine = started(best_of=1)
    if code == "01":
        award_frame(engine, Player.PLAYER_A)
        assert engine.state.winner is Player.PLAYER_A
    elif code == "02":
        award_frame(engine, Player.PLAYER_B)
        assert engine.state.winner is Player.PLAYER_B
    elif code == "03":
        engine.end_frame()
        assert engine.state.current_frame.phase is RulePhase.RESPOTTED_BLACK
        assert engine.state.winner is None
    elif code == "04":
        advance_clearance(engine)
        assert engine.state.current_frame.winner is Player.PLAYER_A
    elif code == "05":
        candidate = foul_candidate(engine)
        engine.confirm_foul(candidate.foul_event_id)
        engine.end_frame()
        assert engine.state.winner is Player.PLAYER_B
    elif code == "06":
        engine.process_shot(shot(engine, "red", BallColor.RED))
        engine.end_frame()
        engine.undo()
        assert engine.state.status is MatchStatus.PLAYING and engine.state.winner is None
    else:
        engine.process_shot(shot(engine, "red", BallColor.RED))
        engine.end_frame()
        count = len([event for event in engine.events if event.event_type is MatchEventType.FRAME_FINISHED])
        with pytest.raises(MatchNotReady):
            engine.end_frame()
        assert len([event for event in engine.events if event.event_type is MatchEventType.FRAME_FINISHED]) == count


def run_us15(case: ExcelCase, tmp_path) -> None:
    code = suffix(case)
    if code in {"06", "07"}:
        invalid = 2 if code == "06" else 0
        with pytest.raises(ValueError):
            SnookerRulesEngine().new_match(best_of=invalid, match_id="bad")
        return
    if code == "08":
        engine = started(best_of=35)
        assert engine.state.frames_to_win == 18
        return
    best_of = {"01": 3, "02": 5, "03": 7, "04": 3, "05": 1}[code]
    engine = started(best_of=best_of)
    if code == "04":
        award_frame(engine, Player.PLAYER_A)
        engine.start_frame()
        award_frame(engine, Player.PLAYER_B)
        assert engine.state.status is MatchStatus.PLAYING
        engine.start_frame()
        assert engine.state.current_frame.frame_number == 3
        return
    needed = engine.state.frames_to_win
    for index in range(needed):
        award_frame(engine, Player.PLAYER_A)
        if index < needed - 1:
            engine.start_frame()
    assert engine.state.status is MatchStatus.FINISHED
    assert engine.state.player_a_frames == needed


def run_us16(case: ExcelCase, tmp_path) -> None:
    code = suffix(case)
    log_path = tmp_path / f"{case.test_case_id}.jsonl"
    engine = started(event_log=EventLog(log_path))
    if code == "01":
        engine.process_shot(shot(engine, "red", BallColor.RED))
        event = engine.events[-1]
        assert event.shot_id == "red" and event.player is Player.PLAYER_A
        assert event.score_delta == 1 and event.frame_number == 1 and event.timestamp.tzinfo is not None
    elif code == "02":
        candidate = foul_candidate(engine)
        engine.confirm_foul(candidate.foul_event_id)
        assert any(event.event_type is MatchEventType.FOUL_CONFIRMED for event in engine.events)
    elif code == "03":
        engine.process_shot(shot(engine, "red", BallColor.RED))
        score = engine.events[-1]
        engine.undo()
        assert score.undone and engine.events[-1].event_type is MatchEventType.UNDO
    elif code == "04":
        engine.process_shot(shot(engine, "red", BallColor.RED))
        stamps = [event.timestamp for event in engine.events]
        assert stamps == sorted(stamps)
    elif code == "05":
        engine.process_shot(shot(engine, "red", BallColor.RED))
        ids = [event.event_id for event in engine.events]
        assert len(ids) == len(set(ids))
    elif code == "06":
        engine.process_shot(shot(engine, "red", BallColor.RED))
        loaded = EventLog(log_path)
        assert len(loaded.events) == len(engine.events)
    else:
        log = EventLog()
        for index in range(1050):
            log.append(
                MatchEvent(
                    f"event-{index}",
                    MatchEventType.SCORE,
                    "performance",
                    1,
                    datetime.now(timezone.utc),
                    Player.PLAYER_A,
                    f"shot-{index}",
                    1,
                )
            )
        assert len(log.events) == 1050


RUNNERS = {
    "P1-US01": run_us01,
    "P1-US02": run_us02,
    "P1-US03": run_us03,
    "P1-US04": run_us04,
    "P1-US05": run_us05,
    "P1-US06": run_us06,
    "P1-US07": run_us07,
    "P1-US08": run_us08,
    "P1-US09": run_us09,
    "P1-US10": run_us10,
    "P1-US11": run_us11,
    "P1-US12": run_us12,
    "P1-US13": run_us13,
    "P1-US14": run_us14,
    "P1-US15": run_us15,
    "P1-US16": run_us16,
}


def case_parameter(case: ExcelCase):
    if case.test_case_id in DATA_REQUIRED_CASES:
        return pytest.param(case, id=case.test_case_id, marks=pytest.mark.data_required)
    return pytest.param(case, id=case.test_case_id)


@pytest.mark.acceptance
@pytest.mark.parametrize("case", [case_parameter(case) for case in CASES])
def test_excel_p1_case(case: ExcelCase, tmp_path) -> None:
    if case.test_case_id in DATA_REQUIRED_CASES:
        pytest.skip(
            f"DATA_REQUIRED: {case.test_case_id} needs real cue-ball pocket/occlusion footage: {case.scenario}"
        )
    RUNNERS[case.story_id](case, tmp_path)


def test_excel_p1_baseline_integrity() -> None:
    assert len(CASES) == 117
    assert len({case.test_case_id for case in CASES}) == 117
    assert Counter(case.priority for case in CASES) == {
        "Critical": 36,
        "High": 67,
        "Medium": 12,
        "Low": 2,
    }


def test_excel_p1_traceability_matrix_matches_test_rows() -> None:
    matrix = load_p1_traceability_counts()
    for story_id in sorted({case.story_id for case in CASES}):
        rows = [case for case in CASES if case.story_id == story_id]
        actual = (
            len(rows),
            sum(case.priority == "Critical" for case in rows),
            sum(case.priority == "High" for case in rows),
            sum(case.priority == "Medium" for case in rows),
            sum(case.priority == "Low" for case in rows),
        )
        assert matrix[story_id] == actual
