# Testing

## Test layers

- `tests/unit/`：dataclass、配置、标定几何、检测/分类合成图、Motion/Shot、Pot、Scoring/Undo。
- `tests/integration/`：完整 recorded event fixture 演示。
- `tests/acceptance/`：直接从 Excel 加载 151 条 P0 TC，并保持 TC ID、优先级和 Story 追踪。

## DATA_REQUIRED policy

依赖真实球桌、人体/球杆遮挡、摄像头抖动、袋口弹回或窗口尺寸的 Excel Case，在对应资产不存在时调用 `pytest.skip("DATA_REQUIRED: ...")`。它们会被 pytest 收集，但不会伪造为 Passed。

当前可执行 Excel Case 是 P0-US11～US14 的 38 条纯计分、球员和 Undo 场景。视觉层另外通过合成单元测试验证算法契约，但合成测试不替代真实视频验收。

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

