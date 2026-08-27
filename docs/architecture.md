# P0 Architecture

## 设计目标

P0 只证明固定摄像头可以将一次可靠落袋转换为可撤销比分。架构将输入、视觉、状态、计分和 UI 分离，允许视觉层用真实 OpenCV 实现，也允许测试层注入合成状态或 recorded event fixture。

## 数据流

```text
FrameSource
  → FrameQualityGate
  → Calibration / PerspectiveTransformer / PocketROI
  → MotionDetector ──────────────→ ShotFSM
  → BallDetector → ColorClassifier → StableStateEstimator
                                      → Before / After
                                      → PotDetector
                                      → Review Gate
                                      → ScoreEngine / Player / Undo
                                      → Streamlit UI
```

## 分层

- `domain/`：跨层 dataclass 和 Enum；不依赖 OpenCV 或 UI。
- `input/`：视频与摄像头生命周期、帧质量。
- `calibration/`：四角验证、透视矩阵、六袋 ROI、持久化和位置失配检测。
- `detection/`：STATIC 画面的非台呢圆形候选检测。
- `classification/`：LAB 原型距离、无彩色门控和 UNKNOWN。
- `motion/`：全局位移过滤、紧凑运动区域过滤、多帧确认。
- `game_state/`：稳定状态聚合、Shot FSM、状态差、袋口活动和 Pot 证据。
- `scoring/`：颜色映射、事件幂等、球员切换锁、快照式 Undo。
- `application/`：组合各层并提供 UI/CLI 友好的服务接口。
- `ui/`：仅展示和调用应用服务，不实现视觉或计分规则。

## 依赖规则

视觉层不能修改比分；只有 Confirmed Pot 可以进入 ScoreEngine。ScoreEngine 不读取图像；UI 不直接修改内部得分字段。Shot 创建时固定 Player，从而避免 Shot 中途切换导致归属错误。

## P0 数据模型

核心对象包括 `Ball`、`ColorCounts`、`TableState`、`ShotEvent`、`PotEvidence`、`PotEvent`、`ScoreEvent` 和 `ScoreboardState`。所有事件具有明确 ID；Score Event 使用 Pot Event ID 作为幂等来源。

