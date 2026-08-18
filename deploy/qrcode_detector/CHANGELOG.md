# Changelog

## [1.0.0] - 2026-08-18

### Added

- 增加 QR 码检测模块 Dockerfile 与容器构建脚本。
- 增加 Compose 配置、健康检查和环境变量模板。
- 增加 ROS 2 接口说明与冒烟测试脚本。

### Fixed

- 明确默认输入为相机图像话题 `/my_camera/pylon_ros2_camera_node/image_raw`。
- 兼容 OpenCV 内置 QR 检测器与 WeChatQR 深度学习模型两种模式。

### Parameters

- 新增 `IMAGE_TOPIC`、`MODEL_DIR`、`PREFER_WECHAT_QR`、`QUEUE_SIZE` 参数。
- 默认开启稳定回退策略，避免模型缺失导致节点异常退出。
