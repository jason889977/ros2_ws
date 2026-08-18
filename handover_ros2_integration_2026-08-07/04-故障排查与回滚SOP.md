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
2. 先保持默认 `aca2500_106611_18.yaml`，检查错误是否持续出现
3. 确认全分辨率链路存在带宽或抓取稳定性问题后，按业务文档切换 `tuned_v3` 降载配置

## 4. 业务分流

请按当前测试链路进入对应文档:

- 二维码链路: ./04A-二维码故障排查与回滚SOP.md
- AprilTag 链路: ./04B-AprilTag故障排查与回滚SOP.md

## 5. FPS 查询与判定

查询方法:

```bash
ros2 topic hz /my_camera/pylon_ros2_camera_node/image_raw
ros2 topic echo /diagnostics
```

判定口径:

- 驱动日志中的 `Image publish FPS` 或 `/diagnostics` 的 `image_publish_rate` 是驱动发布计数；默认全分辨率配置硬件实测约 14-15 FPS。
- `ros2 topic hz` 是该订阅进程实际收到消息的速率。全分辨率 Mono8 单帧约 5 MB，当前测试约为 6.65 Hz，可能受 DDS、反序列化和订阅进程调度影响。
- 若驱动发布计数正常而 `topic hz` 较低，优先检查 DDS、主机负载和订阅端处理，不应直接认定相机抓取异常。
- 若驱动发布计数也持续偏低或伴随抓取错误，再检查曝光、网络链路、CPU 负载及配置是否正确加载。