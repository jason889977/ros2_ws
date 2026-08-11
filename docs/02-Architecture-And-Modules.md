# 02 - Architecture and Module Details

## 1. Package-Level Architecture

```mermaid
flowchart LR
  A[pylon_ros2_camera_interfaces\nmsg/srv/action] --> B[pylon_ros2_camera_component\ncore camera logic]
  B --> C[pylon_ros2_camera_wrapper\nnode launcher/runtime host]
  C --> D[/camera namespace topics\nimage_raw, camera_info, status/]
  D --> E[qrcode_detector\nwechat qr decode]
  E --> F[/wechat_qr_node/decoded_info]
  G[pylon_ros2_camera_test] --> C
  G --> B
```

## 2. Runtime Node Topology

```mermaid
flowchart TB
  L[ros2 launch pylon_ros2_camera_wrapper pylon_ros2_camera.launch.py]
  L --> N[/<camera_id>/pylon_ros2_camera_node]
  N --> T1[/<camera_id>/pylon_ros2_camera_node/image_raw]
  N --> T2[/<camera_id>/pylon_ros2_camera_node/camera_info]
  N --> T3[/<camera_id>/pylon_ros2_camera_node/status]
  QL[ros2 launch qrcode_detector qrcode_detector.launch.py]
  QL --> QN[/wechat_qr_node]
  T1 --> QN
  QN --> QT[/wechat_qr_node/decoded_info]
```

## 3. Module Deep-Dive

### 3.1 pylon_ros2_camera_wrapper

Responsibilities:
- Provide launch-time parameterization and namespace mapping
- Create and host pylon_ros2_camera_node process
- Bridge YAML/launch arguments into runtime parameters

Key files:
- src/pylon_ros2_camera_wrapper/src/pylon_ros2_camera_wrapper.cpp
- src/pylon_ros2_camera_wrapper/launch/pylon_ros2_camera.launch.py
- src/pylon_ros2_camera_wrapper/config/default.yaml

Important parameters:
- camera_id
- config_file
- mtu_size
- startup_user_set
- enable_status_publisher

### 3.2 pylon_ros2_camera_component

Responsibilities:
- Camera device enumeration and connection
- Retry loop on device unavailable
- Start grabbing and publish image/camera_info/status
- Expose extensive service/action interface for camera controls

Key files:
- src/pylon_ros2_camera_component/src/pylon_ros2_camera.cpp
- src/pylon_ros2_camera_component/src/pylon_ros2_camera_node.cpp
- src/pylon_ros2_camera_component/src/tools/set_device_user_id.cpp

### 3.3 qrcode_detector

Responsibilities:
- Subscribe image topic
- Convert ROS Image -> OpenCV image
- Decode QR with WeChatQRCode
- Publish decoded text records

Key files:
- src/qrcode_detector/qrcode_detector/qrcode_node.py
- src/qrcode_detector/launch/qrcode_detector.launch.py
- src/qrcode_detector/config/params.yaml
- src/qrcode_detector/scripts/download_models.py

## 4. Interface Contract Summary

Input topic contract for qrcode_detector:
- sensor_msgs/msg/Image
- Expected encoding convertible to bgr8 by CvBridge

Output topic contract:
- /wechat_qr_node/decoded_info
- std_msgs/msg/String, one message per decoded payload

## 5. Namespace/Topic Alignment Rule

By default:
- Camera publishes under namespaced private topic path
- QR node default image_topic may be /camera/image_raw

Therefore, launch qrcode_detector with explicit image_topic matching runtime camera namespace.

## 6. Evidence References

- qrcode parameter defaults and output topic: [src/qrcode_detector/qrcode_detector/qrcode_node.py](../src/qrcode_detector/qrcode_detector/qrcode_node.py#L19), [src/qrcode_detector/qrcode_detector/qrcode_node.py](../src/qrcode_detector/qrcode_detector/qrcode_node.py#L40), [src/qrcode_detector/qrcode_detector/qrcode_node.py](../src/qrcode_detector/qrcode_detector/qrcode_node.py#L86)
- qrcode launch defaults: [src/qrcode_detector/launch/qrcode_detector.launch.py](../src/qrcode_detector/launch/qrcode_detector.launch.py#L13), [src/qrcode_detector/launch/qrcode_detector.launch.py](../src/qrcode_detector/launch/qrcode_detector.launch.py#L27)
- wrapper build and lint-gate settings: [src/pylon_ros2_camera_wrapper/CMakeLists.txt](../src/pylon_ros2_camera_wrapper/CMakeLists.txt#L1), [src/pylon_ros2_camera_wrapper/CMakeLists.txt](../src/pylon_ros2_camera_wrapper/CMakeLists.txt#L11), [src/pylon_ros2_camera_wrapper/CMakeLists.txt](../src/pylon_ros2_camera_wrapper/CMakeLists.txt#L78)
