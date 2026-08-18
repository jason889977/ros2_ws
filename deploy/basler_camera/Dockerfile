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
COPY pylon-sdk/ /opt/pylon/

WORKDIR /opt/ros2_ws
COPY src/ src/
COPY deploy/basler_camera/ deploy/basler_camera/

RUN . /opt/ros/humble/setup.sh && \
    rosdep update --rosdistro humble && \
    rosdep install --from-paths src --ignore-src --rosdistro humble -r -y && \
    colcon build --symlink-install --packages-up-to pylon_ros2_camera_wrapper

COPY deploy/basler_camera/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh deploy/basler_camera/*.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["ros2", "launch", "pylon_ros2_camera_wrapper", "pylon_ros2_camera.launch.py"]
