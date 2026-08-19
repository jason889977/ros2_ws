# AprilTag 故障排查与回滚 SOP

## 排查顺序

1. 检查 `basler_camera` 容器健康状态。
2. 容器内确认原始图像有数据。
3. 宿主机确认 `/bridge/image_raw` 和 `/bridge/camera_info` 有数据。
4. 确认 `apriltag` 订阅 `/bridge/*`。
5. 依次检查 `/detections`、`/apriltag/pose`、`/apriltag/transform` 和 TF2。

```bash
sudo -n docker inspect --format '{{.State.Status}} {{.State.Health.Status}}' basler_camera
ros2 topic hz /bridge/image_raw
ros2 topic echo /detections --once
ros2 topic echo /apriltag/pose --once
ros2 topic echo /apriltag/transform --once
```

现场验收目标为 `tag36h11`、ID `3`，并应有 `hamming=0` 和稳定的 `decision_margin`。

## 恢复 AprilTag

```bash
pkill -f 'apriltag_pose_reader|apriltag_node|apriltag_pose_reader.launch.py' || true
ros2 launch apriltag_pose_reader apriltag_pose_reader.launch.py \
  image_topic:=/bridge/image_raw \
  camera_info_topic:=/bridge/camera_info \
  lookup_parent_frame:=basler_aca2500_106611_18
```

如果 `/bridge/*` 无数据，先恢复桥接，不要在宿主机另起 Basler 驱动。若容器内出现 `0xE1018006`，检查其他 Pylon 控制端，并等待容器 respawn 完成。

## TF2

从 `/apriltag/transform` 读取 `header.frame_id` 和 `child_frame_id`，再执行:

```bash
ros2 run tf2_ros tf2_echo <header.frame_id> <child_frame_id>
```
