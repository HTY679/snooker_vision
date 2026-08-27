# Testing

## Test layers

- `tests/unit/`：dataclass、配置、标定几何、检测/分类合成图、Motion/Shot、Pot、P0 Scoring/Undo，以及 P1 Match/Frame、规则、清彩、犯规、事件日志和快照。
- `tests/integration/`：完整 recorded event fixture 演示。
- `tests/acceptance/`：直接从 Excel 加载 151 条 P0 + 117 条 P1 TC，并保持 TC ID、优先级和 Story 追踪。

## DATA_REQUIRED policy

依赖真实球桌、人体/球杆遮挡、摄像头抖动、袋口弹回或窗口尺寸的 Excel Case，在对应资产不存在时调用 `pytest.skip("DATA_REQUIRED: ...")`。它们会被 pytest 收集，但不会伪造为 Passed。

当前可执行 Excel Case 是 P0-US11～US14 的 38 条纯计分、球员和 Undo 场景。视觉层另外通过合成单元测试验证算法契约，但合成测试不替代真实视频验收。

P1 中 112/117 条规则与比赛 Case 已执行通过；P1-US09 的 5 条真实白球落袋/离台视觉 Case 保持 `DATA_REQUIRED`。P0 原有 113 条 skip 均未删除或改成 Passed。

## P1 验证结果（2026-08-27）

- 全量 pytest：368 collected，250 passed，118 skipped，0 failed。
- P1 Excel acceptance 文件：114 passed，5 skipped；其中 112 条是 Excel TC，另外 2 条是工作簿映射完整性检查。
- 覆盖率：项目总计 74%，`rules/engine.py` 96%，`rules/event_log.py` 98%。
- Streamlit 冒烟：创建 Alice/Bob BO3、开始 Frame、显示 `EXPECT_RED / RED / 15`、刷新恢复比赛和事件，页面无浏览器错误或警告。

## Commands

```powershell
python -m pytest -q
python -m pytest tests/unit -q
python -m pytest tests/integration -q
python -m pytest tests/acceptance -q
python -m pytest --cov=snooker_vision --cov-report=term-missing
```

## Adding video fixtures

把视频放入 `data/raw/`，在 `data/ground_truth/` 新建与 `schema.json` 一致的 JSON，并补齐帧区间。随后为对应 Excel TC 注册视频路径与断言；在 Ground Truth 未完成前不要移除 `DATA_REQUIRED`。
