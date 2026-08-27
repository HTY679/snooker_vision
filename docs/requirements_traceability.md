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

## P1 Requirement Traceability

P1 测试在 `tests/acceptance/test_excel_p1_acceptance.py` 中动态加载工作簿的 117 条 TC。完整性测试同时核对 16 个 Story 的 Critical/High/Medium/Low 分布与追踪矩阵。

| Story | Capability / Module | Excel TC | Automated evidence | Status |
|---|---|---:|---|---|
| P1-US01 | 比赛初始化；`rules/engine.py` | 7 | Match/Frame 初始化、默认名、Best-of 校验 | Done |
| P1-US02 | 红球阶段规则；`rules/engine.py` | 7 | 红球、空杆、非法彩球、最后红球 | Done |
| P1-US03 | 彩球阶段规则；`rules/engine.py` | 9 | 2～7 分、空杆、多彩球/白球犯规候选 | Done |
| P1-US04 | 彩球重摆；`rules/engine.py` | 7 | pending respot、确认、错误观测、Undo | Done |
| P1-US05 | 红球数量管理；`rules/engine.py` | 7 | 递减、边界、下溢保护、Undo | Done |
| P1-US06 | 清彩阶段；`rules/engine.py` | 10 | 黄→绿→棕→蓝→粉→黑、非法顺序 | Done |
| P1-US07 | 未得分自动换人；`rules/engine.py` | 7 | 红/彩/清彩空杆和事件记录 | Done |
| P1-US08 | 合法得分保留球权；`rules/engine.py` | 6 | 红/彩/清彩连续击球与当前球员 | Done |
| P1-US09 | 白球落袋识别；视觉 + Review Gate | 6 | 1 条规则契约通过；5 条真实视觉 TC `DATA_REQUIRED` | Partial |
| P1-US10 | 常见犯规候选；`rules/engine.py` | 7 | 错误目标、多球、白球、清彩顺序 | Done |
| P1-US11 | 罚分计算；`rules/engine.py` | 8 | `max(4, ball-on, highest involved)` 与对手加分 | Done |
| P1-US12 | 人工确认/取消；`p1_service.py` | 7 | Confirm/Cancel、阻塞后续击球、幂等 | Done |
| P1-US13 | Frame 生命周期；`rules/engine.py` | 7 | Start/Playing/End、下一局和状态保护 | Done |
| P1-US14 | Frame 获胜判断；`rules/engine.py` | 7 | 比分胜者、平分重置黑球、胜局累计 | Done |
| P1-US15 | Best-of 比赛；`rules/engine.py` | 8 | BO3/BO5、提前结束、胜者和新比赛保护 | Done |
| P1-US16 | 比赛事件日志；`event_log.py` | 7 | JSONL、查询、幂等、恢复和 Undo 审计 | Done |

P1 总计 16 个 Story：15 Done、1 Partial；112/117 条 Excel TC 执行通过，5 条 P1-US09 真实视觉 TC 保持 `DATA_REQUIRED`。P0 上表的 Partial 状态与原始标记不因 P1 而改变。
