# 二维码启动与运行 SOP

## 1. 适用范围

本 SOP 仅用于“相机 + 二维码识别”链路。
不包含 AprilTag 启动、TF2、6D 位姿与 RViz2 标签位姿观测步骤。

## 2. 统一前置

在每个终端先执行:

```bash
cd /home/ubuntu/ros2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
```

## 3. 标准启动

### 终端1: 启动相机

```bash
cd /home/ubuntu/ros2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 launch pylon_ros2_camera_wrapper pylon_ros2_camera.launch.py \
  config_file:=/home/ubuntu/ros2_ws/src/pylon_ros2_camera_wrapper/config/aca2500_106611_18.yaml \
  startup_user_set:=Default
```

### 终端2: 启动二维码节点

```bash
cd /home/ubuntu/ros2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 launch qrcode_detector qrcode_detector.launch.py
```

### 终端3: 验证链路

```bash
cd /home/ubuntu/ros2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 node list
ros2 topic info -v /my_camera/pylon_ros2_camera_node/image_raw
ros2 topic echo /wechat_qr_node/decoded_info
```

## 4. 一键脚本

```bash
# 默认复用已有相机节点，避免设备占用冲突
/home/ubuntu/ros2_ws/scripts/deploy_and_run_camera_qr.sh

# 若需要先自动停掉旧相机再重启
CAMERA_MODE=restart /home/ubuntu/ros2_ws/scripts/deploy_and_run_camera_qr.sh
```

## 5. 可选: RViz 图像可视化

```bash
cd /home/ubuntu/ros2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
/home/ubuntu/ros2_ws/scripts/open_camera_rviz.sh
```

或手动启动:

```bash
rviz2
```

在 RViz 中执行:

- Add -> Image
- Topic 选择 /my_camera/pylon_ros2_camera_node/image_raw
- 若不出图，将 Fixed Frame 设置为当前存在坐标系（如 base_link 或相机 frame）

## 6. 快速判定规则

- 相机正常: /my_camera/pylon_ros2_camera_node 存在
- 图像链路正常: /my_camera/pylon_ros2_camera_node/image_raw 的 Publisher count 至少为 1
- 订阅正常: image_raw 的 Subscription count 至少为 1 且包含 wechat_qr_node
- 解码正常: /wechat_qr_node/decoded_info 有持续输出

## 7. 停止流程

```bash
pkill -f "qrcode_node|qrcode_detector.launch.py" || true
pkill -f "pylon_ros2_camera_node|pylon_ros2_camera.launch.py" || true
```

按先停二维码、再停相机执行。
