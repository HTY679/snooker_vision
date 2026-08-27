# P0 Design

## Calibration

人工角点顺序固定为 TL、TR、BR、BL。系统拒绝重复、过近、越界、自交和面积过小的四边形。六袋必须使用六个标准 ID，位于矫正后桌面范围内且不能异常重叠。标定通过临时文件替换方式原子保存。

## Ball Detection and Color

球检测只在 STATIC 状态执行。算法从 HSV 台呢掩膜中提取非台呢区域，使用轮廓圆度、半径、长宽比与可选 Hough Circle 合并候选；长球杆和大面积人体区域被形状或面积门控。颜色在球内部圆盘采样，裁去亮度极端像素后与配置中的 LAB 原型比较。低距离优势、无彩中灰或低置信样本返回 UNKNOWN。

## Motion and Shot FSM

MotionDetector 先估计全局位移，再对帧差连通域按面积和长宽比过滤。大范围前景变化和明显相机移动不会直接形成 Shot。`moving_confirmation_frames` 与 `static_confirmation_frames` 控制状态防抖。

ShotFSM 只有在已存在可信稳定 Before State 时才允许进入 Shot；结束后必须得到时间戳更晚、置信度达标的稳定 After State。低置信度进入 Review Required，不自动计分。

## Pot Detection

Pot Detection 必须同时满足稳定前后数量减少和袋口证据。证据来源可以是：

- 临时球路径终点靠近袋口且距离持续减小；或
- Shot 期间某 Pocket ROI 出现足够活动。

只有稳定缺失且证据、置信度均达到阈值才产生 Confirmed Pot。仅消失但缺少袋口证据产生 Pot Candidate；单帧缺失产生 UNKNOWN；After 中重新出现则不产生 Pot Event。

## Scoring and Undo

P0 只实现颜色值 1～7。White 和 Unknown 不增加正分。ScoreEngine 以 Pot Event ID 幂等；重复提交返回已有事件且不重复加分。Undo 恢复事件前 ScoreboardState，包括双方比分、Current Player 和最小 Current Break，并将关联 Score/Pot/Shot 标记为 undone/reverted。

## Error Handling

缺标定、坏配置、非法角点、断流、黑帧和分辨率变化均产生明确状态或异常并写日志，不静默降级为正常计分。

