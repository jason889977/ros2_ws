# 工业视觉系统当前文档

本目录描述当前工作区中的实际实现。内容以 ROS 2 包清单、launch 文件、节点源码、接口定义、Docker 配置和 CI 配置为依据。

## 文档导航

| 文档 | 内容 |
| ------ | ------ |
| [系统架构](01-系统架构.md) | 包职责、运行拓扑、数据流、单相机模型 |
| [开发与测试](02-开发与测试.md) | 本地环境、构建、pytest、CTest、代码检查 |
| [运行与配置](03-运行与配置.md) | 统一 launch、参数、话题命名、功能开关 |
| [Docker 部署](04-Docker部署.md) | SDK 准备、镜像构建、Compose、持久化和健康检查 |
| [接口参考](05-接口参考.md) | ROS 话题、服务、Action、Dashboard HTTP/WebSocket API |
| [标定与 TF](06-标定与TF.md) | 相机内参、手眼标定、静态 TF 加载 |
| [运维与排障](07-运维与排障.md) | 验收检查、日志、常见故障定位 |
| [AprilTag 功能测试](08-AprilTag功能测试.md) | 真实相机的逐步测试指令、预期结果和判定标准 |
| [内参标定功能测试](09-内参标定功能测试.md) | AprilGrid 采集、Action 求解、YAML 检查、加载与闭环复验 |
| [手眼标定功能测试](10-手眼标定功能测试.md) | xArm eye-in-hand Action 采集、求解、YAML 加载与 TF 闭环复验 |

## 当前基线

- 操作系统与 ROS：Ubuntu 22.04、ROS 2 Humble。
- 工作区：12 个 ROS 2 包，其中 4 个 `ament_cmake` 包、8 个 `ament_python` 包。
- 生产入口：`industrial_vision_bringup/vision_pipeline.launch.py`。
- 容器入口：`deploy/basler_camera/entrypoint.sh`。
- 相机与 AprilTag 检测可在同一个多线程组件容器中运行，并启用 ROS 2 intra-process 通信。
- 相机使用独立 `/{camera_id}` 命名空间。
- Dashboard 默认仅监听容器或主机的 `127.0.0.1:8080`。

## 最短上手路径

### 本地真实硬件

需要先安装 Basler pylon SDK，并确保相机配置文件指向实际设备：

```bash
cd /home/ubuntu/ros2_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-up-to industrial_vision_bringup
source install/setup.bash
ros2 launch industrial_vision_bringup vision_pipeline.launch.py \
  camera_id:=my_camera \
  camera_config:="$PWD/deploy/basler_camera/config/aca2500_106611_18.yaml"
```

### Docker 生产部署

把一个有效的 Basler SDK 安装包放入 `deploy/basler_camera/pylon-sdk/`，然后执行：

```bash
cd /home/ubuntu/ros2_ws
DOCKER_BUILDKIT=1 docker build \
  -f deploy/basler_camera/Dockerfile \
  -t basler_camera_20260819_v2.0 .

cp deploy/basler_camera/.env.example deploy/basler_camera/.env
# 编辑 .env，使相机、扫码器和 TF 参数匹配现场设备。
docker compose --env-file deploy/basler_camera/.env \
  -f deploy/basler_camera/docker-compose.yml up -d
```

## 使用约定

1. 所有命令默认从工作区根目录 `/home/ubuntu/ros2_ws` 执行。
2. 每个新终端先执行 `source /opt/ros/humble/setup.bash`；构建后再执行 `source install/setup.bash`。
3. `camera_id` 必须是合法 ROS 标识符。
4. 容器使用 host 网络；宿主机与容器的 `ROS_DOMAIN_ID`、RMW 实现及 DDS 网络策略必须兼容。
5. `deploy/basler_camera/config/` 是容器运行时只读挂载的现场配置来源。
