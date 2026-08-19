from glob import glob
import os

from setuptools import find_packages, setup

package_name = 'qrcode_detector'

# 收集 models/ 目录下所有文件（编译后会安装到 share 目录）
model_files = [
    (os.path.join('share', package_name, 'models'),
     [os.path.join('models', f) for f in os.listdir('models')
      if os.path.isfile(os.path.join('models', f))])
] if os.path.isdir('models') and os.listdir('models') else []

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        # ament 索引
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        # package.xml
        ('share/' + package_name, ['package.xml']),
        # launch 文件
        (os.path.join('share', package_name, 'launch'),
            glob(os.path.join('launch', '*.launch.py'))),
        # config 文件
        (os.path.join('share', package_name, 'config'),
            glob(os.path.join('config', '*.yaml'))),
    ] + model_files,
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='jason889977',
    maintainer_email='jason889977@users.noreply.github.com',
    description='ROS 2 二维码识别节点，基于 OpenCV WeChatQRCode，适配 Basler 相机',
    license='BSD-3-Clause',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'qrcode_node = qrcode_detector.qrcode_node:main',
        ],
    },
)
