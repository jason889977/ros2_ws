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
`/my_camera/pylon_ros2_camera_node/image_raw` 和 `camera_info`。

## 验收

```bash
docker exec basler_camera /opt/ros2_ws/deploy/basler_camera/smoke_test.sh
docker inspect --format '{{json .State.Health}}' basler_camera
```

## 前置条件

- 宿主机与 GigE 相机网络互通。
- 组织/部署环境已安装 Docker Compose v2。
- 相机目标身份为 Serial `22297681`；不要只依赖 IP。
- 真实 Pylon SDK 不在 Git 仓库中，必须由交付方按许可提供。
