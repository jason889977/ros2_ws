# AprilTag 启动与运行 SOP

## 1. 启动统一容器

按 [02-启动与运行SOP.md](02-启动与运行SOP.md) 启动统一容器：

1. `sudo -n docker restart basler_camera`
2. 确认容器 `healthy`。
3. 确认容器内原始图像为 Mono8、`1294x970`、`binning_x/y=2`。
4. 容器执行 `industrial_vision_bringup/vision_pipeline.launch.py`。
5. 算法直接订阅容器内相机原始话题。

## 2. 单独调试 AprilTag（仅在统一 pipeline 未启用时）

```bash
cd /home/ubuntu/ros2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 launch apriltag_pose_reader apriltag_pose_reader.launch.py \
  image_topic:=/my_camera/pylon_ros2_camera_node/image_raw \
  camera_info_topic:=/my_camera/pylon_ros2_camera_node/camera_info \
  lookup_parent_frame:=basler_aca2500_106611_18
```

上述独立调试 launch 的 AprilTag 输出为 `/detections`、`/apriltag/pose` 和 `/apriltag/transform`。统一容器 pipeline 则使用带相机命名空间的 `/my_camera/detections`、`/my_camera/apriltag/pose` 和 `/my_camera/apriltag/transform`。

## 3. 验证检测和位姿

```bash
ros2 topic echo /detections --once
ros2 topic echo /apriltag/pose --once
ros2 topic echo /apriltag/transform --once
```

现场已验证目标为 `tag36h11`、ID `3`，`hamming=0`，`decision_margin` 约 `46-48`。统一 pipeline 中 Transform 的父 frame 应为 `basler_aca2500_106611_18`，默认相机的子 frame 为 `my_camera/tag36h11:3`；双相机使用各自 `camera_id/tag36h11:3`。

## 4. TF2 和 RViz

```bash
  ros2 run tf2_ros tf2_echo basler_aca2500_106611_18 my_camera/tag36h11:3
```

独立调试 launch 下，RViz 图像应选择 `/my_camera/pylon_ros2_camera_node/image_raw`，图像 QoS 设为 `Best Effort`；TF/位姿使用 `/apriltag/transform` 和 `/apriltag/pose`。统一 pipeline 下则使用 `/my_camera/apriltag/transform` 和 `/my_camera/apriltag/pose`，标签子 frame 为 `my_camera/tag36h11:3`。

## 5. 停止

```bash
pkill -f 'apriltag_pose_reader|apriltag_node|apriltag_pose_reader.launch.py' || true
sudo -n docker stop basler_camera
```

不要使用宿主机 `ros2 launch pylon_ros2_camera_wrapper` 或 `pkill pylon_ros2_camera_node` 管理容器内相机。
