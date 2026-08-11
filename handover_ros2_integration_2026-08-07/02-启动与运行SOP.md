# 启动与运行 SOP

## 1. 统一前置

在每个终端先执行:

```bash
cd /home/ubuntu/ros2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
```

## 2. 三终端标准启动

### 终端1: 启动相机

```bash
cd /home/ubuntu/ros2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 launch pylon_ros2_camera_wrapper pylon_ros2_camera.launch.py \
  config_file:=/home/ubuntu/ros2_ws/src/pylon_ros2_camera_wrapper/config/aca2500_106611_18.tuned_v3.yaml
```

### 终端2: 启动二维码节点

```bash
cd /home/ubuntu/ros2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 launch qrcode_detector qrcode_detector.launch.py
```

### 终端3: 观测验证

```bash
cd /home/ubuntu/ros2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 node list
ros2 topic info -v /my_camera/pylon_ros2_camera_node/image_raw
ros2 topic echo /wechat_qr_node/decoded_info
```

### 可选: RViz 图像可视化

`ros2 topic echo /my_camera/pylon_ros2_camera_node/image_raw` 仅用于在终端查看消息字段，不会在 RViz 中显示图像。

```bash
cd /home/ubuntu/ros2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
rviz2
```

在 RViz 中执行:

- Add -> Image
- Topic 选择 `/my_camera/pylon_ros2_camera_node/image_raw`
- 若不出图，先将 Fixed Frame 设置为当前存在的坐标系（如 `base_link` 或相机 frame）

可用以下命令确认图像话题有持续发布:

```bash
ros2 topic hz /my_camera/pylon_ros2_camera_node/image_raw
```

自动配置（推荐，一条命令打开 RViz 并加载图像显示配置）:

```bash
/home/ubuntu/ros2_ws/scripts/open_camera_rviz.sh
```

## 3. 快速判定规则

- 相机正常: /my_camera/pylon_ros2_camera_node 存在
- 图像链路正常: /my_camera/pylon_ros2_camera_node/image_raw 的 Publisher count 至少为 1
- 订阅正常: image_raw 的 Subscription count 至少为 1 且包含 wechat_qr_node
- 解码正常: /wechat_qr_node/decoded_info 有持续输出

## 4. 日常巡检命令

```bash
ros2 node list
ros2 topic info -v /my_camera/pylon_ros2_camera_node/image_raw
ros2 topic hz /my_camera/pylon_ros2_camera_node/image_raw
ros2 topic echo /wechat_qr_node/decoded_info --once
```

## 5. 停止流程

```bash
pkill -f "qrcode_node|qrcode_detector.launch.py" || true
pkill -f "pylon_ros2_camera_node|pylon_ros2_camera.launch.py" || true
```

按先停二维码、再停相机执行。
