# Known Limitations

1. 仓库没有真实斯诺克视频，因此 113 条视觉/UI Excel Acceptance Case 为 `DATA_REQUIRED`；合成测试不能代表真实光照、遮挡和高速运动性能。
2. P0 不实现长期多球 ID Tracking。Pot 使用短时路径（如果调用方提供）、Pocket ROI 活动和稳定前后数量变化；证据不足时返回 Candidate。
3. 传统 LAB 原型颜色分类需要按具体球桌灯光调参。极端混合光、严重高光或曝光变化可能产生 UNKNOWN。
4. 接触或成簇球使用轮廓与 Hough 的简化合并，无法保证 22 球密集开局全部分离；低置信结果会阻止自动计分。
5. Camera movement monitor 和分辨率失配可使标定失效，但没有实现 P3 的全自动重新标定。
6. 比赛事件默认保存在内存中；异常重启后明确要求重新初始化当前比赛状态。标定配置会持久化。
7. Streamlit 采用显式“处理下一帧/100 帧”方式，优先保证状态可控；不是高帧率生产级实时 UI。
8. White Pot 只产生零分异常/Review，不实现 P1 犯规罚分。
9. Current Break 仅为满足 P0 Undo 一致性的最小字段，不包含最高单杆等 P2 统计。

