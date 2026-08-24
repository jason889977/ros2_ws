# Changelog

## [1.0.0] - 2026-08-18

### Added

- 增加基于 `osrf/ros:humble-ros-base-jammy` 的容器构建文件。
- 增加 Docker Compose 服务、健康检查和冒烟测试脚本。
- 增加 Basler GigE 相机身份和 ROS 2 接口交付文档。

### Fixed

- 默认相机序列号修正为在线枚举确认的 `22297684`。
- 明确 Serial Number 优先，IP 仅作为后备匹配条件。

### Parameters

- 支持 `serial_number`、`user_id`、`mac`、`ip`、`model`。
- 默认 MTU 为 `1500`，启动 User Set 为 `Default`。
