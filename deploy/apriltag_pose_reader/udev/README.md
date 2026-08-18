# AprilTag Hardware Mount

## 设备需求

本模块不直接挂载串口设备；它依赖上游相机输出图像和内参。

- 输入图像：`/my_camera/pylon_ros2_camera_node/image_raw`
- 输入内参：`/my_camera/pylon_ros2_camera_node/camera_info`

## 设备挂载

- 无需额外 `/dev/ttyUSB*` 挂载
- 若使用 USB 相机作为上游输入，则需挂载对应 `/dev/video*`

## udev 示例

```rules
SUBSYSTEM=="video4linux", KERNEL=="video0", MODE="0666"
```

## 说明

AprilTag 模块本身不绑定独立硬件；它依赖图像源和 TF / `/detections` 流。若上游相机节点不在线，则此模块不会正常生成位姿输出。
