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

### 统一容器新增参数（多相机 + 模块化）

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `ENABLE_APRILTAG` | `true` | 启用 AprilTag 检测链 |
| `ENABLE_QRCODE` | `true` | 启用二维码检测链 |
| `ENABLE_KEYENCE` | `true` | 启用 Keyence 扫码节点 |
| `CAMERA_ID_2` | _(空)_ | 第二台相机 ID，非空时启动双 pipeline |
| `CAMERA_CONFIG_2` | _(无默认值)_ | `CAMERA_ID_2` 非空时必填，且必须不同于 `CAMERA_CONFIG_FILE` |
| `ENABLE_APRILTAG_2` | `true` | 第二台相机 AprilTag 开关 |
| `ENABLE_QRCODE_2` | `true` | 第二台相机 QR 开关 |
| `ENABLE_KEYENCE_2` | `true` | 第二台相机 Keyence 开关 |

双相机模式下，`CAMERA_ID_2` 必须不同于 `CAMERA_ID`。统一 pipeline 的
`SCANNER_PORT` 必须为 $1$ 至 $65535$ 的整数，`RECONNECT_INTERVAL_S` 必须为有限且不小于 $0$ 的数值。
独立 QR、AprilTag、Keyence 容器会将 Compose 中对应的环境变量作为 launch 默认参数传入。

### 资源限制参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `MEM_LIMIT` | `4g` | 容器内存上限 |
| `MEM_SWAP_LIMIT` | `4g` | 容器 swap 上限 |
| `CPUS_LIMIT` | `4.0` | 容器 CPU 核数上限 |
| `LOG_MAX_SIZE` | `50m` | 单个日志文件最大大小 |
| `LOG_MAX_FILE` | `3` | 日志文件轮转数量 |

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

## 7.5 QoS 与诊断

### QoS 配置

| 话题 | 可靠性 | 深度 | 说明 |
|------|--------|------|------|
| `image_raw`（发布 + 订阅） | BEST_EFFORT | 1 | 丢弃旧帧，防止反压阻塞采集 |
| `camera_info` | RELIABLE | 10 | 内参数据量小，保证可达 |
| 检测结果 / 位姿 | RELIABLE | 10 | 关键数据，保证可达 |

### 诊断话题 `/diagnostics`

| 诊断名 | 来源 | 内容 |
|--------|------|------|
| `Scanner Connection` | Keyence 节点 | 连接状态、扫码器 IP/端口、累计扫码/错误计数 |
| `AprilTag Status` | AprilTag 节点 | 检测状态、累计检测/发布计数、当前跟踪的标签帧 |

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

### v2.0 稳定性与性能优化（2026-08-20）

**可靠性：**
- C++ 相机节点 78 处空指针保护（服务回调 + detached action 线程），防止相机重连期间段错误
- Python 节点改用 `MultiThreadedExecutor` + `CallbackGroup`，防止阻塞回调卡死定时器
- Keyence TCP 添加 `SO_KEEPALIVE` + `RLock` 线程安全保护
- AprilTag `TransformListener` 改为 `spin_thread=False`，消除双线程竞争
- 所有 respawn 节点添加 `respawn_delay=3.0`，防止崩溃风暴
- Docker entrypoint 双相机信号转发 + 退出码传播
- `calcCurrentBrightness` 整数溢出修复（`0` → `0LL`）
- `catch(...)` 块添加 `RCLCPP_ERROR` 日志（3 处）

**性能：**
- 图像发布/订阅均改为 `BEST_EFFORT QoS depth=1`，防止反压阻塞采集
- `publishCurrentParams` 从每帧调用节流至 1Hz（GigE 负载降 87.5%）
- Chunk mode GenICam 寄存器每帧 2 次读取改为 init 缓存（每帧省 0.2-2ms）
- 12-bit bit-shift 缓冲区复用为成员变量（消除每帧 ~10MB 堆分配）
- `currentROSEncoding` init 缓存（消除每帧 GenICam 字符串读取）
- QR 节点去除 Mono8→BGR 颜色转换（内存带宽降 66%）
- QR OpenCV 后端改为单码优先策略
- AprilTag `_candidate_frames` 缓存 + dirty flag（90%+ TF 回调直接返回缓存）
- 去除 `image_transport republish` 中转节点（省 1 个进程 + 1-5ms 延迟）

**多相机：**
- Launch 文件添加 `enable_apriltag`/`enable_qrcode`/`enable_keyence` 条件开关
- 所有输出话题命名空间化为 `/{camera_id}/...`
- Docker 支持 `CAMERA_ID_2` 双相机部署
- Keyence 绝对话题改为相对路径 `~/barcode`、`~/trigger`

**运维：**
- 所有 Docker 容器添加 `mem_limit`/`cpus` + 日志轮转
- Healthcheck 增加检测模块节点存活检查
- 新增故障排查手册、架构数据流图
- 17 个单元测试覆盖核心逻辑

## 9. 交付结论

本次交付中，四个模块均已按照要求整理完毕，文件结构齐全，且均遵循“只提交镜像 Tag，不提交完整镜像 .tar 文件”的原则。该交付物可用于团队部署、Docker Registry 推送和后续交接复核。
