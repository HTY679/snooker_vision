# Real-video Data Collection

## Common setup

1. 固定摄像头，完整覆盖球桌和六袋；建议 1080p、30 fps 或更高。
2. 关闭自动数字变焦，尽量锁定曝光、白平衡和焦距。
3. 标定后不要移动摄像头；记录分辨率、帧率、机位高度和照明条件。
4. 每段视频开始和结束至少保留 2 秒完全静止画面。
5. 不剪掉 Shot 前后的稳定帧；保留原始编码文件。
6. 每个场景建议录制不少于 5 次，并包含不同球桌区域和光照。

## Required files

| File | Required content | Key expected result |
|---|---|---|
| `static_table.mp4` | 标准球局或多色静止球，含至少 5 秒静止 | 稳定 ROI、STATIC、球数/颜色 Ground Truth |
| `red_pot_corner.mp4` | 红球进入任一角袋 | 一个 RED Confirmed Pot |
| `red_pot_middle.mp4` | 红球进入中袋 | 一个 RED Confirmed Pot |
| `black_pot.mp4` | 黑球真实入袋 | BLACK Confirmed Pot、+7 |
| `ball_bounce_out.mp4` | 球进入袋口区域后弹回并留在台面 | NO_POT |
| `cue_occlusion.mp4` | 球杆遮住球后移开，球仍在台面 | 不生成 Pot/虚假 Shot |
| `hand_occlusion.mp4` | 手遮住球后移开 | 不生成 Pot；恢复稳定状态 |
| `slow_roll.mp4` | 球极慢滚动后真正停止 | 停止前保持 MOVING |
| `fast_shot.mp4` | 一杆带动多球、碰库 | 仅一个 Shot Event |

## Annotation procedure

- 复制 `data/ground_truth/example_red_pot.json`，填写唯一 `video_id`。
- 标注 `frame_start`、`frame_end`、Before/After 各颜色数量、预期 Pot 类型/颜色/数量和预期得分。
- 对遮挡或弹袋视频，在 `notes` 中记录遮挡帧区间、袋口 ID 和球最终是否仍在台面。
- 两人交叉复核 Ground Truth；有争议的样本标记 REVIEW，不进入自动验收。

原始视频不要提交到公共仓库；可在本地 `data/raw/` 保存并通过受控存储共享。

