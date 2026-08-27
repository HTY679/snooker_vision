# P1 Completion Report

Date: 2026-08-27  
Repository: `HTY679/snooker_vision`  
Development branch: `p1-rules`

## Executive result

P1 core rules, match/frame lifecycle, foul review, event audit, atomic undo, restart recovery and Streamlit rule-state UI are implemented. The complete P0/P1 regression suite has zero failures. Of 117 P1 Excel test cases, 112 executable cases pass and 5 real cue-ball vision cases remain explicitly `DATA_REQUIRED`.

No P0 Partial story was changed to Done, no existing `DATA_REQUIRED` marker was removed, and P1 was not merged into `main`.

## Starting Git state

The required Git preparation was completed before source modification:

- Initial branch: `main`.
- Initial worktree: clean; status was `## main...origin/main`.
- `git fetch origin`, `git checkout main`, and `git pull origin main` completed; local main was already current.
- P1 base main commit: `15cb894f12d2ca445f36660f0726c953237945b1` (`P0-0`).
- New branch: `p1-rules`.
- Upstream established before development: `origin/p1-rules`.
- No uncommitted P0 work existed at start, so no stash, reset or deletion was performed.

## Delivered modules

### Domain and rules

- Match, Frame, Player, ShotOutcome, FoulEvent, RuleDecision and MatchEvent models.
- Match/Frame invariants and Best-of 3/5 progression.
- `EXPECT_RED`, `EXPECT_COLOR`, `CLEARANCE`, respot and respotted-black states.
- Legal-pot scoring, turn retention, miss switching and remaining-red management.
- Ordered yellow-to-black clearance.
- Foul candidate review, Confirm/Cancel and `max(4, ball-on, highest involved)` penalty calculation.
- Idempotent shot processing and whole-shot atomic Undo.

### Persistence and integration

- Append-only JSONL event log with event/shot/frame indexes and undo audit.
- Atomic active-match snapshots and restart restore.
- P1 service composed over the P0 completed-shot hook.
- P1 rules state is authoritative; the P0 scoreboard remains a synchronized compatibility view.

### UI

- Match creation with player names and Best-of selection.
- Frame start/next-frame controls.
- Current phase, expected ball, remaining reds, scores, current player and frame wins.
- Respot confirmation, foul Confirm/Cancel, event history and Undo.
- Automatic active-match restoration after UI refresh/restart.

## Requirement and acceptance status

Source workbook: `snooker_vision_user_stories_and_test_cases.xlsx`.

| Metric | Result |
|---|---:|
| P1 stories | 16 |
| Done | 15 |
| Partial | 1 (`P1-US09`) |
| P1 Excel test cases | 117 |
| P1 Excel cases passed | 112 |
| P1 Excel cases `DATA_REQUIRED` | 5 |
| Critical / High / Medium / Low | 36 / 67 / 12 / 2 |

The five outstanding cases are `TC-P1-US09-01` through `TC-P1-US09-05`. They require real cue-ball pot/off-table visual evidence. The remaining P1-US09 rule contract is executable. These skips are evidence gaps, not Passed results.

P0 regression status is preserved: its original 113 skipped real-video/UI acceptance cases and all Partial story labels remain unchanged.

## Verification evidence

Environment: project `.venv`, Python 3.12.

```text
python -m compileall -q src tests
PASS

python -m pytest -q
250 passed, 118 skipped, 0 failed (368 collected)

python -m pytest tests/acceptance/test_excel_p1_acceptance.py -q
114 passed, 5 skipped
```

The P1 acceptance file result includes 112 Excel cases plus 2 workbook-mapping integrity tests. Coverage verification reported 74% overall, 96% for `rules/engine.py`, and 98% for `rules/event_log.py`.

Streamlit was also exercised in the in-app browser: an Alice/Bob Best-of-3 match was created, Frame 1 started, `EXPECT_RED / RED / 15` and frame-win state rendered, then a refresh restored the active match and events without browser errors or warnings.

## Known limitations and follow-up evidence

- Supply real fixed-camera clips and ground truth for the five P1-US09 cue-ball scenarios before changing their status.
- P0 visual stories still need the previously documented real-video corpus; P1 does not close those gaps.
- Full WPBSA referee semantics such as first contact, Foul and a Miss, Free Ball and Touching Ball are outside the Excel P1 baseline and are not claimed.
- JSONL/snapshot persistence is intended for one local process, not concurrent distributed operation.

## Git handoff

- Branch: `p1-rules`.
- Base: main commit `15cb894f12d2ca445f36660f0726c953237945b1`.
- Expected P1 commit count after this report commit: 6.
- Remote: `origin/p1-rules`.
- Merge status: not merged; `main` remains at the base commit.

The exact SHA of the commit containing this report cannot be embedded in that same commit without changing its SHA. The final delivery message records the verified final commit SHA, remote equality, clean-worktree status and commit count after push.
