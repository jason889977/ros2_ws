# 二维码启动与运行 SOP

先按 [02-启动与运行SOP.md](02-启动与运行SOP.md) 启动 `basler_camera` 容器并建立 TCP 图像桥。二维码节点订阅桥接话题，不直接订阅容器原始话题。

## 启动二维码

```bash
cd /home/ubuntu/ros2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 launch qrcode_detector qrcode_detector.launch.py \
  image_topic:=/bridge/image_raw \
  camera_info_topic:=/bridge/camera_info \
  prefer_wechat_qr:=true \
  use_camera_info:=true
```

## 验证

```bash
ros2 topic info -v /bridge/image_raw
ros2 topic echo /wechat_qr_node/decoded_info --once
ros2 topic echo /wechat_qr_node/qr_pose --once
```

二维码进入视野后应输出文本；启用相机内参时应输出 `PoseStamped`。RViz 图像话题选择 `/bridge/image_raw`，QoS 使用 `Reliable`。停止时先停二维码节点，再停图像桥；Basler 容器只用 Docker 管理。
