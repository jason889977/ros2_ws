# 05 - Scripts and Automation

## 1. Script Inventory

| Script | Path | Purpose | Notes |
|---|---|---|---|
| Dependency installer | install_dependencies.sh | Install system/ROS dependencies and build workspace | Requires ROS_DISTRO initialized |
| Basler installer | install_basler_driver.sh | Download/install pylon SDK, set USB rules, build workspace | Includes pylon acquisition path |
| Model downloader | src/qrcode_detector/scripts/download_models.py | Download WeChatQRCode model files | Needed for deterministic QR behavior |

## 2. Script Execution Order

1. source /opt/ros/humble/setup.bash
2. ./install_dependencies.sh
3. ./install_basler_driver.sh
4. source install/setup.bash

## 3. Script Safety Notes

- Keep script execution in workspace root.
- Verify network availability before pylon/model download.
- Review pylon version policy before production freeze.

## 4. Automation Example: Non-interactive quick setup

```bash
#!/usr/bin/env bash
set -euo pipefail

cd /home/ubuntu/ros2_ws
source /opt/ros/humble/setup.bash

./install_dependencies.sh
./install_basler_driver.sh

source install/setup.bash
colcon list
```

## 5. Deployment Script (Operational)

Create and use the helper script below for repeated field deployment.

Path:
- scripts/deploy_and_run_camera_qr.sh

Behavior:
- validate env
- build required packages
- launch camera node
- launch qrcode node
- print validation commands

## 6. Script Parameters (Current Defaults)

Defined in `scripts/deploy_and_run_camera_qr.sh`:

- `WORKSPACE_DIR=/home/ubuntu/ros2_ws`
- `CAMERA_ID=basler_106611_18`
- `CAMERA_CONFIG=/home/ubuntu/ros2_ws/install/pylon_ros2_camera_wrapper/share/pylon_ros2_camera_wrapper/config/aca2500_106611_18.yaml`
- `IMAGE_TOPIC=/$CAMERA_ID/pylon_ros2_camera_node/image_raw`

If you need another camera profile, duplicate the script and change `CAMERA_ID` and `CAMERA_CONFIG`.

## 7. Example Run

```bash
cd /home/ubuntu/ros2_ws
./scripts/deploy_and_run_camera_qr.sh
```

Expected output includes:
- Camera launch PID
- QR launch PID
- Validation commands
