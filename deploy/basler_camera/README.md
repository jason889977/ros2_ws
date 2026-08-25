# Basler Camera Module Delivery

## 构建

Basler pylon SDK 具有许可和厂商运行时限制，未提交到仓库。构建前将与当前架构匹配的 SDK 文件放入 `deploy/basler_camera/pylon-sdk/`，确保其中包含 `lib/`、`include/` 和 GenTL producer 文件。

```bash
docker build -f deploy/basler_camera/Dockerfile -t basler_camera_20260819_v2.0 .
```

## 运行

```bash
cp deploy/basler_camera/.env.example deploy/basler_camera/.env
docker compose --env-file deploy/basler_camera/.env \
  -f deploy/basler_camera/docker-compose.yml up -d
```

默认容器同时启动 Basler、AprilTag 和 QR 节点。容器内算法直接订阅
`/my_camera/pylon_ros2_camera_node/image_raw` 和
`/my_camera/pylon_ros2_camera_node/camera_info`，输出统一位于
`/my_camera/{apriltag,qr,scanner}/...` 命名空间下。

QR 节点生产配置启用 WeChatQR C++ Component，直接链接系统 OpenCV 原生模块
（`libopencv_wechat_qrcode.so`），消除 Python pip 双版本混装问题并实现进程内零拷贝传输；
运行时如果 WeChatQR 模型不可用，节点会自动降级为 OpenCV `QRCodeDetector`。

双相机模式需同时设置 `CAMERA_ID_2` 与 `CAMERA_CONFIG_2`；第二路 ID 和配置文件
都必须与第一路不同。若第二路启用 AprilTag，还需设置不重复的 `CAMERA_FRAME_2`。
统一 pipeline 中 `SCANNER_PORT` 必须为 $1$ 至 $65535$ 的整数，
`RECONNECT_INTERVAL_S` 必须为有限且不小于 $0$ 的数值。`CAMERA_STARTUP_TIMEOUT_S`
为容器启动阶段等待 `/{camera_id}/pylon_ros2_camera_node/camera_info` 的最大秒数；
超时会直接退出容器并报错（用于处理相机被占用或未连接场景）。

## 验收

```bash
docker exec basler_camera /opt/ros2_ws/deploy/basler_camera/smoke_test.sh
docker inspect --format '{{json .State.Health}}' basler_camera
```

健康检查要求每路相机都能提供 `camera_info`，并要求每路所有 `ENABLE_*` 为 `true`
的模块节点已经启动且诊断状态正常。禁用模块不参与检查；启用模块持续缺失或诊断状态
为 `ERROR`/`STALE` 会使容器状态变为 `unhealthy`。

## 前置条件

- 宿主机与 GigE 相机网络互通。
- 组织/部署环境已安装 Docker Compose v2。
- 相机目标身份为 Serial `22297684`；不要只依赖 IP。
- 真实 Pylon SDK 不在 Git 仓库中，必须由交付方按许可提供。
