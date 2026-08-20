# Module Delivery Summary

本文档汇总本次交付的 ROS 2 模块 Docker 镜像信息、运行入口、健康检查方式、接口摘要和更新日志。所有模块均遵循本次交付标准：

- 不提交完整镜像 .tar 文件
- 仅提交镜像 Tag / Registry 引用
- 提供 Dockerfile、Compose 配置、环境变量模板、健康检查、ROS 2 接口说明、smoke test 和更新日志

## 1. 模块列表

| 模块 | 镜像 Tag | 目录 | 备注 |
| --- | --- | --- | --- |
| Basler Camera（统一容器） | `basler_camera_20260819_v2.0` | `deploy/basler_camera` | **生产主路径**，包含全部 5 个节点 |
| QR Detector（独立容器） | `qrcode_detector_20260818_v1.0` | `deploy/qrcode_detector` | 遗留独立部署，非生产主路径 |
| AprilTag Pose Reader（独立容器） | `apriltag_pose_reader_20260818_v1.0` | `deploy/apriltag_pose_reader` | 遗留独立部署，非生产主路径 |
| Keyence SR Wrapper（独立容器） | `keyence_sr_wrapper_20260818_v1.0` | `deploy/keyence_sr_wrapper` | 遗留独立部署，非生产主路径 |

## 2. Docker 构建与运行

### Basler Camera（统一容器，生产主路径）

```bash
docker build -f deploy/basler_camera/Dockerfile -t basler_camera_20260819_v2.0 .
cp deploy/basler_camera/.env.example deploy/basler_camera/.env
docker compose --env-file deploy/basler_camera/.env \
  -f deploy/basler_camera/docker-compose.yml up -d
```

### QR Detector

```bash
docker build -f deploy/qrcode_detector/Dockerfile -t qrcode_detector_20260818_v1.0 .
cp deploy/qrcode_detector/.env.example deploy/qrcode_detector/.env
docker compose --env-file deploy/qrcode_detector/.env \
  -f deploy/qrcode_detector/docker-compose.yml up -d
```

### AprilTag Pose Reader

```bash
docker build -f deploy/apriltag_pose_reader/Dockerfile -t apriltag_pose_reader_20260818_v1.0 .
cp deploy/apriltag_pose_reader/.env.example deploy/apriltag_pose_reader/.env
docker compose --env-file deploy/apriltag_pose_reader/.env \
  -f deploy/apriltag_pose_reader/docker-compose.yml up -d
```

### Keyence SR Wrapper

```bash
docker build -f deploy/keyence_sr_wrapper/Dockerfile -t keyence_sr_wrapper_20260818_v1.0 .
cp deploy/keyence_sr_wrapper/.env.example deploy/keyence_sr_wrapper/.env
docker compose --env-file deploy/keyence_sr_wrapper/.env \
  -f deploy/keyence_sr_wrapper/docker-compose.yml up -d
```

## 3. 健康检查命令

每个模块都附带 `healthcheck.sh`，用于在容器启动后检查节点是否存活与就绪。

### Basler

```bash
docker exec basler_camera /opt/ros2_ws/deploy/basler_camera/healthcheck.sh
```

### QR

```bash
docker exec qrcode_detector /opt/ros2_ws/deploy/qrcode_detector/healthcheck.sh
```

### AprilTag

```bash
docker exec apriltag_pose_reader /opt/ros2_ws/deploy/apriltag_pose_reader/healthcheck.sh
```

### Keyence

```bash
docker exec keyence_sr_wrapper /opt/ros2_ws/deploy/keyence_sr_wrapper/healthcheck.sh
```

## 4. 冒烟测试

每个模块都提供 `smoke_test.sh`，用于快速验证功能是否正常。

### Basler

```bash
docker exec basler_camera /opt/ros2_ws/deploy/basler_camera/smoke_test.sh
```

### QR

```bash
docker exec qrcode_detector /opt/ros2_ws/deploy/qrcode_detector/smoke_test.sh
```

### AprilTag

```bash
docker exec apriltag_pose_reader /opt/ros2_ws/deploy/apriltag_pose_reader/smoke_test.sh
```

### Keyence

```bash
docker exec keyence_sr_wrapper /opt/ros2_ws/deploy/keyence_sr_wrapper/smoke_test.sh
```

## 5. 环境变量模板

所有模块均提供 `.env.example`，可按需复制为 `.env` 后调整参数。

- Basler: `deploy/basler_camera/.env.example`
- QR: `deploy/qrcode_detector/.env.example`
- AprilTag: `deploy/apriltag_pose_reader/.env.example`
- Keyence: `deploy/keyence_sr_wrapper/.env.example`

关键参数包括：

- `ROS_DOMAIN_ID`
- `RMW_IMPLEMENTATION`
- 图像/相机输入话题
- 扫码器 IP / 端口
- 分辨率、MTU、采样率等模块相关参数

## 6. 硬件挂载要求

### Basler

- 依赖 GigE 相机网络，不依赖 `/dev/ttyUSB*` / `/dev/video*`
- 通过 `network_mode: host` 访问网络相机
- 由 `udev/README.md` 说明设备要求

### QR

- 默认消费上游相机图像，不要求额外串口设备
- 若使用 USB 相机，仅需要对应 `/dev/video*` 挂载

### AprilTag

- 依赖上游相机图像与 `camera_info`
- 无额外串口设备需求

### Keyence

- 通过 TCP/IP 连接到扫码器，无需串口挂载
- 默认 IP：`172.31.0.91`
- 默认端口：`9004`

## 7. ROS 2 接口摘要

### Basler

发布（`{camera_id}` 默认 `my_camera`）：

- `/{camera_id}/pylon_ros2_camera_node/image_raw` `sensor_msgs/msg/Image`
- `/{camera_id}/pylon_ros2_camera_node/camera_info` `sensor_msgs/msg/CameraInfo`
- `/{camera_id}/pylon_ros2_camera_node/status` `pylon_ros2_camera_interfaces/msg/ComponentStatus`

服务：

- `~/set_exposure`
- `~/set_gain`
- `~/set_gamma`
- `~/set_roi`
- `~/set_white_balance`

### QR

订阅：

- `/{camera_id}/pylon_ros2_camera_node/image_raw`

发布：

- `/{camera_id}/qr/decoded_info` `std_msgs/msg/String`

### AprilTag

订阅：

- `/{camera_id}/detections`
- `/tf`
- `/{camera_id}/pylon_ros2_camera_node/image_raw`
- `/{camera_id}/pylon_ros2_camera_node/camera_info`

发布：

- `/{camera_id}/apriltag/pose` `geometry_msgs/msg/PoseStamped`
- `/{camera_id}/apriltag/transform` `geometry_msgs/msg/TransformStamped`

### Keyence

发布：

- `/{camera_id}/scanner/barcode` `std_msgs/msg/String`

服务：

- `/{camera_id}/scanner/trigger` `std_srvs/srv/Trigger`

## 8. 更新日志摘要

### Basler

- 增加 Docker Compose 服务、健康检查和冒烟测试脚本
- 修正默认相机序列号和启动参数
- 完善 ROS 2 接口交付文档

### QR

- 增加 QR 检测模块 Dockerfile 与部署配置
- 支持 OpenCV fallback 与可选 WeChatQR 模型
- 完善环境变量和发布话题说明

### AprilTag

- 增加 AprilTag 检测与位姿读取容器配置
- 统一 `/apriltag/pose` 与 `/apriltag/transform` 输出方式
- 完成健康检查和 smoke test

### Keyence

- 增加 TCP/IP 扫码器包装层
- 增加超时重连逻辑
- 补齐 ROS 2 接口说明与 smoke test

## 9. 交付结论

本次交付中，四个模块均已按照要求整理完毕，文件结构齐全，且均遵循“只提交镜像 Tag，不提交完整镜像 .tar 文件”的原则。该交付物可用于团队部署、Docker Registry 推送和后续交接复核。
