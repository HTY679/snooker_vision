from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from threading import RLock
from uuid import uuid4

from snooker_vision.domain.models import (
    BallColor,
    FoulEvent,
    FoulStatus,
    FrameResult,
    FrameState,
    FrameStatus,
    MatchEvent,
    MatchEventType,
    MatchState,
    MatchStatus,
    Player,
    PlayerIdentity,
    RuleDecision,
    RuleDecisionStatus,
    RulePhase,
    SNOOKER_BALL_VALUES,
    SNOOKER_COLOR_ORDER,
    ShotOutcome,
)
from snooker_vision.rules.event_log import EventLog


class RulesError(RuntimeError):
    pass


class MatchInProgress(RulesError):
    pass


class MatchNotReady(RulesError):
    pass


class PendingDecision(RulesError):
    pass


class InvalidRespot(RulesError):
    pass


class UnknownFoul(RulesError):
    pass


class RuleStateConflict(RulesError):
    pass


@dataclass(slots=True)
class UndoEntry:
    prior_state: MatchState
    event_ids: tuple[str, ...]
    shot_id: str | None = None
    prior_decision: RuleDecision | None = None
    foul_event_id: str | None = None
    prior_foul_status: FoulStatus | None = None


class SnookerRulesEngine:
    """Deterministic P1 rules state machine for one active match."""

    def __init__(self, event_log: EventLog | None = None) -> None:
        self.event_log = event_log or EventLog()
        self._state: MatchState | None = None
        self._pending_fouls: dict[str, FoulEvent] = {}
        self._fouls: dict[str, FoulEvent] = {}
        self._processed_shots: dict[str, RuleDecision] = {}
        self._undo: list[UndoEntry] = []
        self._lock = RLock()

    @property
    def state(self) -> MatchState:
        if self._state is None:
            raise MatchNotReady("Create a match first")
        return self._state

    @property
    def pending_fouls(self) -> tuple[FoulEvent, ...]:
        return tuple(self._pending_fouls.values())

    @property
    def fouls(self) -> tuple[FoulEvent, ...]:
        return tuple(self._fouls.values())

    @property
    def events(self) -> tuple[MatchEvent, ...]:
        return self.event_log.events

    def new_match(
        self,
        player_a_name: str = "Player A",
        player_b_name: str = "Player B",
        best_of: int = 3,
        match_id: str | None = None,
    ) -> MatchState:
        with self._lock:
            requested_id = match_id or f"match-{uuid4().hex}"
            if self._state is not None and self._state.status is not MatchStatus.FINISHED:
                if match_id is not None and requested_id == self._state.match_id:
                    return self._state
                raise MatchInProgress("An unfinished match already exists; confirmation is required")
            if best_of < 1 or best_of > 35 or best_of % 2 == 0:
                raise ValueError("best_of must be an odd number between 1 and 35")
            name_a = player_a_name.strip() or "Player A"
            name_b = player_b_name.strip() or "Player B"
            frame = FrameState(frame_number=1)
            self._state = MatchState(
                requested_id,
                PlayerIdentity(f"{requested_id}-player-a", Player.PLAYER_A, name_a),
                PlayerIdentity(f"{requested_id}-player-b", Player.PLAYER_B, name_b),
                best_of,
                MatchStatus.NOT_STARTED,
                0,
                0,
                frame,
            )
            self._pending_fouls.clear()
            self._fouls.clear()
            self._processed_shots.clear()
            self._undo.clear()
            self._append_event(MatchEventType.MATCH_CREATED, details={"best_of": best_of})
            return self._state

    def start_frame(self) -> MatchState:
        with self._lock:
            state = self.state
            if state.status is MatchStatus.FINISHED:
                raise MatchNotReady("Match is already finished")
            frame = state.current_frame
            if frame.status is FrameStatus.PLAYING:
                return state
            if frame.status is FrameStatus.FINISHED:
                frame = FrameState(
                    frame_number=frame.frame_number + 1,
                    current_player=frame.winner.other() if frame.winner is not None else Player.PLAYER_A,
                )
            frame = replace(frame, status=FrameStatus.PLAYING)
            first_start = state.status is MatchStatus.NOT_STARTED
            self._state = replace(state, status=MatchStatus.PLAYING, current_frame=frame)
            if first_start:
                self._append_event(MatchEventType.MATCH_STARTED)
            self._append_event(MatchEventType.FRAME_STARTED)
            return self._state

    def process_shot(self, outcome: ShotOutcome) -> RuleDecision:
        with self._lock:
            existing = self._processed_shots.get(outcome.shot_id)
            if existing is not None and existing.status is not RuleDecisionStatus.FOUL_CANCELLED:
                return existing
            if existing is not None:
                self._processed_shots.pop(outcome.shot_id, None)
            state = self._require_playing()
            frame = state.current_frame
            if self._pending_fouls:
                raise PendingDecision("Resolve the pending foul before processing another shot")
            if frame.pending_respots:
                raise PendingDecision("Complete pending color respots before the next shot")
            if outcome.player is not frame.current_player:
                raise RuleStateConflict("Shot player does not match current player")
            if not outcome.confirmed:
                decision = RuleDecision(
                    outcome.shot_id,
                    RuleDecisionStatus.REVIEW_REQUIRED,
                    outcome.player,
                    message="Shot evidence requires confirmation",
                )
                self._processed_shots[outcome.shot_id] = decision
                return decision
            violations = self._violations(frame, outcome)
            if violations:
                return self._create_foul_candidate(outcome, violations)
            return self._apply_legal_outcome(outcome)

    def resolve_review(self, outcome: ShotOutcome) -> RuleDecision:
        with self._lock:
            prior = self._processed_shots.get(outcome.shot_id)
            if prior is None or prior.status is not RuleDecisionStatus.REVIEW_REQUIRED:
                raise RuleStateConflict("Shot is not awaiting review")
            if not outcome.confirmed:
                return prior
            self._processed_shots.pop(outcome.shot_id)
            return self.process_shot(outcome)

    def confirm_foul(self, foul_event_id: str) -> RuleDecision:
        with self._lock:
            foul = self._fouls.get(foul_event_id)
            if foul is None:
                raise UnknownFoul(f"Unknown foul event: {foul_event_id}")
            if foul.status is FoulStatus.CONFIRMED:
                return self._processed_shots[foul.shot.shot_id]
            if foul.status is not FoulStatus.CANDIDATE:
                raise UnknownFoul(f"Foul event is not confirmable: {foul_event_id}")
            prior_state = self.state
            prior_decision = self._processed_shots.get(foul.shot.shot_id)
            frame = prior_state.current_frame
            opponent = foul.shot.player.other()
            remaining_reds = frame.remaining_reds - foul.shot.potted_colors.count(BallColor.RED)
            if remaining_reds < 0:
                raise RuleStateConflict("Detected potted reds exceed remaining reds")
            pending_respots = frame.pending_respots
            if frame.phase in (RulePhase.EXPECT_RED, RulePhase.EXPECT_COLOR):
                pending_respots += tuple(
                    color for color in foul.shot.potted_colors if color in SNOOKER_COLOR_ORDER
                )
                next_phase = RulePhase.EXPECT_RED if remaining_reds else RulePhase.CLEARANCE
                expected = BallColor.RED if remaining_reds else BallColor.YELLOW
            else:
                next_phase = frame.phase
                expected = frame.expected_ball
            score_fields = self._score_fields(frame, opponent, foul.penalty_points, break_points=0)
            updated_frame = replace(
                frame,
                **score_fields,
                current_player=opponent,
                remaining_reds=remaining_reds,
                phase=next_phase,
                expected_ball=expected,
                pending_respots=pending_respots,
            )
            self._state = replace(prior_state, current_frame=updated_frame)
            foul.status = FoulStatus.CONFIRMED
            self._pending_fouls.pop(foul.event_id, None)
            event_ids = [
                self._append_event(
                    MatchEventType.FOUL_CONFIRMED,
                    player=opponent,
                    shot_id=foul.shot.shot_id,
                    score_delta=foul.penalty_points,
                    details={"foul_event_id": foul.event_id, "reasons": foul.reasons},
                ).event_id,
                self._append_event(
                    MatchEventType.PLAYER_SWITCHED,
                    player=opponent,
                    shot_id=foul.shot.shot_id,
                    details={"reason": "FOUL"},
                ).event_id,
            ]
            if pending_respots:
                event_ids.append(
                    self._append_event(
                        MatchEventType.RESPOT_PENDING,
                        player=opponent,
                        shot_id=foul.shot.shot_id,
                        details={"colors": pending_respots},
                    ).event_id
                )
            if frame.phase is RulePhase.RESPOTTED_BLACK:
                event_ids.extend(self._finish_frame_events(self._finish_current_frame()))
            decision = RuleDecision(
                foul.shot.shot_id,
                RuleDecisionStatus.FOUL_CONFIRMED,
                foul.shot.player,
                penalty_points=foul.penalty_points,
                foul_event_id=foul.event_id,
                message="Foul confirmed",
            )
            self._processed_shots[foul.shot.shot_id] = decision
            self._undo.append(
                UndoEntry(
                    prior_state,
                    tuple(event_ids),
                    foul.shot.shot_id,
                    prior_decision,
                    foul.event_id,
                    FoulStatus.CANDIDATE,
                )
            )
            return decision

    def cancel_foul(self, foul_event_id: str) -> RuleDecision:
        with self._lock:
            foul = self._fouls.get(foul_event_id)
            if foul is None or foul.status is not FoulStatus.CANDIDATE:
                raise UnknownFoul(f"Unknown pending foul event: {foul_event_id}")
            foul.status = FoulStatus.CANCELLED
            self._pending_fouls.pop(foul.event_id, None)
            decision = RuleDecision(
                foul.shot.shot_id,
                RuleDecisionStatus.FOUL_CANCELLED,
                foul.shot.player,
                foul_event_id=foul.event_id,
                message="Foul cancelled; match state unchanged",
            )
            self._processed_shots[foul.shot.shot_id] = decision
            self._append_event(
                MatchEventType.FOUL_CANCELLED,
                player=foul.shot.player,
                shot_id=foul.shot.shot_id,
                details={"foul_event_id": foul.event_id},
            )
            return decision

    def complete_respot(self, color: BallColor, observed_color: BallColor | None = None) -> MatchState:
        with self._lock:
            state = self._require_playing()
            frame = state.current_frame
            if color not in frame.pending_respots:
                raise InvalidRespot(f"No pending respot for {color.value}")
            if observed_color is not None and observed_color is not color:
                raise InvalidRespot("Observed color does not match pending respot")
            prior_state = state
            pending = list(frame.pending_respots)
            pending.remove(color)
            self._state = replace(state, current_frame=replace(frame, pending_respots=tuple(pending)))
            event = self._append_event(
                MatchEventType.RESPOT_COMPLETED,
                player=frame.current_player,
                details={"color": color.value},
            )
            self._undo.append(UndoEntry(prior_state, (event.event_id,)))
            return self._state

    def end_frame(self) -> MatchState:
        with self._lock:
            state = self._require_playing()
            frame = state.current_frame
            if frame.player_a_score == frame.player_b_score:
                self._state = replace(
                    state,
                    current_frame=replace(
                        frame,
                        phase=RulePhase.RESPOTTED_BLACK,
                        expected_ball=BallColor.BLACK,
                        colors_on_table=(BallColor.BLACK,),
                    ),
                )
                return self._state
            prior_state = state
            self._finish_current_frame()
            event_ids = tuple(self._finish_frame_events(self.state))
            self._undo.append(UndoEntry(prior_state, event_ids))
            return self.state

    def undo(self) -> MatchEvent | None:
        with self._lock:
            if not self._undo:
                return None
            entry = self._undo.pop()
            current = self.state
            self._state = entry.prior_state
            self.event_log.mark_undone(entry.event_ids)
            if entry.shot_id is not None:
                if entry.prior_decision is None:
                    self._processed_shots.pop(entry.shot_id, None)
                else:
                    self._processed_shots[entry.shot_id] = entry.prior_decision
            if entry.foul_event_id is not None and entry.prior_foul_status is not None:
                foul = self._fouls[entry.foul_event_id]
                foul.status = entry.prior_foul_status
                if entry.prior_foul_status is FoulStatus.CANDIDATE:
                    self._pending_fouls[foul.event_id] = foul
            return self._append_event(
                MatchEventType.UNDO,
                player=current.current_frame.current_player,
                details={"undone_event_ids": entry.event_ids},
            )

    def _apply_legal_outcome(self, outcome: ShotOutcome) -> RuleDecision:
        prior_state = self.state
        frame = prior_state.current_frame
        potted = outcome.potted_colors
        event_ids: list[str] = []
        if not potted:
            next_phase, expected = self._phase_after_miss(frame)
            updated_frame = replace(
                frame,
                current_player=frame.current_player.other(),
                current_break=0,
                phase=next_phase,
                expected_ball=expected,
            )
            self._state = replace(prior_state, current_frame=updated_frame)
            event_ids.append(
                self._append_event(MatchEventType.MISS, player=outcome.player, shot_id=outcome.shot_id).event_id
            )
            event_ids.append(
                self._append_event(
                    MatchEventType.PLAYER_SWITCHED,
                    player=updated_frame.current_player,
                    shot_id=outcome.shot_id,
                    details={"reason": "MISS"},
                ).event_id
            )
            decision = RuleDecision(outcome.shot_id, RuleDecisionStatus.MISS, outcome.player)
        elif frame.phase is RulePhase.EXPECT_RED:
            red_count = potted.count(BallColor.RED)
            if red_count > frame.remaining_reds:
                raise RuleStateConflict("Detected potted reds exceed remaining reds")
            points = red_count
            fields = self._score_fields(frame, outcome.player, points)
            updated_frame = replace(
                frame,
                **fields,
                remaining_reds=frame.remaining_reds - red_count,
                phase=RulePhase.EXPECT_COLOR,
                expected_ball=None,
            )
            self._state = replace(prior_state, current_frame=updated_frame)
            event_ids.append(self._score_event(outcome, points).event_id)
            decision = RuleDecision(outcome.shot_id, RuleDecisionStatus.LEGAL, outcome.player, points=points)
        elif frame.phase is RulePhase.EXPECT_COLOR:
            color = potted[0]
            points = SNOOKER_BALL_VALUES[color]
            fields = self._score_fields(frame, outcome.player, points)
            next_phase = RulePhase.EXPECT_RED if frame.remaining_reds else RulePhase.CLEARANCE
            expected = BallColor.RED if frame.remaining_reds else BallColor.YELLOW
            updated_frame = replace(
                frame,
                **fields,
                phase=next_phase,
                expected_ball=expected,
                pending_respots=frame.pending_respots + (color,),
            )
            self._state = replace(prior_state, current_frame=updated_frame)
            event_ids.append(self._score_event(outcome, points).event_id)
            event_ids.append(
                self._append_event(
                    MatchEventType.RESPOT_PENDING,
                    player=outcome.player,
                    shot_id=outcome.shot_id,
                    details={"colors": [color.value]},
                ).event_id
            )
            decision = RuleDecision(outcome.shot_id, RuleDecisionStatus.LEGAL, outcome.player, points=points)
        else:
            color = potted[0]
            points = SNOOKER_BALL_VALUES[color]
            fields = self._score_fields(frame, outcome.player, points)
            colors = tuple(item for item in frame.colors_on_table if item is not color)
            if frame.phase is RulePhase.RESPOTTED_BLACK or color is BallColor.BLACK:
                updated_frame = replace(frame, **fields, colors_on_table=colors)
                self._state = replace(prior_state, current_frame=updated_frame)
                event_ids.append(self._score_event(outcome, points).event_id)
                if frame.phase is RulePhase.RESPOTTED_BLACK:
                    self._finish_current_frame()
                    event_ids.extend(self._finish_frame_events(self.state))
                elif updated_frame.player_a_score == updated_frame.player_b_score:
                    self._state = replace(
                        self.state,
                        current_frame=replace(
                            updated_frame,
                            phase=RulePhase.RESPOTTED_BLACK,
                            expected_ball=BallColor.BLACK,
                            colors_on_table=(BallColor.BLACK,),
                        ),
                    )
                else:
                    self._finish_current_frame()
                    event_ids.extend(self._finish_frame_events(self.state))
            else:
                next_color = SNOOKER_COLOR_ORDER[SNOOKER_COLOR_ORDER.index(color) + 1]
                updated_frame = replace(
                    frame,
                    **fields,
                    colors_on_table=colors,
                    expected_ball=next_color,
                )
                self._state = replace(prior_state, current_frame=updated_frame)
                event_ids.append(self._score_event(outcome, points).event_id)
            decision = RuleDecision(outcome.shot_id, RuleDecisionStatus.LEGAL, outcome.player, points=points)
        self._processed_shots[outcome.shot_id] = decision
        self._undo.append(UndoEntry(prior_state, tuple(event_ids), outcome.shot_id))
        return decision

    def _create_foul_candidate(self, outcome: ShotOutcome, violations: tuple[str, ...]) -> RuleDecision:
        penalty = self._foul_penalty(self.state.current_frame, outcome)
        foul = FoulEvent(f"foul-{uuid4().hex}", outcome, violations, penalty)
        self._pending_fouls[foul.event_id] = foul
        self._fouls[foul.event_id] = foul
        decision = RuleDecision(
            outcome.shot_id,
            RuleDecisionStatus.FOUL_CANDIDATE,
            outcome.player,
            penalty_points=penalty,
            foul_event_id=foul.event_id,
            message="Foul requires confirmation",
        )
        self._processed_shots[outcome.shot_id] = decision
        self._append_event(
            MatchEventType.FOUL_CANDIDATE,
            player=outcome.player,
            shot_id=outcome.shot_id,
            details={"foul_event_id": foul.event_id, "reasons": violations, "penalty": penalty},
        )
        return decision

    @staticmethod
    def _violations(frame: FrameState, outcome: ShotOutcome) -> tuple[str, ...]:
        potted = outcome.potted_colors
        reasons: list[str] = []
        if BallColor.WHITE in potted:
            reasons.append("CUE_BALL_POTTED")
        reds = potted.count(BallColor.RED)
        colors = tuple(color for color in potted if color in SNOOKER_COLOR_ORDER)
        if frame.phase is RulePhase.EXPECT_RED:
            if colors:
                reasons.append("WRONG_BALL_POTTED")
        elif frame.phase is RulePhase.EXPECT_COLOR:
            if reds:
                reasons.append("WRONG_BALL_POTTED")
            if len(colors) > 1:
                reasons.append("MULTIPLE_COLORS_POTTED")
            if outcome.nominated_color is not None and colors and colors[0] is not outcome.nominated_color:
                reasons.append("WRONG_BALL_POTTED")
        elif potted:
            if len(potted) != 1 or potted[0] is not frame.expected_ball:
                reasons.append("CLEARANCE_ORDER")
        return tuple(dict.fromkeys(reasons))

    @staticmethod
    def _foul_penalty(frame: FrameState, outcome: ShotOutcome) -> int:
        values = [4]
        values.extend(SNOOKER_BALL_VALUES[color] for color in outcome.potted_colors if color in SNOOKER_BALL_VALUES)
        if frame.phase in (RulePhase.CLEARANCE, RulePhase.RESPOTTED_BLACK) and frame.expected_ball is not None:
            values.append(SNOOKER_BALL_VALUES[frame.expected_ball])
        if frame.phase is RulePhase.EXPECT_COLOR and outcome.nominated_color is not None:
            values.append(SNOOKER_BALL_VALUES[outcome.nominated_color])
        return max(values)

    @staticmethod
    def _phase_after_miss(frame: FrameState) -> tuple[RulePhase, BallColor | None]:
        if frame.phase is RulePhase.EXPECT_COLOR:
            if frame.remaining_reds:
                return RulePhase.EXPECT_RED, BallColor.RED
            return RulePhase.CLEARANCE, BallColor.YELLOW
        return frame.phase, frame.expected_ball

    @staticmethod
    def _score_fields(
        frame: FrameState, player: Player, points: int, break_points: int | None = None
    ) -> dict[str, int]:
        result = {
            "player_a_score": frame.player_a_score,
            "player_b_score": frame.player_b_score,
            "current_break": frame.current_break + points if break_points is None else break_points,
        }
        key = "player_a_score" if player is Player.PLAYER_A else "player_b_score"
        result[key] += points
        return result

    def _finish_current_frame(self) -> MatchState:
        state = self.state
        frame = state.current_frame
        if frame.player_a_score == frame.player_b_score:
            raise RuleStateConflict("A tied frame requires respotted black")
        winner = Player.PLAYER_A if frame.player_a_score > frame.player_b_score else Player.PLAYER_B
        finished_at = datetime.now(timezone.utc)
        finished = replace(
            frame,
            status=FrameStatus.FINISHED,
            phase=RulePhase.FRAME_COMPLETE,
            expected_ball=None,
            pending_respots=(),
            winner=winner,
        )
        result = FrameResult(
            frame.frame_number,
            frame.player_a_score,
            frame.player_b_score,
            winner,
            finished_at,
        )
        a_frames = state.player_a_frames + int(winner is Player.PLAYER_A)
        b_frames = state.player_b_frames + int(winner is Player.PLAYER_B)
        match_winner = winner if max(a_frames, b_frames) >= state.frames_to_win else None
        self._state = replace(
            state,
            status=MatchStatus.FINISHED if match_winner is not None else MatchStatus.PLAYING,
            player_a_frames=a_frames,
            player_b_frames=b_frames,
            current_frame=finished,
            completed_frames=state.completed_frames + (result,),
            winner=match_winner,
        )
        return self._state

    def _finish_frame_events(self, state: MatchState) -> list[str]:
        frame = state.current_frame
        ids = [
            self._append_event(
                MatchEventType.FRAME_FINISHED,
                player=frame.winner,
                details={
                    "player_a_score": frame.player_a_score,
                    "player_b_score": frame.player_b_score,
                },
            ).event_id
        ]
        if state.status is MatchStatus.FINISHED:
            ids.append(
                self._append_event(
                    MatchEventType.MATCH_FINISHED,
                    player=state.winner,
                    details={
                        "player_a_frames": state.player_a_frames,
                        "player_b_frames": state.player_b_frames,
                    },
                ).event_id
            )
        return ids

    def _score_event(self, outcome: ShotOutcome, points: int) -> MatchEvent:
        return self._append_event(
            MatchEventType.SCORE,
            player=outcome.player,
            shot_id=outcome.shot_id,
            score_delta=points,
            details={"potted_colors": [color.value for color in outcome.potted_colors]},
        )

    def _append_event(
        self,
        event_type: MatchEventType,
        player: Player | None = None,
        shot_id: str | None = None,
        score_delta: int = 0,
        details: dict[str, object] | None = None,
    ) -> MatchEvent:
        state = self.state
        event = MatchEvent(
            event_id=f"event-{uuid4().hex}",
            event_type=event_type,
            match_id=state.match_id,
            frame_number=state.current_frame.frame_number,
            timestamp=datetime.now(timezone.utc),
            player=player,
            shot_id=shot_id,
            score_delta=score_delta,
            details=dict(details or {}),
        )
        return self.event_log.append(event)

    def _require_playing(self) -> MatchState:
        state = self.state
        if state.status is MatchStatus.FINISHED or state.current_frame.status is not FrameStatus.PLAYING:
            raise MatchNotReady("Start an unfinished frame before processing rule events")
        return state
