# 02C - keyence_sr 启动与运行 SOP

## 1. 目标与范围
本文档用于指导统一视觉容器内 `keyence_sr_wrapper` 的启动、运行、联调与基础故障排查。

节点能力：
- 提供服务 `/scanner/trigger`（`std_srvs/srv/Trigger`）用于触发一次扫码。
- 发布话题 `/scanner/barcode`（`std_msgs/msg/String`）输出扫码结果。
- 支持运行时修改 IP/端口参数并自动重连，无需重启节点。
- 内置定时后台重连机制，连接断开后自动恢复。

## 2. 前置条件
- `basler_camera` 容器已启动并处于运行状态。
- 容器内已安装统一启动包 `industrial_vision_bringup`。
- 扫码器与主机网络互通（默认 IP `172.31.0.91`，端口 `9004`）。
- 容器镜像已构建，包含 `keyence_sr_wrapper` 包。

## 3. 统一容器启动
在终端执行：

```bash
cd /home/ubuntu/ros2_ws
sudo -n docker restart basler_camera
sudo -n docker inspect --format '{{.State.Status}} {{.State.Health.Status}}' basler_camera
```

Keyence 随 Basler、AprilTag 和二维码节点一起由
`industrial_vision_bringup/vision_pipeline.launch.py` 启动，不需要在宿主机另起 Keyence 节点。

## 4. 启动方式

### 4.1 兼容模式：单独运行节点

```bash
sudo -n docker exec -it basler_camera bash -lc \
  'source /opt/ros/humble/setup.bash && source /opt/ros2_ws/install/setup.bash && \
   ros2 run keyence_sr_wrapper keyence_sr_node'
```

### 4.2 统一 pipeline 参数覆盖

```bash
sudo -n docker compose -f /home/ubuntu/ros2_ws/deploy/basler_camera/docker-compose.yml \
  up -d --force-recreate
```

如需覆盖默认 IP/端口/重连间隔：

```bash
SCANNER_IP=172.31.0.92 SCANNER_PORT=9004 RECONNECT_INTERVAL_S=3.0 \
sudo -n docker compose -f /home/ubuntu/ros2_ws/deploy/basler_camera/docker-compose.yml \
  up -d --force-recreate
```

## 5. 使用说明与联调步骤

### 5.1 监听扫码结果
新开一个终端（同样先 `source` 环境）执行：

```bash
sudo -n docker exec basler_camera bash -lc \
  'source /opt/ros/humble/setup.bash && source /opt/ros2_ws/install/setup.bash && \
   ros2 topic echo /scanner/barcode'
```

### 5.2 触发一次扫码
再开一个终端执行：

```bash
sudo -n docker exec basler_camera bash -lc \
  'source /opt/ros/humble/setup.bash && source /opt/ros2_ws/install/setup.bash && \
   ros2 service call /scanner/trigger std_srvs/srv/Trigger {}'
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
- `scanner_ip`（string，默认 `172.31.0.91`）— 扫码器 TCP 地址
- `scanner_port`（int，默认 `9004`）— 扫码器 TCP 端口
- `reconnect_interval_s`（double，默认 `5.0`）— 后台重连检查间隔（秒）

查询参数：

```bash
sudo -n docker exec basler_camera bash -lc \
  'source /opt/ros/humble/setup.bash && source /opt/ros2_ws/install/setup.bash && \
   ros2 param list /keyence_sr_node'
```

### 6.1 运行时参数热重载

节点支持在运行中动态修改 `scanner_ip` 和 `scanner_port`，修改后会自动断开旧连接并重新连接到新地址，无需重启节点。

示例：切换到新扫码器

```bash
# 修改 IP，节点自动重连
sudo -n docker exec basler_camera bash -lc \
  'source /opt/ros/humble/setup.bash && source /opt/ros2_ws/install/setup.bash && \
   ros2 param set /keyence_sr_node scanner_ip 172.31.0.92'

# 修改端口，节点自动重连
sudo -n docker exec basler_camera bash -lc \
  'source /opt/ros/humble/setup.bash && source /opt/ros2_ws/install/setup.bash && \
   ros2 param set /keyence_sr_node scanner_port 9005'
```

节点日志会输出：
```
[INFO] 参数 scanner_ip 已更新为: 172.31.0.92
[INFO] 正在重新连接扫码器...
[INFO] Successfully connected to Keyence SR-1000.
```

### 6.2 自动重连机制

- 当 `trigger_scan_callback` 中发生通信异常（如连接断开）时，节点会立即尝试重连。
- 后台定时器按 `reconnect_interval_s` 间隔检查连接状态，若发现连接断开则自动重连。
- 重连过程中服务调用会返回 `Scanner not connected.`，等待重连完成后即可恢复正常。

## 7. 常见问题排查

### 7.1 服务可调用但一直超时
- 检查扫码器是否在线、网线/交换机状态是否正常。
- 检查目标地址与端口是否与设备配置一致。
- 确认扫码器触发模式允许外部 TCP 命令触发。

### 7.2 提示 `Scanner not connected.`
- 说明节点当前未连接到扫码器（启动时连接失败或运行中断开）。
- 后台重连定时器仍在运行，等待数秒后可能自动恢复。
- 若持续无法连接，检查网络后重启节点或修改参数触发重连。

### 7.3 修改参数后连接未恢复
- 确认节点日志中是否出现"正在重新连接扫码器..."。
- 检查新 IP/端口是否可达：`ping <ip>` 或 `nc -zv <ip> <port>`。
- 若后台重连未触发，可手动调用一次服务触发即时重连：
  ```bash
  ros2 service call /scanner/trigger std_srvs/srv/Trigger {}
  ```
- 如仍无法恢复，停止节点并使用新参数重新启动。

## 8. 停止与清理
- 统一容器停止时执行：
  ```bash
  sudo -n docker stop basler_camera
  ```
- 节点退出时会自动关闭 TCP 连接；容器重启后会自动恢复连接尝试。