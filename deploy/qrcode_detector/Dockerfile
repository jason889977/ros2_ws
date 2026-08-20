FROM osrf/ros:humble-desktop

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /opt/ros2_ws

RUN apt-get update && apt-get install -y \
    python3-opencv \
    python3-pip \
    python3-dev \
    python3-numpy \
    ros-humble-cv-bridge \
    ros-humble-image-transport \
    ros-humble-sensor-msgs \
    ros-humble-std-msgs \
    ros-humble-rclpy \
    && rm -rf /var/lib/apt/lists/*

COPY src/qrcode_detector/ src/qrcode_detector/

RUN /bin/bash -lc 'source /opt/ros/humble/setup.bash && colcon build --packages-select qrcode_detector --symlink-install --cmake-args -DCMAKE_BUILD_TYPE=Release'

CMD ["/bin/bash", "-lc", "source /opt/ros/humble/setup.bash && source /opt/ros2_ws/install/setup.bash && ros2 launch qrcode_detector qrcode_detector.launch.py"]
