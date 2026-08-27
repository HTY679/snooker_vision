# P1 Rules Design

## Scope

P1 adds a deterministic snooker match-rules layer above the existing P0 vision and shot pipeline. It covers the 16 P1 stories and 117 P1 test cases in `snooker_vision_user_stories_and_test_cases.xlsx` while preserving every P0 `DATA_REQUIRED` marker.

Implemented scope:

- Match and Frame lifecycle with Best-of 3/5 support.
- Red/color alternation and remaining-red tracking.
- Final-color clearance in yellow, green, brown, blue, pink, black order.
- Color-respot confirmation during the red phase.
- Miss-based player switching and legal-pot turn retention.
- Foul candidates, manual Confirm/Cancel, penalty awards and player switching.
- Tied-frame respotted black.
- Append-only event log, idempotency, atomic shot undo and restart recovery.

The system does not claim full referee-rule coverage. First-contact evidence, Foul and a Miss, Free Ball, Touching Ball and other advanced rulings remain outside P1.

## Domain model

`MatchState` owns both player identities, Best-of configuration, frame-win totals, match status and the current `FrameState`. `FrameState` owns scores, current player, current break, remaining reds, expected phase/ball, pending respots and frame status.

The principal rule states are:

```text
EXPECT_RED
  ├─ legal red pot ───────────────→ EXPECT_COLOR
  ├─ miss ────────────────────────→ EXPECT_RED (switch player)
  └─ foul candidate ──────────────→ pending manual decision

EXPECT_COLOR
  ├─ legal color, reds remain ────→ pending respot → EXPECT_RED
  ├─ legal color, no reds remain ─→ pending respot → CLEARANCE(YELLOW)
  ├─ miss ────────────────────────→ EXPECT_RED/CLEARANCE (switch player)
  └─ foul candidate ──────────────→ pending manual decision

CLEARANCE(YELLOW..BLACK)
  ├─ expected color potted ───────→ next expected color
  ├─ miss ────────────────────────→ same expected color (switch player)
  └─ final black / end decision ──→ FRAME_ENDED or RESPOTTED_BLACK
```

## Decisions and transactions

`ShotOutcome` is the boundary between vision/application and rules. `SnookerRulesEngine.process_shot()` returns a `RuleDecision` rather than letting UI code mutate scores. The decision records points, penalty, resulting player/phase, foul ID and status.

Each processed shot is one atomic transaction. Its score, phase change, remaining-red change, player change, pending respot/foul and emitted events share the same undo snapshot. Duplicate shot IDs are idempotent and return the prior decision.

Foul evidence first produces `FOUL_CANDIDATE`. Until a user confirms or cancels it, later shots are blocked. Confirming awards the opponent:

```text
penalty = max(4, value(ball on), highest value involved)
```

Cancel restores the pre-shot state without awarding points. Both paths are logged.

## Respot and clearance

During red/color play, a legally potted color creates `pending_respots`; no new shot is accepted until its respot is confirmed. Respot confirmation never awards points a second time. After the final red and its following color are resolved, the phase becomes `CLEARANCE` and colors are removed in ascending value order rather than respotted.

When a frame ends level, the engine enters respotted-black play instead of choosing a winner. The next score or confirmed foul resolves the frame.

## Persistence and audit

`EventLog` writes newline-delimited JSON. Every `MatchEvent` has an event ID, match/frame/shot association, type, timestamp and payload. Re-appending an existing event ID is a no-op. Events can be queried by frame or shot, and reload reconstructs the in-memory indexes.

`P1Application` stores an atomic JSON snapshot beside the event log after rule mutations. On startup, the Streamlit UI restores a compatible active match and surfaces a restore message. Event log plus snapshot provides auditability and operational recovery; it is not a multi-writer database.

## P0 integration

The P0 frame-processing pipeline is unchanged through detection, classification, motion, Shot FSM, before/after comparison and pot review. A completed P0 shot invokes an application hook; `P1Application` aggregates its confirmed potted balls into one `ShotOutcome` and sends it to the rules engine.

The P1 Match/Frame state is authoritative for rules scoring. The legacy P0 scoreboard is synchronized only as a compatibility view, preventing independent score ledgers. P0 tests remain part of every full regression run.

## Verification strategy

- Unit tests cover models, invariants, red/color phases, clearance, respots, fouls, match progression, event log and snapshots.
- Application tests cover whole-shot aggregation, review decisions, persistence and P0/P1 view synchronization.
- Excel acceptance maps all 117 P1 IDs and validates the workbook traceability counts.
- Five real cue-ball visual cases remain `DATA_REQUIRED`; no synthetic result is presented as real-video acceptance.
- Streamlit browser smoke testing validates match creation, frame start, rule-state rendering and refresh recovery.
