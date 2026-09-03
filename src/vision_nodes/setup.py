from setuptools import find_packages, setup

package_name = 'vision_nodes'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='jason889977',
    maintainer_email='jason889977@users.noreply.github.com',
    description='ROS 2 observability nodes for the industrial vision pipeline.',
    license='BSD-3-Clause',
    extras_require={'test': ['pytest']},
    entry_points={
        'console_scripts': [
            'vision_status_aggregator = vision_nodes.vision_status_aggregator:main',
            'event_logger = vision_nodes.event_logger:main',
            'web_dashboard = vision_nodes.web_dashboard_node:main',
            'apriltag_pose_reader = vision_nodes.apriltag_pose_reader:main',
        ],
    },
)
