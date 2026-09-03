import os

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    scanner_ip_arg = DeclareLaunchArgument(
        'scanner_ip',
        default_value=os.environ.get('SCANNER_IP', '172.31.0.91'),
        description='IP address of Keyence SR scanner',
    )
    scanner_port_arg = DeclareLaunchArgument(
        'scanner_port',
        default_value=os.environ.get('SCANNER_PORT', '9004'),
        description='TCP port of Keyence SR scanner',
    )
    reconnect_interval_arg = DeclareLaunchArgument(
        'reconnect_interval_s',
        default_value='5.0',
        description='Seconds between reconnect attempts when scanner is offline',
    )

    scanner_node = Node(
        package='keyence_sr_wrapper',
        executable='keyence_sr_node',
        name='keyence_sr_node',
        output='screen',
        parameters=[
            {
                'scanner_ip': LaunchConfiguration('scanner_ip'),
                'scanner_port': LaunchConfiguration('scanner_port'),
                'reconnect_interval_s': LaunchConfiguration('reconnect_interval_s'),
            }
        ],
    )

    return LaunchDescription([
        scanner_ip_arg,
        scanner_port_arg,
        reconnect_interval_arg,
        scanner_node,
    ])
