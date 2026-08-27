from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from snooker_vision.application.service import P0Application, P0ViewState
from snooker_vision.domain.models import (
    FoulEvent,
    MatchEvent,
    MatchState,
    PotEvent,
    PotStatus,
    RuleDecision,
    RuleDecisionStatus,
    ScoreboardState,
    ShotEvent,
    ShotOutcome,
    ShotStatus,
    SystemStatus,
)
from snooker_vision.rules import EventLog, SnookerRulesEngine


@dataclass(frozen=True, slots=True)
class P1ViewState(P0ViewState):
    match: MatchState | None
    pending_fouls: tuple[FoulEvent, ...]
    rule_events: tuple[MatchEvent, ...]
    last_rule_decision: RuleDecision | None


class P1Application(P0Application):
    """P0 vision pipeline connected to the atomic P1 rules engine."""

    def __init__(self, config: Mapping[str, object], storage_dir: str | Path | None = None) -> None:
        super().__init__(config)
        self.storage_dir = Path(storage_dir) if storage_dir is not None else None
        event_path = self.storage_dir / "match-events.jsonl" if self.storage_dir is not None else None
        self.rules = SnookerRulesEngine(EventLog(event_path))
        self.snapshot_path = self.storage_dir / "active-match.json" if self.storage_dir is not None else None
        self.last_rule_decision: RuleDecision | None = None

    @classmethod
    def restore(
        cls,
        config: Mapping[str, object],
        snapshot_path: str | Path,
        event_log_path: str | Path | None = None,
    ) -> "P1Application":
        app = cls(config)
        app.rules = SnookerRulesEngine.load_snapshot(snapshot_path, event_log_path)
        app.snapshot_path = Path(snapshot_path)
        app.storage_dir = app.snapshot_path.parent
        app._sync_scoreboard()
        app.status = SystemStatus.READY
        app.message = "Match restored"
        return app

    def new_match(
        self,
        player_a_name: str = "Player A",
        player_b_name: str = "Player B",
        best_of: int = 3,
        match_id: str | None = None,
    ) -> MatchState:
        state = self.rules.new_match(player_a_name, player_b_name, best_of, match_id)
        self._sync_scoreboard()
        self.message = "Match created; start Frame 1"
        self._persist_rules()
        return state

    def start_frame(self) -> MatchState:
        state = self.rules.start_frame()
        self._sync_scoreboard()
        self.message = f"Frame {state.current_frame.frame_number} playing"
        self._persist_rules()
        return state

    def commit_rule_shot(
        self, shot: ShotEvent, pot_events: Sequence[PotEvent]
    ) -> RuleDecision | None:
        if shot.status is not ShotStatus.COMPLETED or shot.after_state is None:
            raise ValueError("Rule shot must be completed and contain an After State")
        shot.potted_balls = tuple(pot_events)
        unresolved = [
            event for event in pot_events if event.status in (PotStatus.CANDIDATE, PotStatus.UNKNOWN)
        ]
        if unresolved:
            for event in unresolved:
                if event not in self.review_events:
                    self.review_events.append(event)
            self.last_shot = shot
            self.status = SystemStatus.REVIEW_REQUIRED
            self.message = "Pot evidence requires review before rule evaluation"
            return None
        confirmed = [event for event in pot_events if event.status is PotStatus.CONFIRMED]
        colors = tuple(color for event in confirmed for color in (event.ball_color,) * event.count)
        outcome = ShotOutcome(
            shot_id=shot.shot_id,
            player=shot.player,
            potted_colors=colors,
            confidence=min((event.confidence for event in confirmed), default=1.0),
            timestamp=shot.ended_at or shot.started_at,
        )
        decision = self.rules.process_shot(outcome)
        self.last_rule_decision = decision
        self.last_shot = shot
        self.last_pot = confirmed[-1] if confirmed else None
        self.last_stable_state = shot.after_state
        self._sync_scoreboard()
        if decision.status is RuleDecisionStatus.FOUL_CANDIDATE:
            self.status = SystemStatus.REVIEW_REQUIRED
            self.message = "Possible foul requires confirmation"
        elif decision.status is RuleDecisionStatus.REVIEW_REQUIRED:
            self.status = SystemStatus.REVIEW_REQUIRED
            self.message = decision.message
        else:
            self.status = SystemStatus.READY
            self.message = decision.message or decision.status.value
        self._persist_rules()
        return decision

    def _handle_completed_shot(self, shot: ShotEvent, events: Sequence[PotEvent]) -> None:
        auto_threshold = float(self.config["app"]["auto_commit_confidence"])  # type: ignore[index]
        normalized: list[PotEvent] = []
        for event in events:
            if event.status is PotStatus.CONFIRMED and event.confidence < auto_threshold:
                event.status = PotStatus.CANDIDATE
            normalized.append(event)
        shot.potted_balls = tuple(normalized)
        self.commit_rule_shot(shot, normalized)

    def confirm_pot(self, event_id: str) -> None:
        event = next((item for item in self.review_events if item.event_id == event_id), None)
        if event is None or self.last_shot is None:
            raise KeyError(f"Unknown pending pot event: {event_id}")
        self.pot_detector.confirm_candidate(event)
        self.review_events.remove(event)
        if not self.review_events:
            self.commit_rule_shot(self.last_shot, self.last_shot.potted_balls)
        self.status = SystemStatus.REVIEW_REQUIRED if self.review_events else self.status

    def reject_pot(self, event_id: str) -> None:
        event = next((item for item in self.review_events if item.event_id == event_id), None)
        if event is None or self.last_shot is None:
            raise KeyError(f"Unknown pending pot event: {event_id}")
        self.pot_detector.reject_candidate(event)
        self.review_events.remove(event)
        if not self.review_events:
            self.commit_rule_shot(self.last_shot, self.last_shot.potted_balls)
        self.status = SystemStatus.REVIEW_REQUIRED if self.review_events else self.status

    def confirm_foul(self, foul_event_id: str) -> RuleDecision:
        decision = self.rules.confirm_foul(foul_event_id)
        self.last_rule_decision = decision
        self._sync_scoreboard()
        self.status = SystemStatus.READY
        self.message = f"Foul confirmed: opponent +{decision.penalty_points}"
        self._persist_rules()
        return decision

    def cancel_foul(self, foul_event_id: str) -> RuleDecision:
        decision = self.rules.cancel_foul(foul_event_id)
        self.last_rule_decision = decision
        self.status = SystemStatus.READY
        self.message = "Foul cancelled; match state unchanged"
        self._persist_rules()
        return decision

    def complete_respot(self, color) -> MatchState:
        state = self.rules.complete_respot(color, observed_color=color)
        self._sync_scoreboard()
        self.message = f"{color.value} respot completed"
        self._persist_rules()
        return state

    def undo(self) -> MatchEvent | None:
        event = self.rules.undo()
        self._sync_scoreboard()
        self.status = SystemStatus.READY
        self.message = "Nothing to undo" if event is None else "Last P1 rule action undone"
        self._persist_rules()
        return event

    def view_state(self) -> P1ViewState:
        self._sync_scoreboard()
        base = super().view_state()
        try:
            match = self.rules.state
        except Exception:
            match = None
        return P1ViewState(
            scoreboard=base.scoreboard,
            system_status=base.system_status,
            motion=base.motion,
            last_shot=base.last_shot,
            last_pot=base.last_pot,
            last_score_event=base.last_score_event,
            stable_state=base.stable_state,
            review_events=base.review_events,
            message=base.message,
            match=match,
            pending_fouls=self.rules.pending_fouls,
            rule_events=self.rules.events,
            last_rule_decision=self.last_rule_decision,
        )

    def _sync_scoreboard(self) -> None:
        try:
            frame = self.rules.state.current_frame
        except Exception:
            return
        self.score_engine.state = ScoreboardState(
            player_a_score=frame.player_a_score,
            player_b_score=frame.player_b_score,
            current_player=frame.current_player,
            current_break=frame.current_break,
        )

    def _persist_rules(self) -> None:
        if self.snapshot_path is not None:
            self.rules.save_snapshot(self.snapshot_path)
