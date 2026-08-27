# Known Limitations

1. 仓库没有真实斯诺克视频，因此 113 条视觉/UI Excel Acceptance Case 为 `DATA_REQUIRED`；合成测试不能代表真实光照、遮挡和高速运动性能。
2. P0 不实现长期多球 ID Tracking。Pot 使用短时路径（如果调用方提供）、Pocket ROI 活动和稳定前后数量变化；证据不足时返回 Candidate。
3. 传统 LAB 原型颜色分类需要按具体球桌灯光调参。极端混合光、严重高光或曝光变化可能产生 UNKNOWN。
4. 接触或成簇球使用轮廓与 Hough 的简化合并，无法保证 22 球密集开局全部分离；低置信结果会阻止自动计分。
5. Camera movement monitor 和分辨率失配可使标定失效，但没有实现 P3 的全自动重新标定。
6. P1 比赛快照和 JSONL 事件日志会持久化并支持重启恢复；它们是单机文件存储，不提供并发写入、远程复制或数据库级事务保证。
7. Streamlit 采用显式“处理下一帧/100 帧”方式，优先保证状态可控；不是高帧率生产级实时 UI。
8. P1 可把白球落袋作为犯规候选并按确认决定罚分，但 P1-US09 的 5 条真实白球视觉验收仍缺视频，保持 `DATA_REQUIRED`。
9. Current Break 仍是最小字段，不包含最高单杆等 P2 统计。
10. P1 覆盖 Excel 基线中的核心规则，但不宣称实现全部 WPBSA 裁判规则；首碰球判定、Foul and a Miss、Free Ball、Touching Ball、重新摆球争议与复杂斯诺克判罚不在当前范围。
11. 犯规确认由人工 Review Gate 完成；视觉层不能可靠提供首碰球和所有犯规证据时，系统不会自动作出裁判级判断。
