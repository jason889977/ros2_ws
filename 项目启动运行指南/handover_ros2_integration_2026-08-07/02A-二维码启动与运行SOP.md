# 二维码启动与运行 SOP

先按 [02-启动与运行SOP.md](02-启动与运行SOP.md) 启动 `basler_camera` 容器。二维码节点由统一 pipeline 启动，直接订阅容器内相机原始话题。

## 验证

```bash
sudo -n docker exec basler_camera bash -lc \
  'source /opt/ros/humble/setup.bash && source /opt/ros2_ws/install/setup.bash && \
   ros2 topic echo /wechat_qr_node/decoded_info --once'
```

二维码进入视野后应输出文本；启用相机内参时可通过 `/wechat_qr_node/qr_pose` 查看 `PoseStamped`。RViz 图像话题选择 `/my_camera/pylon_ros2_camera_node/image_raw`，QoS 使用 `Reliable`。停止时只需停止 `basler_camera` 容器。
