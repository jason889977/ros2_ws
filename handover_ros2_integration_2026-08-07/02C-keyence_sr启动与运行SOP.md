# 02C - keyence_sr 启动与运行 SOP

## 1. 目标与范围
本文档用于指导 `keyence_sr_wrapper` 独立节点的启动、运行、联调与基础故障排查。

节点能力：
- 提供服务 `/scanner/trigger`（`std_srvs/srv/Trigger`）用于触发一次扫码。
- 发布话题 `/scanner/barcode`（`std_msgs/msg/String`）输出扫码结果。

## 2. 前置条件
- 已安装并可使用 ROS2（建议 Humble）。
- 工作目录：`/home/ubuntu/ros2_ws`。
- 扫码器与主机网络互通（默认 IP `172.31.0.91`，端口 `9004`）。
- 已完成工作区构建（至少包含 `keyence_sr_wrapper` 包）。

## 3. 构建与环境加载
在终端执行：

```bash
cd /home/ubuntu/ros2_ws
colcon build --packages-select keyence_sr_wrapper
source /opt/ros/humble/setup.bash
source /home/ubuntu/ros2_ws/install/setup.bash
```

## 4. 启动方式

### 4.1 方式 A：直接运行节点

```bash
ros2 run keyence_sr_wrapper keyence_sr_node
```

### 4.2 方式 B：使用 launch（推荐，便于传参）

```bash
ros2 launch keyence_sr_wrapper keyence_sr_node.launch.py
```

如需覆盖默认 IP/端口：

```bash
ros2 launch keyence_sr_wrapper keyence_sr_node.launch.py scanner_ip:=172.31.0.92 scanner_port:=9004
```

## 5. 使用说明与联调步骤

### 5.1 监听扫码结果
新开一个终端（同样先 `source` 环境）执行：

```bash
ros2 topic echo /scanner/barcode
```

### 5.2 触发一次扫码
再开一个终端执行：

```bash
ros2 service call /scanner/trigger std_srvs/srv/Trigger {}
```

正常情况下：
- 服务返回 `success: true`，`message` 为扫码内容。
- 话题 `/scanner/barcode` 同步收到字符串消息。

异常情况下常见返回：
- `Scanner not connected.`
- `Timeout: Scanner did not respond in time.`
- `Scanner Error: ER...`
- `Communication Error: ...`

## 6. 参数说明

当前节点参数：
- `scanner_ip`（string，默认 `172.31.0.91`）
- `scanner_port`（int，默认 `9004`）

查询参数：

```bash
ros2 param list /keyence_sr_node
ros2 param get /keyence_sr_node scanner_ip
ros2 param get /keyence_sr_node scanner_port
```

说明：
- 当前实现在节点启动时读取参数并建立连接。
- 运行中执行 `ros2 param set` 不会自动重连到新 IP/端口。
- 需要变更 IP/端口时，请使用新参数重新启动节点（推荐通过 launch 传参）。

## 7. 常见问题排查

### 7.1 服务可调用但一直超时
- 检查扫码器是否在线、网线/交换机状态是否正常。
- 检查目标地址与端口是否与设备配置一致。
- 确认扫码器触发模式允许外部 TCP 命令触发。

### 7.2 提示 `Scanner not connected.`
- 说明节点启动时连接失败，查看节点日志中的连接错误。
- 修正网络后重启节点。

### 7.3 修改参数后不生效
- 这是当前版本预期行为。
- 请停止节点并使用新参数重新启动。

## 8. 停止与清理
- 在运行节点的终端按 `Ctrl+C` 停止。
- 节点退出时会自动关闭 TCP 连接。