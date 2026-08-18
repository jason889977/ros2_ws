FROM osrf/ros:humble-ros-base-jammy

ARG DEBIAN_FRONTEND=noninteractive
ENV ROS_DISTRO=humble
ENV PYLON_ROOT=/opt/pylon
ENV GENICAM_GENTL64_PATH=/opt/pylon/lib/gentlproducer/gtl

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake git python3-colcon-common-extensions python3-rosdep \
    libopencv-dev libyaml-cpp-dev \
    ros-humble-camera-info-manager ros-humble-cv-bridge \
    ros-humble-diagnostic-updater ros-humble-image-geometry \
    ros-humble-image-transport ros-humble-pcl-ros \
    ros-humble-rclcpp-components ros-humble-sensor-msgs \
    && rm -rf /var/lib/apt/lists/*

# Place the licensed Basler pylon runtime/SDK under deploy/basler_camera/pylon-sdk.
# The SDK is intentionally not committed to this repository.
# Place the licensed Basler pylon setup archive under deploy/basler_camera/pylon-sdk.
# The archive contains a second SDK tarball, so both layers must be extracted.
COPY deploy/basler_camera/pylon-sdk/pylon-8.0.0-linux-x86_64_setup.tar.gz /tmp/pylon-setup.tar.gz
RUN mkdir -p /tmp/pylon-inner /opt/pylon && \
    tar -xzf /tmp/pylon-setup.tar.gz -C /tmp/pylon-inner && \
    tar -xzf /tmp/pylon-inner/pylon-*.tar.gz -C /opt/pylon && \
    rm -rf /tmp/pylon-setup.tar.gz /tmp/pylon-inner

WORKDIR /opt/ros2_ws
COPY src/ src/
COPY deploy/basler_camera/config/ deploy/basler_camera/config/
COPY deploy/basler_camera/*.sh deploy/basler_camera/
COPY deploy/basler_camera/README.md deploy/basler_camera/ROS2-INTERFACE.md deploy/basler_camera/CHANGELOG.md deploy/basler_camera/

RUN . /opt/ros/humble/setup.sh && \
    rosdep update --rosdistro humble && \
    rosdep install --from-paths src --ignore-src --rosdistro humble -r -y && \
    colcon build --symlink-install --packages-up-to pylon_ros2_camera_wrapper

COPY deploy/basler_camera/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh deploy/basler_camera/*.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["ros2", "launch", "pylon_ros2_camera_wrapper", "pylon_ros2_camera.launch.py"]
