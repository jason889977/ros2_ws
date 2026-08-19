# 故障排查与回滚 SOP（公共入口）

## 1. 目的

二维码与 AprilTag 排障文档已拆分，避免在同一流程中混排两类业务问题。

- 二维码专用排障: ./04A-二维码故障排查与回滚SOP.md
- AprilTag 专用排障: ./04B-AprilTag故障排查与回滚SOP.md

## 2. 公共排查总原则

按顺序排查:
1. 检查 `basler_camera` 容器状态和健康状态
2. 在容器内检查原始 image_raw 是否有实际数据
3. 检查宿主机 `/bridge/image_raw` 是否有实际数据
4. 检查业务节点是否订阅 `/bridge/*`
5. 最后检查相机锁、GigE 和配置

## 3. 公共关键错误码守门

快速扫描命令:

```bash
latest=$(ls -1t /home/ubuntu/.ros/log/pylon_ros2_camera_wrapper_*.log | head -n 1)
grep -E "3774873620|incompletely grabbed|Grab was not successful" -i "$latest" || true
```

处理顺序:
1. 检查网线/交换机/NIC
2. 确认实际 profile 使用 `binning_x/y=2` 且输出为 `1294x970`
3. 不要启动第二个宿主机驱动或随意切换 `tuned_v3`

## 4. 业务分流

请按当前测试链路进入对应文档:

- 二维码链路: ./04A-二维码故障排查与回滚SOP.md
- AprilTag 链路: ./04B-AprilTag故障排查与回滚SOP.md

## 5. FPS 查询与判定

查询方法:

```bash
ros2 topic hz /bridge/image_raw
ros2 topic echo /diagnostics
```

判定口径:

- 驱动日志中的 `Image publish FPS` 或 `/diagnostics` 的 `image_publish_rate` 是容器内驱动发布计数。
- `ros2 topic hz /bridge/image_raw` 是桥接后宿主机实际收到的速率，受 JPEG 桥和宿主机负载影响。
- 若驱动发布计数正常而 `topic hz` 较低，优先检查 DDS、主机负载和订阅端处理，不应直接认定相机抓取异常。
- 若驱动发布计数也持续偏低或伴随抓取错误，再检查曝光、网络链路、CPU 负载及配置是否正确加载。