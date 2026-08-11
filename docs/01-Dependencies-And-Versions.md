# 01 - Dependencies and Versions

## 1. Environment Baseline

- OS: Ubuntu 22.04 (Jammy)
- ROS 2: Humble
- Build Toolchain: colcon + CMake + GCC/Clang

Evidence:
- install_basler_driver.sh
- install_dependencies.sh

## 2. Dependency Matrix

| Category | Package/Tool | Version/Range | Source of Truth | Notes |
|---|---|---|---|---|
| OS | Ubuntu | 22.04 | install scripts | Required baseline |
| ROS 2 | humble | fixed distro | install scripts | Must source /opt/ros/humble/setup.bash |
| Compiler std | C++ | C++17 | package CMakeLists | Core C++ packages use C++17 |
| CMake | cmake_minimum_required | 3.22 | package CMakeLists | component/wrapper/test/interfaces |
| Python | python3 | runtime-managed | shebang/tests/install tree | Jammy 默认运行时通常为 3.10 |
| OpenCV (Python) | python3-opencv | apt-managed | install_dependencies.sh | Needed by qrcode_detector |
| ROS cv bridge | ros-$ROS_DISTRO-cv-bridge | distro package | install_dependencies.sh/package.xml | Required for image conversion |
| Basler SDK | pylon | 8.0.0 or newer | scripts/guide | Version guidance is inconsistent; see below |
| Colcon | python3-colcon-common-extensions | apt package | install_dependencies.sh | Required for build/test |

## 3. Version Policy and Ambiguities

### 3.1 pylon Version Ambiguity

Current repository has two guidance lines:
- install_basler_driver.sh sets PYLON_VERSION=8.0.0
- install_dependencies.sh text references pylon 8.x Debian 安装包

Recommended policy for this project doc set:
- Primary validated line: pylon 8.x series (scripted path)
- Secondary acceptable line: latest pylon officially compatible with ROS wrapper and host kernel
- During release, freeze one exact pylon version and checksum in deployment notes

## 4. Required Commands

```bash
source /opt/ros/humble/setup.bash
```

```bash
colcon build --symlink-install --cmake-args -DCMAKE_BUILD_TYPE=Release
```

## 5. Compatibility Notes

- qrcode_detector requires OpenCV with wechat_qrcode support (observed in runtime validation).
- If running in isolated/sandbox environments, network and raw socket operations (ping, camera checks) may require unsandboxed execution.

## 6. Verification Checklist

- [ ] ROS_DISTRO=humble is active
- [ ] /opt/pylon exists and is configured
- [ ] colcon can discover all packages
- [ ] python3-opencv is installed
- [ ] cv_bridge and launch_ros deps are available

## 7. Evidence References

- Ubuntu 22.04 + ROS 2 Humble baseline: [install_basler_driver.sh](../install_basler_driver.sh#L4)
- OpenCV/colcon/cv_bridge dependencies: [install_dependencies.sh](../install_dependencies.sh#L35), [install_dependencies.sh](../install_dependencies.sh#L37), [install_dependencies.sh](../install_dependencies.sh#L51)
- CMake/C++ standard (wrapper): [src/pylon_ros2_camera_wrapper/CMakeLists.txt](../src/pylon_ros2_camera_wrapper/CMakeLists.txt#L1), [src/pylon_ros2_camera_wrapper/CMakeLists.txt](../src/pylon_ros2_camera_wrapper/CMakeLists.txt#L11)
- CMake/C++ standard (component): [src/pylon_ros2_camera_component/CMakeLists.txt](../src/pylon_ros2_camera_component/CMakeLists.txt#L1), [src/pylon_ros2_camera_component/CMakeLists.txt](../src/pylon_ros2_camera_component/CMakeLists.txt#L11)
