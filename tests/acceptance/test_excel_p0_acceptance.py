from __future__ import annotations

from datetime import datetime, timezone
from collections import Counter

import pytest

from snooker_vision.application import P0Application
from snooker_vision.domain.models import BallColor, PotEvent, PotStatus
from snooker_vision.scoring import PlayerSwitchLocked, ReviewRequired, ScoreEngine
from tests.acceptance.excel_cases import ExcelCase, load_p0_cases, load_traceability_counts


CASES = load_p0_cases()
EXECUTABLE_STORIES = {"P0-US11", "P0-US12", "P0-US13", "P0-US14"}


def make_pot(
    event_id: str,
    color: BallColor,
    count: int = 1,
    status: PotStatus = PotStatus.CONFIRMED,
) -> PotEvent:
    return PotEvent(event_id, f"shot-{event_id}", color, count, status, 0.95, datetime.now(timezone.utc))


def run_us11(case: ExcelCase, config: dict[str, object]) -> None:
    engine = ScoreEngine(config["scoring"])
    values = {
        "01": (BallColor.RED, 1),
        "02": (BallColor.YELLOW, 2),
        "03": (BallColor.GREEN, 3),
        "04": (BallColor.BROWN, 4),
        "05": (BallColor.BLUE, 5),
        "06": (BallColor.PINK, 6),
        "07": (BallColor.BLACK, 7),
    }
    suffix = case.test_case_id[-2:]
    if suffix in values:
        color, value = values[suffix]
        event = engine.apply_pot(make_pot(case.test_case_id, color))
        assert event is not None and event.score_delta == value
    elif suffix in {"08", "09"}:
        color = BallColor.WHITE if suffix == "08" else BallColor.UNKNOWN
        assert engine.apply_pot(make_pot(case.test_case_id, color)) is None
        assert engine.state.player_a_score == 0
    elif suffix == "10":
        assert engine.state.player_a_score == 0
    elif suffix == "11":
        source = make_pot(case.test_case_id, BallColor.RED)
        assert engine.apply_pot(source) is engine.apply_pot(source)
        assert engine.state.player_a_score == 1
    elif suffix == "12":
        source = make_pot(case.test_case_id, BallColor.RED)
        engine.apply_pot(source)
        engine.undo()
        replay = engine.apply_pot(source)
        assert replay is not None and replay.undone
        assert engine.state.player_a_score == 0


def run_us12(case: ExcelCase, config: dict[str, object]) -> None:
    engine = ScoreEngine(config["scoring"])
    suffix = case.test_case_id[-2:]
    if suffix == "01":
        engine.apply_pot(make_pot("red", BallColor.RED))
        assert (engine.state.player_a_score, engine.state.player_b_score) == (1, 0)
    elif suffix == "02":
        engine.apply_pot(make_pot("red", BallColor.RED))
        engine.apply_pot(make_pot("black", BallColor.BLACK))
        assert engine.state.player_a_score == 8
    elif suffix == "03":
        engine.switch_player()
        engine.apply_pot(make_pot("black-b", BallColor.BLACK))
        assert (engine.state.player_a_score, engine.state.player_b_score) == (0, 7)
    elif suffix == "04":
        engine.apply_pot(make_pot("red-1", BallColor.RED))
        engine.apply_pot(make_pot("red-2", BallColor.RED))
        assert engine.state.player_a_score == 2
    elif suffix == "05":
        source = make_pot("duplicate", BallColor.BLACK)
        engine.apply_pot(source)
        engine.apply_pot(source)
        assert engine.state.player_a_score == 7
    elif suffix == "06":
        with pytest.raises(ReviewRequired):
            engine.apply_pot(make_pot("candidate", BallColor.BLACK, status=PotStatus.CANDIDATE))
        assert engine.state.player_a_score == 0
    elif suffix == "07":
        engine.apply_pot(make_pot("black", BallColor.BLACK))
        engine.undo()
        assert engine.state.player_a_score == 0
    elif suffix == "08":
        app = P0Application(config)
        assert app.view_state().scoreboard == app.score_engine.state
    elif suffix == "09":
        engine.apply_pot(make_pot("large", BallColor.BLACK, count=50))
        assert engine.state.player_a_score == 350


def run_us13(case: ExcelCase, config: dict[str, object]) -> None:
    engine = ScoreEngine(config["scoring"])
    suffix = case.test_case_id[-2:]
    if suffix == "01":
        assert engine.state.current_player.value == "PLAYER_A"
    elif suffix == "02":
        assert engine.switch_player().current_player.value == "PLAYER_B"
    elif suffix == "03":
        engine.switch_player()
        assert engine.switch_player().current_player.value == "PLAYER_A"
    elif suffix == "04":
        with pytest.raises(PlayerSwitchLocked):
            engine.switch_player(locked=True)
    elif suffix == "05":
        app = P0Application(config)
        app.review_events.append(make_pot("pending", BallColor.RED, status=PotStatus.CANDIDATE))
        with pytest.raises(PlayerSwitchLocked):
            app.switch_player()
    elif suffix == "06":
        assert engine.switch_player().current_player.value == "PLAYER_B"
        assert engine.events == ()
    elif suffix == "07":
        for _ in range(20):
            engine.switch_player()
        assert engine.state.current_player.value == "PLAYER_A"
        assert engine.events == ()
    elif suffix == "08":
        app = P0Application(config)
        app.switch_player()
        assert app.view_state().scoreboard.current_player == app.score_engine.state.current_player


def run_us14(case: ExcelCase, config: dict[str, object]) -> None:
    engine = ScoreEngine(config["scoring"])
    suffix = case.test_case_id[-2:]
    if suffix == "01":
        engine.apply_pot(make_pot("ten-reds", BallColor.RED, count=10))
        engine.apply_pot(make_pot("black", BallColor.BLACK))
        engine.undo()
        assert engine.state.player_a_score == 10
    elif suffix == "02":
        engine.apply_pot(make_pot("red", BallColor.RED))
        engine.apply_pot(make_pot("black", BallColor.BLACK))
        engine.undo()
        engine.undo()
        assert engine.state.player_a_score == 0
    elif suffix == "03":
        assert engine.undo() is None and engine.state.player_a_score == 0
    elif suffix == "04":
        engine.apply_pot(make_pot("two-reds", BallColor.RED, count=2))
        engine.undo()
        assert engine.state.player_a_score == 0
    elif suffix == "05":
        engine.apply_pot(make_pot("red", BallColor.RED))
        engine.undo()
        engine.apply_pot(make_pot("black", BallColor.BLACK))
        assert engine.state.player_a_score == 7
    elif suffix == "06":
        source = make_pot("red", BallColor.RED)
        engine.apply_pot(source)
        engine.undo()
        engine.apply_pot(source)
        assert engine.state.player_a_score == 0
        engine.apply_pot(source, allow_reconfirm=True)
        assert engine.state.player_a_score == 1
    elif suffix == "07":
        engine.apply_pot(make_pot("red", BallColor.RED))
        engine.apply_pot(make_pot("black", BallColor.BLACK))
        engine.undo()
        assert engine.state.current_break == 1
    elif suffix == "08":
        engine.switch_player()
        engine.apply_pot(make_pot("black-b", BallColor.BLACK))
        engine.undo()
        assert engine.state.current_player.value == "PLAYER_B"
        assert engine.state.player_b_score == 0
    elif suffix == "09":
        engine.apply_pot(make_pot("red", BallColor.RED))
        for _ in range(10):
            engine.undo()
        assert engine.state.player_a_score == 0


RUNNERS = {
    "P0-US11": run_us11,
    "P0-US12": run_us12,
    "P0-US13": run_us13,
    "P0-US14": run_us14,
}


def case_parameter(case: ExcelCase):
    if case.story_id in EXECUTABLE_STORIES:
        return pytest.param(case, id=case.test_case_id)
    return pytest.param(case, id=case.test_case_id, marks=pytest.mark.data_required)


@pytest.mark.acceptance
@pytest.mark.parametrize("case", [case_parameter(case) for case in CASES])
def test_excel_p0_case(case: ExcelCase, config: dict[str, object]) -> None:
    if case.story_id not in EXECUTABLE_STORIES:
        pytest.skip(
            f"DATA_REQUIRED: {case.test_case_id} needs a recorded visual/UI fixture for scenario: {case.scenario}"
        )
    RUNNERS[case.story_id](case, config)


def test_excel_baseline_integrity() -> None:
    assert len(CASES) == 151
    assert len({case.test_case_id for case in CASES}) == 151
    assert Counter(case.priority for case in CASES) == {
        "Critical": 15,
        "High": 119,
        "Medium": 15,
        "Low": 2,
    }


def test_excel_traceability_matrix_matches_test_rows() -> None:
    matrix = load_traceability_counts()
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

