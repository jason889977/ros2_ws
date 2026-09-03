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

默认容器同时启动 Basler 和 AprilTag 节点。AprilTag 订阅驱动提供的
`/my_camera/pylon_ros2_camera_node/image_rect`；使用
`/my_camera/pylon_ros2_camera_node/camera_info`。输出统一位于
`/my_camera/{apriltag,scanner}/...` 命名空间下。

Web Dashboard 默认仅监听 `127.0.0.1:8080`。如需远程访问，应通过带认证的反向代理暴露，不能直接将节点绑定到所有网卡。

事件日志默认写入 `/var/log/vision`；两者均由 Compose 挂载到宿主机持久化目录。

统一 pipeline 中 `SCANNER_PORT` 必须为 $1$ 至 $65535$ 的整数，
`RECONNECT_INTERVAL_S` 必须为有限且不小于 $0$ 的数值。`CAMERA_STARTUP_TIMEOUT_S`
为容器启动阶段等待 `/{camera_id}/pylon_ros2_camera_node/camera_info` 的最大秒数；
超时会直接退出容器并报错（用于处理相机被占用或未连接场景）。

## 验收

```bash
docker exec basler_camera /opt/ros2_ws/deploy/basler_camera/smoke_test.sh
docker inspect --format '{{json .State.Health}}' basler_camera
```

健康检查要求相机能够提供 `camera_info`，并要求所有 `ENABLE_*` 为 `true`
的模块节点已经启动且诊断状态正常。禁用模块不参与检查；启用模块持续缺失或诊断状态
为 `ERROR`/`STALE` 会使容器状态变为 `unhealthy`。

## 前置条件

- 宿主机与 GigE 相机网络互通。
- 组织/部署环境已安装 Docker Compose v2。
- 相机目标身份为 Serial `22297681`；不要只依赖 IP。
- 真实 Pylon SDK 不在 Git 仓库中，必须由交付方按许可提供。
