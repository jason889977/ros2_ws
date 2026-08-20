ARG BASE_IMAGE=osrf/ros:humble-ros-base-jammy
FROM ${BASE_IMAGE}

ARG DEBIAN_FRONTEND=noninteractive
ARG UBUNTU_APT_MIRROR=http://mirrors.tuna.tsinghua.edu.cn/ubuntu
ARG ROS2_APT_MIRROR=http://mirrors.tuna.tsinghua.edu.cn/ros2/ubuntu
ENV ROS_DISTRO=humble
ENV PYLON_ROOT=/opt/pylon
ENV GENICAM_GENTL64_PATH=/opt/pylon/lib/gentlproducer/gtl

RUN set -eux && \
    sed -i \
        -e "s|http://archive.ubuntu.com/ubuntu|${UBUNTU_APT_MIRROR}|g" \
        -e "s|http://security.ubuntu.com/ubuntu|${UBUNTU_APT_MIRROR}|g" \
        /etc/apt/sources.list && \
    for apt_source in /etc/apt/sources.list.d/*; do \
        [ -f "$apt_source" ] || continue; \
        sed -i \
            -e "s|http://packages.ros.org/ros2/ubuntu|${ROS2_APT_MIRROR}|g" \
            -e "s|https://packages.ros.org/ros2/ubuntu|${ROS2_APT_MIRROR}|g" \
            -e 's|^Types:.*deb-src.*|Types: deb|g' \
            "$apt_source"; \
    done

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    rm -f /etc/apt/apt.conf.d/docker-clean && \
    printf '%s\n' 'Binary::apt::APT::Keep-Downloaded-Packages "true";' > /etc/apt/apt.conf.d/keep-cache && \
    apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake git python3-colcon-common-extensions python3-rosdep \
    libopencv-dev libyaml-cpp-dev \
    python3-opencv python3-yaml \
    ros-humble-apriltag-ros ros-humble-apriltag-msgs \
    ros-humble-camera-info-manager ros-humble-cv-bridge \
    ros-humble-diagnostic-updater ros-humble-image-geometry \
    ros-humble-image-transport ros-humble-pcl-ros \
    ros-humble-rclcpp-components ros-humble-sensor-msgs

# Place the licensed Basler pylon runtime/SDK under deploy/basler_camera/pylon-sdk.
# The SDK is intentionally not committed to this repository.
# This repo may contain either the Basler release tar.gz (setup archive) or the Debian
# package bundle tar.gz; both are supported here.
RUN --mount=type=bind,source=deploy/basler_camera/pylon-sdk,target=/tmp/pylon-sdk,readonly \
    --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    set -eux && \
    rm -f /etc/apt/apt.conf.d/docker-clean && \
    printf '%s\n' 'Binary::apt::APT::Keep-Downloaded-Packages "true";' > /etc/apt/apt.conf.d/keep-cache && \
    printf '%s\n' \
        'path-exclude=/opt/pylon/share/pylon/doc/*' \
        'path-exclude=/usr/share/doc/*' \
        'path-include=/usr/share/doc/*/copyright' \
        'path-exclude=/usr/share/man/*' \
        'path-exclude=/usr/share/locale/*' \
        > /etc/dpkg/dpkg.cfg.d/01_nodoc && \
    mkdir -p /tmp/pylon-inner && \
    if ls /tmp/pylon-sdk/*.tar.gz >/dev/null 2>&1; then \
        for pkg in /tmp/pylon-sdk/*.tar.gz; do \
            tar -xzf "$pkg" -C /tmp/pylon-inner; \
        done; \
    fi && \
    if ls /tmp/pylon-inner/*.deb >/dev/null 2>&1; then \
        apt-get update && \
        apt-get install -y --no-install-recommends /tmp/pylon-inner/*.deb && \
        rm -rf /tmp/pylon-inner; \
    else \
        mkdir -p /opt/pylon && \
        tar -xzf /tmp/pylon-sdk/*_setup.tar.gz -C /opt/pylon && \
        rm -rf /tmp/pylon-inner; \
    fi

WORKDIR /opt/ros2_ws
COPY src/ src/
COPY deploy/basler_camera/config/ deploy/basler_camera/config/
COPY deploy/basler_camera/*.sh deploy/basler_camera/
COPY deploy/basler_camera/README.md deploy/basler_camera/ROS2-INTERFACE.md deploy/basler_camera/CHANGELOG.md deploy/basler_camera/

RUN . /opt/ros/humble/setup.sh && \
    colcon build --symlink-install

COPY deploy/basler_camera/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh deploy/basler_camera/*.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["ros2", "launch", "pylon_ros2_camera_wrapper", "pylon_ros2_camera.launch.py"]
