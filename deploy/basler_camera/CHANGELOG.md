# Changelog

## [1.1.0] - 2026-08-26

### Fixed

- **健康检查永远失败 (Critical)**：`healthcheck.sh` 中 `check_pipeline_status()` 的 `grep ... && return 1` 后缺少显式 `return 0`，导致函数任何输入都返回退出码 1，Docker 永远标记 unhealthy 并反复重启容器。
- **Web Dashboard 执行器污染 (Critical)**：`/api/trigger_scan`、`/api/set_exposure`、`/api/set_gain` 三个端点调用 `rclpy.spin_until_future_complete(node, future)` 未传 executor，导致同一 node 被 MultiThreadedExecutor 和临时 SingleThreadedExecutor 并发 spin，产生未定义行为。已改为 `while not future.done()` 轮询。
- **Web Dashboard MJPEG 线程池耗尽 (Critical)**：`/api/camera/stream` 的同步生成器在相机未推流时永不 yield，Starlette 线程池被永久占满。已改为 `async def generate()` + `await asyncio.sleep()`。
- **Pylon runtime 引用计数泄漏 (Critical)**：`PylonROS2Camera::create()` identity 匹配路径中，相机类型为 UNKNOWN 时 `createFromDevice` 返回 nullptr 后未调用 `PylonTerminate()`，反复重连后驱动 .so 无法卸载。
- **相机节点 Action 回调数据竞争 (Critical)**：`executeGrabRawImagesAction`、`executeGrabRectImagesAction`、`executeGrabBlazeDataAction` 在独立线程运行但不持有 `grab_mutex_`，null 检查与后续 `pylon_camera_->` 访问之间存在竞态窗口，可导致 SIGSEGV。已加 `lock_guard<recursive_mutex>` 保护。
- **`setBinningCallback` 未初始化变量 (Critical)**：`reached_binning_x/y` 声明时未初始化，`setBinningX/Y` 失败时不赋值，后续 `static_cast` 读取栈垃圾值（未定义行为）。已初始化为 0。
- **39 个服务回调缺少空指针检查**：`enablePTP*`、`setChunkExposureTime`、`setUserOutput`、`setAutoflash` 等 39 个回调直接解引用 `pylon_camera_->` 无空检查。已由 `createCameraService` 的 `grab_mutex_` 隐式保护，现补充显式空检查作为纵深防御。
- **`setBrightnessCallback` 锁间隙**：`setBrightness()` 释放锁后，`enableContinuousAutoExposure/Gain` 和 `currentExposure/Gain` 在无锁状态下访问 `pylon_camera_`。已加 `lock_guard` 保护。
- **`setImageEncodingCallback` 锁间隙**：`grabbingStarting()` 返回后对 `currentROSEncoding()`/`currentBaslerEncoding()`/`bit_shift_active_` 的访问无锁无空检查。已加空检查 + `lock_guard`。
- **`spin()` 主循环空指针**：`isCamRemoved()` 调用前未检查 `pylon_camera_` 是否为 null，重连失败后可 SIGSEGV。已加空检查。
- **`waitForCamera()` 空指针 + 错误信息**：`pylon_camera_->isReady()` 无空检查；错误信息 "Setting brightness failed" 为 copy-paste 错误。已修复。
- **`grabImage()` 空指针**：首行 `pylon_camera_->isBlaze()` 无空检查。已加空检查。
- **`setupInitialCameraInfo()` 空指针**：`pylon_camera_->getInitialCameraInfo()` 无空检查。已加空检查。
- **`sleep_for` 负值**：帧处理超时后 `sleep_time = frame_step - tdiff` 为负，`sleep_for` 负值行为实现定义。已加 `> 0` 保护。
- **帧率除零**：4 处 `1.0 / tdiff` 在 `tdiff == 0` 时产生 inf。已改为 `(tdiff > 0) ? (1.0 / tdiff) : 0.0`。
- **Keyence 条码 UTF-8 解码损坏**：工业 GS1 条码含 FNC1 等控制字符，`errors='replace'` 替换为 U+FFFD 导致字段分隔符丢失。已改为 `latin-1` 解码（字节→字符 1:1 无损）。
- **Keyence No-Read 误发布**：仅 `startswith('ER')` 判断失败，空串/'No Read'/'NG' 等常见 NoRead 响应被当作有效条码发布。已加 NoRead 白名单。
- **Keyence 参数回调阻塞**：参数回调与 trigger 服务回调并发竞争 `_socket_lock`，参数设置可阻塞 30s。已改为"设标志位 + 定时线程执行重连"。
- **AprilTag TF Buffer 双写**：`TransformListener` 已自动订阅 `/tf`，代码又显式订阅同一话题并手动 `set_transform`，高并发下导致 `ConnectivityException`。已改为仅 `_tf_topic != '/tf'` 时手动订阅。
- **WebSocket 死客户端泄漏**：`run_coroutine_threadsafe` 返回的 Future 异常未检查，死客户端无法清理。已加 `add_done_callback`。
- **`/api/events` limit 参数未校验**：limit=0 返回全量历史（可能数十 MB）。已钳制为 `[1, 10000]`。
- **日志轮转边界错误**：`max_file_count=1` 时 `.1` 永不被清理；`i > 0` 恒真导致 else 分支为死代码。已修复清理循环。
- **`vision_status_aggregator` 内存泄漏**：`_latest` 字典只增不删，长期运行无限增长。已在 `_on_diagnostics` 中清理超时条目。
- **标定工具路径遍历**：`aprilgrid_calibration.py`、`aprilgrid_capture.py`、`handeye_calibrate.py` 的 `--output` 参数无路径校验，可覆盖任意文件。已加 workspace/home 白名单。
- **`calibrateCamera` 输入 dtype 不一致**：object/image points 为 float32，initial_K 为 float64。已统一 float64 并加最少 8 角点下限。
- **`distortion_model` 硬编码**：永远写 `plumb_bob`，即使返回 4/8/12/14 系数模型。已按系数数量动态设置。
- **`FileStorage` 假成功 + 句柄泄漏**：打开失败时静默 no-op，异常时 `release()` 不被调用。已加 `isOpened()` 检查 + `try/finally`。
- **矩阵→四元数 180° 崩溃**：`trace ≈ -1` 时 `sqrt(0)` 导致 ZeroDivisionError。已加 SVD 正交化 + `max(0, ...)` + 归一化。
- **矩阵形状/奇异值无校验**：`np.linalg.inv` 未检查行列式，NaN 直接发布 TF。已加 shape/finite 校验。
- **`xarm_handeye_capture` 并发损坏**：MultiThreadedExecutor 下 timer 回调与 subscription 回调并发访问 `_samples`。已加 `threading.Lock` + `_finished` 标志。
- **`qrcode_node_main` 无异常保护**：构造异常 → `std::terminate` → SIGABRT。已加 `try-catch`。
- **`entrypoint.sh` 孤儿进程**：`kill $PID` 不杀子进程，SIGKILL 后相机设备被孤儿进程占用。已改为 `kill -- -$PID` 进程组广播。
- **`is_sleeping_` 数据竞争**：普通 `bool` 跨线程读写。已改为 `std::atomic<bool>`。
- **`aprilgrid_capture.py` 路径遍历**：`output_dir` 参数无校验。已加 workspace/home 白名单。

### Changed

- Keyence 扫码器响应解码从 `utf-8 (errors='replace') + strip()` 改为 `latin-1` 无损解码。下游消费者如需处理含控制字符的 GS1 条码，应按 `latin-1` 或原始字节处理。

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
