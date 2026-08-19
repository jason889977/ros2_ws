# 二维码故障排查与回滚 SOP

## 排查顺序

1. 检查 `basler_camera` 容器是否 `healthy`。
2. 在容器内确认 `/my_camera/pylon_ros2_camera_node/image_raw` 有实际消息。
3. 在宿主机确认 `/bridge/image_raw` 有实际消息。
4. 确认二维码节点订阅 `/bridge/image_raw` 和 `/bridge/camera_info`。
5. 最后检查模型、曝光和识别结果。

```bash
sudo -n docker inspect --format '{{.State.Status}} {{.State.Health.Status}}' basler_camera
ros2 topic hz /bridge/image_raw
ros2 topic info -v /bridge/image_raw
ros2 topic echo /wechat_qr_node/decoded_info --once
```

如果容器内有图像而桥接话题无数据，重启桥的 host 端和容器转发端；不要重启第二个 Basler 驱动。若容器内也无图像，检查容器日志、GigE 网络、相机锁和实际挂载配置。

## 恢复二维码节点

```bash
pkill -f 'qrcode_node|qrcode_detector.launch.py' || true
ros2 launch qrcode_detector qrcode_detector.launch.py \
  image_topic:=/bridge/image_raw \
  camera_info_topic:=/bridge/camera_info \
  prefer_wechat_qr:=true
```

当前日常配置为 `2x2 binning`；不再使用宿主机相机 launch 或 `tuned_v3` 作为常规回滚路径。
