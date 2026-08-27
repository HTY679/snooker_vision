# P0 Requirement Traceability

需求来源：`snooker_vision_user_stories_and_test_cases.xlsx`。Excel 测试在 `tests/acceptance/test_excel_p0_acceptance.py` 中动态加载，因此新增、删除或重复 TC 会直接影响测试收集或完整性测试。

| Story | Module | Excel TC | C/H/M/L | Automated evidence | Status |
|---|---|---:|---:|---|---|
| P0-US01 | `calibration/calibrator.py` | US01-01..10 (10) | 0/7/3/0 | synthetic ROI/calibration unit tests; real cases DATA_REQUIRED | Partial |
| P0-US02 | `calibration/calibrator.py` | US02-01..08 (8) | 0/7/1/0 | geometry/round-trip unit tests; video drift DATA_REQUIRED | Partial |
| P0-US03 | `detection/ball_detector.py` | US03-01..14 (14) | 0/12/2/0 | synthetic ball/cue tests; real table footage DATA_REQUIRED | Partial |
| P0-US04 | `classification/color_classifier.py` | US04-01..14 (14) | 0/14/0/0 | nine-output synthetic tests; lighting footage DATA_REQUIRED | Partial |
| P0-US05 | `motion/motion_detector.py` | US05-01..10 (10) | 0/10/0/0 | confirmation/shift unit tests; motion videos DATA_REQUIRED | Partial |
| P0-US06 | `game_state/shot_fsm.py` | US06-01..10 (10) | 0/9/1/0 | deterministic FSM tests; real shot videos DATA_REQUIRED | Partial |
| P0-US07 | `game_state/state_estimator.py` | US07-01..08 (8) | 0/7/1/0 | stable snapshot tests; full video continuity DATA_REQUIRED | Partial |
| P0-US08 | `game_state/state_estimator.py` | US08-01..09 (9) | 0/9/0/0 | state-diff tests; occlusion footage DATA_REQUIRED | Partial |
| P0-US09 | `calibration/calibrator.py` | US09-01..08 (8) | 0/6/2/0 | six-pocket validation/persistence; moved-camera footage DATA_REQUIRED | Partial |
| P0-US10 | `game_state/pot_detector.py` | US10-01..14 (14) | 10/4/0/0 | synthetic confirmed/candidate/bounce tests; all Excel video cases DATA_REQUIRED | Partial |
| P0-US11 | `scoring/engine.py` | US11-01..12 (12) | 1/10/1/0 | all 12 Excel cases executable | Done |
| P0-US12 | `scoring/engine.py`, `application/service.py` | US12-01..09 (9) | 1/7/1/0 | all 9 Excel cases executable | Done |
| P0-US13 | `scoring/engine.py`, `application/service.py` | US13-01..08 (8) | 0/6/1/1 | all 8 Excel cases executable | Done |
| P0-US14 | `scoring/engine.py`, `application/service.py` | US14-01..09 (9) | 3/6/0/0 | all 9 Excel cases executable | Done |
| P0-US15 | `ui/app.py` | US15-01..08 (8) | 0/5/2/1 | UI implemented; device/layout acceptance DATA_REQUIRED | Partial |

“Partial” 表示实现和合成测试存在，但 Excel 指定的真实视觉或设备验收数据尚未提供；不是遗漏代码，也不能解释为测试通过。

