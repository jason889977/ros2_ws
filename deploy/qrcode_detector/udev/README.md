# QR Detector Hardware Mount

## 设备需求

本模块不直接依赖串口设备或视频设备节点；它只消费上游相机或图像流。

- 输入设备：图像源，通常来自 Basler GigE 相机
- 典型话题：`/my_camera/pylon_ros2_camera_node/image_raw`

## 设备挂载

- 默认无需额外 `/dev/ttyUSB*` 或 `/dev/video*` 映射
- 若图像输入来自 USB 摄像头，则需额外挂载对应 `/dev/video*`

## udev 示例

```rules
# 示例：USB Camera
SUBSYSTEM=="video4linux", KERNEL=="video0", MODE="0666"
```

## 说明

本模块本身不绑定硬件串口；如果部署时从其他图像源接入，则仅需保证该图像话题可用即可。
