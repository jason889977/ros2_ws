# Changelog

## [1.0.0] - 2026-08-18

### Added

- 增加 Keyence SR 扫码器 ROS 2 包装容器。
- 增加 Docker Compose、健康检查和环境变量模板。
- 增加 ROS 2 接口说明与冒烟测试脚本。

### Fixed

- 明确扫码器连接依赖 TCP 网络访问，而不是串口设备。
- 提供超时重连逻辑，提升网络异常时的稳定性。

### Parameters

- 支持 `SCANNER_IP` 和 `SCANNER_PORT` 参数覆盖。
