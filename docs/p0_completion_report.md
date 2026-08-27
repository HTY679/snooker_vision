# P0 Completion Report

Date: 2026-08-27  
Baseline: `snooker_vision_user_stories_and_test_cases.xlsx`

## Outcome

P0 可运行项目已经完成：依赖可安装、包可编辑安装、CLI/标定/UI 可启动、确定性 Demo 可执行、pytest 全量回归无失败。真实视频资产尚未提供，因此所有依赖真实视觉或设备布局的 Excel Acceptance Case 保持 `DATA_REQUIRED`，没有伪造通过。

## Story status

| Metric | Count |
|---|---:|
| P0 User Story | 15 |
| Done | 4 |
| Partial | 11 |
| Blocked | 0 |

| Story | Status | Result |
|---|---|---|
| P0-US01 球桌区域识别 | Partial | 自动 ROI、固定标定和异常状态已实现；真实场景 DATA_REQUIRED |
| P0-US02 透视矫正 | Partial | 四角验证、透视矩阵、分辨率失配已测试；1000 帧漂移视频 DATA_REQUIRED |
| P0-US03 台球检测 | Partial | STATIC 轮廓/Hough 检测及负向合成测试通过；真实 22 球/遮挡视频 DATA_REQUIRED |
| P0-US04 颜色分类 | Partial | 八色+UNKNOWN 合成测试通过；真实强弱光视频 DATA_REQUIRED |
| P0-US05 STATIC/MOVING | Partial | 多帧门控、慢停窗口和全局抖动防护已实现；真实运动视频 DATA_REQUIRED |
| P0-US06 Shot Detection | Partial | Shot FSM 单杆唯一性测试通过；真实多碰库/短停视频 DATA_REQUIRED |
| P0-US07 Before State | Partial | 稳定快照和低置信门控已实现；真实连续比赛视频 DATA_REQUIRED |
| P0-US08 After State | Partial | 稳定 After 和状态差已实现；真实遮挡抖动视频 DATA_REQUIRED |
| P0-US09 六袋 ROI | Partial | 六袋验证、持久化和重启加载测试通过；移动摄像头视频 DATA_REQUIRED |
| P0-US10 Pot Detection | Partial | Confirmed/Candidate/Unknown/弹回合成测试通过；10 条 Critical 视频 TC DATA_REQUIRED |
| P0-US11 基础得分 | Done | 12/12 Excel Case Passed |
| P0-US12 比分更新 | Done | 9/9 Excel Case Passed |
| P0-US13 当前球员 | Done | 8/8 Excel Case Passed |
| P0-US14 Undo | Done | 9/9 Excel Case Passed，含比分、Break、Player、事件状态 |
| P0-US15 基础 UI | Partial | 页面和内置 Demo 已在本地浏览器验证；1080p/小窗口/断摄像头验收资产 DATA_REQUIRED |

Partial 的原因是缺少外部验收数据，不是代码模块缺失。详细 Story→Code→TC 见 `requirements_traceability.md`。

## Test result

最后一次全量覆盖率回归：

| Metric | Result |
|---|---:|
| Pytest items | 200 |
| Passed | 87 |
| Failed | 0 |
| Skipped | 113 |
| DATA_REQUIRED | 113 |
| Blocked by implementation bug | 0 |
| Python coverage | 67% overall |

Excel P0 Acceptance 子集：

| Priority | Total | Passed | Failed | DATA_REQUIRED |
|---|---:|---:|---:|---:|
| Critical | 15 | 5 | 0 | 10 |
| High | 119 | 29 | 0 | 90 |
| Medium | 15 | 3 | 0 | 12 |
| Low | 2 | 1 | 0 | 1 |
| Total | 151 | 38 | 0 | 113 |

Critical Passed：US11 事件幂等、US12 重复提交、US14 核心 Undo 三项。Critical DATA_REQUIRED 全部是 P0-US10 真实 Pot Detection 视频：US10-01、02、03、06、07、08、09、10、11、14。

High Passed 29 条来自 US11～US14；其余 90 条依赖真实视觉或 UI/设备验收。除此之外，49 个 unit/integration/基线完整性测试 Passed。

## Fix and regression history

- 首轮：85 Passed、2 Failed、113 Skipped。
- 修复中性灰色误分类：新增配置化 achromatic/black/white 门控。
- 修复 Shot FSM 测试时间线：After State 时间戳严格晚于 Shot Start。
- 第二轮及最终覆盖率回归：87 Passed、0 Failed、113 Skipped。

## Demo capability

确定性 recorded-event Demo 已通过：

```text
Player A 0
→ RED Confirmed Pot
→ Player A 1
→ BLACK Confirmed Pot
→ Player A 8
→ Undo
→ Player A 1
```

Streamlit 页面已验证显示 Player A/B、Current Player、System State、Motion、Current Break、Last Shot、Last Potted Ball、Score Delta、Confidence、Review Status、Switch Player 和 Undo。页面内置 Demo 实际渲染结果为 `0 → 1 → 8 → 1`。

真实视觉链路的代码路径完整，但必须在提供视频和标定后才能给出真实准确率结论。

## Required real videos

请按 `data_collection.md` 提供：

- `static_table.mp4`
- `red_pot_corner.mp4`
- `red_pot_middle.mp4`
- `black_pot.mp4`
- `ball_bounce_out.mp4`
- `cue_occlusion.mp4`
- `hand_occlusion.mp4`
- `slow_roll.mp4`
- `fast_shot.mp4`

每段视频还需要符合 `data/ground_truth/schema.json` 的 Ground Truth 和已复核帧区间。

## Run commands

```powershell
python -m pip install -r requirements.txt
python -m pip install -e . --no-build-isolation
python scripts/calibrate.py --source 0 --output config/calibration.json
streamlit run src/snooker_vision/ui/app.py
python scripts/demo_recorded_events.py
python -m pytest -q
```

## Known limitations and next step

完整限制见 `known_limitations.md`。下一步仍属于 P0 验收：采集上述视频、标注 Ground Truth、针对实际球桌调整 `config/default.yaml`，然后逐条移除相应 `DATA_REQUIRED` 并重新执行 Critical→High 回归。不得在这些验证完成前声称真实视觉 P0 已达到生产准确率。
