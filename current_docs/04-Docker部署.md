# Docker 部署

## 1. 部署模型

生产 Compose 使用单个 `basler_camera` 容器承载一条视觉流水线。

关键属性：

- `network_mode: host`，用于相机网络和 ROS 2 DDS；
- `restart: unless-stopped`；
- 默认资源上限为 4 GiB 内存、4 GiB swap、4 CPU；
- 相机配置只读挂载；
- 图像归档、事件日志和标定数据写入宿主机持久化目录；
- 容器健康检查执行 ROS 2 业务探针，不只检查进程。

## 2. 准备 pylon SDK

Docker 构建上下文必须包含一个合法的 Basler pylon SDK 包：

```text
deploy/basler_camera/pylon-sdk/
```

支持：

- 直接放置 `.deb` 文件；
- 放置一个包含 `.deb` 的 `.tar.gz`；
- 放置一个 Basler `*_setup.tar.gz`。

构建逻辑不允许目录中存在多个候选 tar 包，以避免选择歧义。SDK 受 Basler 许可证约束，不应提交到公共源码仓库。

## 3. 构建镜像

必须从工作区根目录构建，因为 Dockerfile 会复制 `src/`、`scripts/` 和部署配置：

```bash
cd /home/ubuntu/ros2_ws
DOCKER_BUILDKIT=1 docker build \
  -f deploy/basler_camera/Dockerfile \
  -t basler_camera_20260819_v2.0 .
```

也可使用 buildx：

```bash
docker buildx build --builder default --progress=plain --load \
  -f deploy/basler_camera/Dockerfile \
  -t basler_camera_20260819_v2.0 .
```

镜像内工作区位于 `/opt/ros2_ws`，默认命令为：

```text
ros2 launch industrial_vision_bringup vision_pipeline.launch.py
```

## 4. 准备环境变量

```bash
cp deploy/basler_camera/.env.example deploy/basler_camera/.env
```

至少核对：

- `BASLER_IMAGE=basler_camera_20260819_v2.0`；
- `CAMERA_ID` 与 `CAMERA_FRAME`；
- `CAMERA_CONFIG_FILE`；
- `CAMERA_MTU_SIZE`；
- `SCANNER_IP`、`SCANNER_PORT`；
- `ENABLE_APRILTAG`、`ENABLE_KEYENCE`；
- `ROS_DOMAIN_ID` 与 `RMW_IMPLEMENTATION`。

`.env` 可能包含现场网络信息，不应无检查地提交。

## 5. 启动和停止

```bash
docker compose --env-file deploy/basler_camera/.env \
  -f deploy/basler_camera/docker-compose.yml up -d
```

查看状态：

```bash
docker compose --env-file deploy/basler_camera/.env \
  -f deploy/basler_camera/docker-compose.yml ps
docker logs --tail 200 basler_camera
```

停止：

```bash
docker compose --env-file deploy/basler_camera/.env \
  -f deploy/basler_camera/docker-compose.yml down
```

entrypoint 会等待 `camera_info` 首帧。默认最多等待 120 秒；配置无效或启动超时分别导致非零退出，随后由 Compose 重启策略处理。

## 6. 持久化目录

Compose 默认挂载：

| 宿主机路径 | 容器路径 | 用途 |
| ------------ | ---------- | ------ |
| `deploy/basler_camera/config` | `/opt/ros2_ws/deploy/basler_camera/config` | 相机/标定配置，只读 |
| `deploy/basler_camera/data/calibration` | `/var/lib/vision/calibration` | 标定页面的采集图、结果 YAML、去畸变预览和历史记录 |
| `deploy/basler_camera/data/events` | `/var/log/vision` | JSON Lines 事件日志 |
| `deploy/basler_camera/data/archive` | `/var/lib/vision/archive` | Dashboard 快照归档 |

启动前确保 Docker 进程对四个数据目录有写权限。`CALIBRATION_DIR` 默认为 `/var/lib/vision/calibration`，可在 `.env` 中覆盖。

## 7. 健康检查

Compose 每 15 秒执行：

```text
/opt/ros2_ws/deploy/basler_camera/healthcheck.sh
```

探针检查流水线：

1. `camera_info` 话题类型正确且能收到消息；
2. 所有已启用算法/扫码模块的节点存在；
3. `vision/status` 能收到消息；
4. `overall_level` 不是 ERROR 或 STALE。

手动执行：

```bash
docker exec basler_camera \
  /opt/ros2_ws/deploy/basler_camera/healthcheck.sh
```

查看 Docker 健康状态：

```bash
docker inspect --format \
  '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}' \
  basler_camera
```

## 8. 功能冒烟

```bash
docker exec basler_camera \
  /opt/ros2_ws/deploy/basler_camera/smoke_test.sh
```

该脚本验证相机节点存在，并实际接收 `camera_info` 和 `image_raw`。

## 9. 开发 Compose 覆盖

开发覆盖文件将宿主机源码只读挂载到容器，并打开归档：

```bash
docker compose --env-file deploy/basler_camera/.env \
  -f deploy/basler_camera/docker-compose.yml \
  -f deploy/basler_camera/docker-compose.dev.yml up
```

注意：镜像在构建阶段已经执行 `colcon build`。仅挂载修改后的源码不会自动重新编译 C++ 或重新安装 Python 包；需要在容器内重新构建，或重新构建镜像。

## 10. Dashboard 访问边界

Dashboard 的 uvicorn 当前绑定 `127.0.0.1`。在 host 网络模式下可从工控机本机访问：

```text
http://127.0.0.1:8080
```

它不会直接监听所有网卡。需要远程访问时应通过受控反向代理、SSH 隧道或明确修改监听策略，并评估相机控制 API 的访问权限。
