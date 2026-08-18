# QR Code Detector ROS 2 Interface

## 节点

- `/wechat_qr_node`

## 订阅 Topic

| 相对名称 | 完整默认名称 | 类型 |
| --- | --- | --- |
| `/camera/image_raw` | `/camera/image_raw` | `sensor_msgs/msg/Image` |
| 或者通过参数覆盖 | `/my_camera/pylon_ros2_camera_node/image_raw` | `sensor_msgs/msg/Image` |

默认输入图像由 Basler 相机驱动提供：

- `/my_camera/pylon_ros2_camera_node/image_raw`
- 类型：`sensor_msgs/msg/Image`

## 发布 Topic

| 相对名称 | 完整默认名称 | 类型 |
| --- | --- | --- |
| `~/decoded_info` | `/wechat_qr_node/decoded_info` | `std_msgs/msg/String` |

发布内容为识别到的 QR 码字符串，以 `std_msgs/String.data` 形式输出。

## Services

- 无常规业务 Service
- 本节点仅在图像流基础上进行解码，不提供标准服务接口

## Actions

- 无 Action 定义

## TF

- 不发布 TF
- 不依赖 TF 作为输入
- 仅基于图像帧解析 QR 码内容

## 参数

- `image_topic`：输入图像话题，默认 `/my_camera/pylon_ros2_camera_node/image_raw`
- `model_dir`：WeChatQR 模型目录
- `queue_size`：订阅队列长度，默认 10
- `prefer_wechat_qr`：是否优先使用 WeChatQR，默认 `false`
- `use_camera_info`：预留参数，当前未启用
