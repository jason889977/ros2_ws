# Changelog

## [1.0.0] - 2026-08-18

### Added

- 增加 AprilTag 检测与位姿读取模块 Dockerfile 与容器配置。
- 增加 Compose 服务、健康检查和环境变量模板。
- 增加 ROS 2 接口说明和冒烟测试脚本。

### Fixed

- 明确上游相机默认图像输入为 `/my_camera/pylon_ros2_camera_node/image_raw`。
- 统一输出 `/apriltag/pose` 与 `/apriltag/transform`，便于下游使用。

### Parameters

- 支持 `IMAGE_TOPIC`、`CAMERA_INFO_TOPIC`、`START_DETECTOR`、`TAG_FAMILY`、`TAG_ID`、`LOOKUP_PARENT_FRAME`、`LOOKUP_RATE_HZ`。
- 默认开启 `apriltag_ros` 检测节点，适合标准可视化与位姿解析流程。
