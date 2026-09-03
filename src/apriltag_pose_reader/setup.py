from glob import glob
import os

from setuptools import find_packages, setup

package_name = 'apriltag_pose_reader'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'config'), glob(os.path.join('config', '*.yaml'))),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='jason889977',
    maintainer_email='jason889977@users.noreply.github.com',
    description='ROS 2 AprilTag pose reader that republishes TF detections as pose topics.',
    license='BSD-3-Clause',
    extras_require={
        'test': ['pytest'],
    },
    entry_points={
        'console_scripts': [
        ],
    },
)
