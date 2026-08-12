# 故障排查与回滚 SOP（公共入口）

## 1. 目的

二维码与 AprilTag 排障文档已拆分，避免在同一流程中混排两类业务问题。

- 二维码专用排障: ./04A-二维码故障排查与回滚SOP.md
- AprilTag 专用排障: ./04B-AprilTag故障排查与回滚SOP.md

## 2. 公共排查总原则

按顺序排查:
1. 先看 ROS 图谱
2. 再看业务关键话题
3. 再看关键错误码
4. 最后看参数与配置

## 3. 公共关键错误码守门

快速扫描命令:

```bash
latest=$(ls -1t /home/ubuntu/.ros/log/pylon_ros2_camera_wrapper_*.log | head -n 1)
grep -E "3774873620|incompletely grabbed|Grab was not successful" -i "$latest" || true
```

处理顺序:
1. 检查网线/交换机/NIC
2. 保持 v3 配置，不做激进调参
3. 若反复出现，按业务文档执行回滚

## 4. 业务分流

请按当前测试链路进入对应文档:

- 二维码链路: ./04A-二维码故障排查与回滚SOP.md
- AprilTag 链路: ./04B-AprilTag故障排查与回滚SOP.md
