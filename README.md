# ROS2 Basler Camera + QR Detector Workspace

这是一个基于 ROS 2 Humble 的 Basler 相机与二维码识别工作区，包含相机驱动、二维码检测节点、运行脚本以及交接文档。

## 目录说明

- `src/pylon_ros2_camera_component`: Basler pylon 相机核心组件
- `src/pylon_ros2_camera_wrapper`: 相机 ROS2 包装与 launch/config
- `src/qrcode_detector`: 二维码检测节点与模型
- `scripts`: 部署、迁移、RViz 启动等脚本
- `docs`: 英文文档总览
- `handover_ros2_integration_2026-08-07`: 中文交接与运行 SOP

## 环境要求

- Ubuntu 22.04
- ROS 2 Humble
- Basler pylon SDK

## 快速启动

每个终端先执行：

```bash
cd /home/ubuntu/ros2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
```

### 1. 启动相机

```bash
ros2 launch pylon_ros2_camera_wrapper pylon_ros2_camera.launch.py \
  config_file:=/home/ubuntu/ros2_ws/src/pylon_ros2_camera_wrapper/config/aca2500_106611_18.tuned_v3.yaml
```

### 2. 启动二维码节点

```bash
ros2 launch qrcode_detector qrcode_detector.launch.py
```

### 3. 验证链路

```bash
ros2 node list
ros2 topic info -v /my_camera/pylon_ros2_camera_node/image_raw
ros2 topic echo /wechat_qr_node/decoded_info --once
```

### 4. 打开 RViz 查看图像

```bash
/home/ubuntu/ros2_ws/scripts/open_camera_rviz.sh
```

## 文档入口

- 英文文档总览：`docs/README.md`
- 中文启动 SOP：`handover_ros2_integration_2026-08-07/02-启动与运行SOP.md`
- Basler 安装说明：`BASLER_INSTALL_GUIDE.md`

## GitHub 仓库

当前工作区已同步到两个远程仓库：

- 个人仓库：`origin` -> https://github.com/jason889977/ros2_ws
- 组织仓库：`org` -> https://github.com/industrialnext-ai-dd/ros2_ws

查看远程：

```bash
git remote -v
```

常规提交流程：

```bash
git add .
git commit -m "your message"
git push
```

同时同步个人仓库与组织仓库：

```bash
git sync-all
```

如果只想单独推送组织仓库：

```bash
git push org main
```

## 备注

- `build/`、`install/`、`log/` 已通过 `.gitignore` 忽略，不会提交到 GitHub。
- `main` 当前默认跟踪个人仓库 `origin/main`。