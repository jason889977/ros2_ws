# Keyence SR Wrapper ROS 2 Interface

## 节点

- `/keyence_sr_node`

## 发布 Topic

| 相对名称 | 完整默认名称 | 类型 |
| --- | --- | --- |
| `/scanner/barcode` | `/scanner/barcode` | `std_msgs/msg/String` |

## 服务

| 服务名称 | 类型 |
| --- | --- |
| `/scanner/trigger` | `std_srvs/srv/Trigger` |

## 订阅 Topic

- 无业务订阅 Topic

## Actions

- 无 Action 定义

## TF

- 无 TF 输出
- 该模块为网络扫码设备封装，不参与坐标系变换

## 参数

- `scanner_ip`：默认 `172.31.0.91`
- `scanner_port`：默认 `9004`
