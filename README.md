# Snooker Vision — P0

传统计算机视觉驱动的斯诺克自动计分 Proof of Concept。需求基线是仓库根目录的 `snooker_vision_user_stories_and_test_cases.xlsx`，范围严格限制在 P0。

## 已实现能力

- 视频文件或摄像头输入，黑帧、断流和分辨率失配提示
- 手工四角标定、透视矫正、六袋 ROI、JSON 持久化
- 基于 OpenCV 的静止球候选检测
- RED/YELLOW/GREEN/BROWN/BLUE/PINK/BLACK/WHITE/UNKNOWN 分类
- 多帧 STATIC/MOVING 判断与 `STATIC → MOVING → STATIC` Shot FSM
- Before/After 稳定状态、多帧状态差、Pot Candidate/Confirmed Pot
- P0 颜色分值、当前球员、幂等 Score Event、Undo
- Streamlit 计分界面、CLI 管线和确定性事件 Demo
- Excel 151 条 P0 Test Case 的 pytest 收集与追踪

不包含完整斯诺克规则、犯规罚分、自动换人、彩球重摆、长期多球 ID Tracking、云端或账户功能。

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

界面支持打开视频/摄像头、逐帧或批量处理、切换球员、确认/拒绝 Pot Candidate、Undo，以及运行无需真实视频的确定性 P0 Demo。

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

Excel 中每条 P0 TC 都被收集为独立 pytest 参数。纯业务逻辑场景会执行；缺少对应真实视频的视觉/UI 验收场景明确 `SKIPPED`，原因以 `DATA_REQUIRED` 开头。不能把这些 Skipped 解读为通过。

## 配置与日志

- 全部阈值：`config/default.yaml`
- 运行时标定：`config/calibration.json`
- JSON 日志：`logs/snooker_vision.log`
- Ground Truth：`data/ground_truth/`

采集真实视频前请阅读 `docs/data_collection.md`；架构、测试结果与限制分别见 `docs/architecture.md`、`docs/testing.md` 和 `docs/p0_completion_report.md`。

