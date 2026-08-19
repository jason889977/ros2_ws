# 交接签收 Checklist

## 1. 基本信息

- 交接日期:
- 交接人:
- 接收人:
- 环境:
- 交接包版本: 2026-08-07

## 2. 文件签收

- [ ] 已收到并确认 00-交接总览.md
- [ ] 已收到并确认 01-文件与配置交接清单.md
- [ ] 已收到并确认 02-启动与运行SOP.md
- [ ] 已收到并确认 02A-二维码启动与运行SOP.md
- [ ] 已收到并确认 02B-AprilTag启动与运行SOP.md
- [ ] 已收到并确认 03-测试方法与验收标准.md
- [ ] 已收到并确认 03A-二维码测试方法与验收标准.md
- [ ] 已收到并确认 03B-AprilTag测试方法与验收标准.md
- [ ] 已收到并确认 04-故障排查与回滚SOP.md
- [ ] 已收到并确认 04A-二维码故障排查与回滚SOP.md
- [ ] 已收到并确认 04B-AprilTag故障排查与回滚SOP.md
- [ ] 已收到并确认 05-交接签收Checklist.md
- [ ] 已收到并确认 06-组件与依赖安装详单.md

## 3. 启动签收

- [ ] 已按 SOP 启动或重启 `basler_camera` 容器
- [ ] 二维码链路: 已按 02A 启动并完成验证
- [ ] AprilTag 链路: 已按 02B 启动并完成验证

## 4. 测试签收

- [ ] 已完成图谱连通测试
- [ ] 二维码链路: 已按 03A 完成验收
- [ ] AprilTag 链路: 已按 03B 完成验收
- [ ] 已确认图像规格为 Mono8、1294x970、binning 2x2
- [ ] 已确认 `/bridge/image_raw` 能实际收到消息
- [ ] 已知 `ros2 topic hz` 是订阅端到达率，不要求等于驱动发布计数
- [ ] 已完成关键错误码守门检查
- [ ] 已形成测试结论与记录

## 5. 风险与回滚认知签收

- [ ] 已知日常 Basler 由 `basler_camera` 容器管理
- [ ] 已知宿主机 ROS 端点发现不等于容器图像数据可达
- [ ] 已知 3774873620 为阻断级风险
- [ ] 已知回滚后必须重做关键测试
- [ ] 二维码链路: 已阅读 04A 并理解回滚流程
- [ ] AprilTag 链路: 已阅读 04B 并理解回滚流程

## 6. 证据记录

建议附上:
- ros2 node list 输出截图或日志
- ros2 topic info -v image_raw 输出
- 二维码: ros2 topic echo /wechat_qr_node/decoded_info 输出
- AprilTag: /detections、/apriltag/pose、/apriltag/transform 输出
- 驱动 `Image publish FPS` 日志或 `/diagnostics` 输出
- ros2 topic hz 订阅端到达率输出
- 错误码扫描输出

## 7. 最终结论

- 交接状态: 完成/未完成
- 接收结论: 可接手/需补充
- 补充项:
- 双方签字:
