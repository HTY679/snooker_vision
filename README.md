# Snooker Vision — P1

传统计算机视觉驱动的斯诺克自动计分与规则状态机。需求基线是仓库根目录的 `snooker_vision_user_stories_and_test_cases.xlsx`；P1 在保持 P0 视觉管线与回归行为的基础上增加比赛、局和规则处理。

## 已实现能力

- 视频文件或摄像头输入，黑帧、断流和分辨率失配提示
- 手工四角标定、透视矫正、六袋 ROI、JSON 持久化
- 基于 OpenCV 的静止球候选检测
- RED/YELLOW/GREEN/BROWN/BLUE/PINK/BLACK/WHITE/UNKNOWN 分类
- 多帧 STATIC/MOVING 判断与 `STATIC → MOVING → STATIC` Shot FSM
- Before/After 稳定状态、多帧状态差、Pot Candidate/Confirmed Pot
- P0 颜色分值、当前球员、幂等 Score Event、Undo
- P1 Match/Frame 模型、Best-of 比赛与局胜负
- 红球/彩球交替、清彩顺序、重摆提示、平分重置黑球
- 犯规候选的确认/取消、罚分、换人，以及整次击球原子 Undo
- JSONL 事件日志、幂等事件、快照恢复
- Streamlit 规则界面、CLI 管线和确定性事件 Demo
- Excel 151 条 P0 + 117 条 P1 Test Case 的 pytest 收集与追踪

P1 覆盖当前 Excel 基线中的核心比赛规则；完整裁判规则、长期多球 ID Tracking、云端和账户功能不在本迭代范围。详见 `docs/known_limitations.md`。

## 环境安装

需要 Python 3.11 或更高版本。PowerShell 示例：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install -e . --no-build-isolation
```

本仓库开发验证使用 Python 3.12 隔离环境。

## 1. 生成标定

摄像头：

```powershell
python scripts/calibrate.py --source 0 --output config/calibration.json
```

视频第一帧：

```powershell
python scripts/calibrate.py --source data/raw/static_table.mp4 --output config/calibration.json
```

依次点击球桌 `TL → TR → BR → BL`，再按界面提示点击六个袋口中心；按 Enter 保存，`R` 重置，`Esc` 取消。示例格式见 `config/calibration.example.json`。摄像头位置或分辨率变化后必须重新标定。

## 2. 运行 UI

```powershell
streamlit run src/snooker_vision/ui/app.py
```

界面支持创建比赛、开始/结束一局、展示目标球与阶段、确认重摆/犯规、恢复快照、打开视频/摄像头、确认/拒绝 Pot Candidate 和 Undo。

## 3. 运行 CLI

```powershell
python scripts/run_p0.py --source data/raw/red_pot_corner.mp4 --calibration config/calibration.json
```

摄像头输入使用 `--source 0`。无窗口批处理可增加 `--headless --max-frames 500`。

## 4. 运行确定性 Demo

```powershell
python scripts/demo_recorded_events.py
```

预期输出：Player A `0 → RED +1 → BLACK +7 = 8 → Undo = 1`。此 Demo 验证状态、计分、幂等和 Undo，不代表真实视觉视频已验收。

## 5. 运行测试

```powershell
python -m pytest -q
```

Excel 中每条 P0/P1 TC 都被收集为独立 pytest 参数。纯业务逻辑场景会执行；缺少对应真实视频的视觉/UI 验收场景明确 `SKIPPED`，原因以 `DATA_REQUIRED` 开头。不能把这些 Skipped 解读为通过。

## 配置与日志

- 全部阈值：`config/default.yaml`
- 运行时标定：`config/calibration.json`
- JSON 日志：`logs/snooker_vision.log`
- Ground Truth：`data/ground_truth/`

采集真实视频前请阅读 `docs/data_collection.md`；P1 设计、测试结果、限制和完成报告分别见 `docs/p1_design.md`、`docs/testing.md`、`docs/known_limitations.md` 和 `docs/p1_completion_report.md`。P0 报告保留在 `docs/p0_completion_report.md`，其中 Partial 与 `DATA_REQUIRED` 状态未被改写。
