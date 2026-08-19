#!/usr/bin/env python3
"""Bridge camera images from the Basler container to host ROS 2 topics."""

import argparse
import json
import socket
import struct

import cv2
import numpy as np
import rclpy
from cv_bridge import CvBridge
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import CameraInfo, Image

HOST = "127.0.0.1"
PORT = 18765
IMAGE_TOPIC = "/my_camera/pylon_ros2_camera_node/image_raw"
INFO_TOPIC = "/my_camera/pylon_ros2_camera_node/camera_info"


def qos():
    profile = QoSProfile(depth=2)
    profile.reliability = ReliabilityPolicy.RELIABLE
    profile.durability = DurabilityPolicy.VOLATILE
    return profile


class HostBridge(Node):
    def __init__(self, port):
        super().__init__("camera_tcp_bridge")
        self.image_pub = self.create_publisher(Image, "/bridge/image_raw", qos())
        self.info_pub = self.create_publisher(CameraInfo, "/bridge/camera_info", qos())
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind((HOST, port))
        self.server.listen(1)
        self.server.settimeout(1.0)
        self.client = None
        self.info = None
        self.create_timer(0.01, self.poll)
        self.get_logger().info(f"Listening on {HOST}:{port}")

    def poll(self):
        if self.client is None:
            try:
                self.client, _ = self.server.accept()
                self.client.settimeout(2.0)
                self.get_logger().info("Container connected")
            except socket.timeout:
                return
        try:
            payload_size, metadata_size = struct.unpack("!II", self.read(8))
            metadata = json.loads(self.read(metadata_size).decode())
            image = cv2.imdecode(
                np.frombuffer(self.read(payload_size), np.uint8), cv2.IMREAD_GRAYSCALE
            )
            stamp = self.get_clock().now().to_msg()
            image_msg = Image()
            image_msg.header.stamp = stamp
            image_msg.header.frame_id = metadata["frame_id"]
            image_msg.height, image_msg.width = image.shape
            image_msg.encoding = "mono8"
            image_msg.step = image_msg.width
            image_msg.data = image.tobytes()
            self.image_pub.publish(image_msg)
            if self.info is None:
                self.info = CameraInfo()
                self.info.height = metadata["camera_info"]["height"]
                self.info.width = metadata["camera_info"]["width"]
                self.info.distortion_model = metadata["camera_info"]["distortion_model"]
                self.info.d = metadata["camera_info"]["d"]
                self.info.k = metadata["camera_info"]["k"]
                self.info.r = metadata["camera_info"]["r"]
                self.info.p = metadata["camera_info"]["p"]
                self.info.binning_x = metadata["camera_info"]["binning_x"]
                self.info.binning_y = metadata["camera_info"]["binning_y"]
            self.info.header = image_msg.header
            self.info_pub.publish(self.info)
        except (OSError, ValueError, TypeError, struct.error, json.JSONDecodeError):
            if self.client is not None:
                self.client.close()
            self.client = None

    def read(self, size):
        data = b""
        while len(data) < size:
            chunk = self.client.recv(size - len(data))
            if not chunk:
                raise OSError("bridge peer closed")
            data += chunk
        return data

    def destroy_node(self):
        if self.client is not None:
            self.client.close()
        self.server.close()
        super().destroy_node()


class ContainerForwarder(Node):
    def __init__(self, host, port):
        super().__init__("camera_tcp_forwarder")
        self.bridge = CvBridge()
        self.socket = None
        self.info = None
        self.host = host
        self.port = port
        self.create_subscription(CameraInfo, INFO_TOPIC, self.info_callback, qos())
        self.create_subscription(Image, IMAGE_TOPIC, self.image_callback, qos())

    def info_callback(self, message):
        self.info = message

    def image_callback(self, message):
        if self.info is None:
            return
        if self.socket is None:
            try:
                self.socket = socket.create_connection((self.host, self.port), 2.0)
            except OSError:
                return
        image = self.bridge.imgmsg_to_cv2(message, "mono8")
        encoded, payload = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not encoded:
            return
        metadata = {
            "frame_id": message.header.frame_id,
            "camera_info": {
                "height": self.info.height,
                "width": self.info.width,
                "distortion_model": self.info.distortion_model,
                "d": list(self.info.d), "k": list(self.info.k),
                "r": list(self.info.r), "p": list(self.info.p),
                "binning_x": self.info.binning_x,
                "binning_y": self.info.binning_y,
            },
        }
        metadata["camera_info"]["height"] = message.height
        metadata["camera_info"]["width"] = message.width
        metadata_bytes = json.dumps(metadata).encode()
        payload_bytes = payload.tobytes()
        try:
            self.socket.sendall(
                struct.pack("!II", len(payload_bytes), len(metadata_bytes))
                + metadata_bytes + payload_bytes
            )
        except OSError:
            self.socket.close()
            self.socket = None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("host", "forward"))
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args()
    rclpy.init()
    node = HostBridge(args.port) if args.mode == "host" else ContainerForwarder(args.host, args.port)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
