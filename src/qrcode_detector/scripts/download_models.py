#!/usr/bin/env python3
"""
下载 WeChatQRCode 深度学习模型文件

功能概述：
    从 GitHub 下载 WeChatQR 检测器所需的 4 个 Caffe 模型文件，
    保存到功能包的 models/ 目录下，供 qrcode_node.py 运行时加载。

背景知识：
    WeChatQRCode 是微信开源的 QR 码检测引擎，基于 Caffe 深度学习框架。
    它包含两个神经网络：
      1. 检测网络（detect）— 定位图像中 QR 码的位置和四个角点
      2. 超分辨率网络（sr）— 对小尺寸/模糊 QR 码做超分辨率重建

    每个网络需要两个文件：
      - .prototxt   — 网络结构定义（文本格式，描述层与层之间的连接关系）
      - .caffemodel — 网络权重文件（二进制格式，存储训练好的参数）

    因此一共需要 4 个文件。

使用方法：
    python3 src/qrcode_detector/scripts/download_models.py
    下载完成后需要重新编译功能包，使模型文件被复制到 install 目录：
    colcon build --packages-select qrcode_detector
"""

# ============================================================================
# 导入部分
# ============================================================================

import os
# Python 标准库：操作系统接口
# 提供路径操作（os.path）、目录创建（os.makedirs）等功能

import sys
# Python 标准库：系统接口
# 此处主要用于 sys.stderr（标准错误输出流）和 sys.exit()（退出程序）
# sys.stderr 与 print 默认的 stdout 不同，错误信息输出到 stderr
# 可以在终端中被区分显示（通常显示为红色），也方便重定向

import urllib.request
# Python 标准库：URL 请求
# 提供从 URL 下载文件的功能，无需安装第三方库（如 requests）
# urlretrieve(url, filename) 是最简单的下载方法：
#   直接将从 url 获取的内容保存到本地 filename 文件中


# ============================================================================
# 常量定义
# ============================================================================

# 模型文件的 GitHub 下载地址
# 这些文件托管在 WeChatCV 组织的 opencv_3rdparty 仓库的 wechat_qrcode 分支
# raw.githubusercontent.com 是 GitHub 的原始文件服务，可直接下载单个文件
BASE_URL = (
    'https://raw.githubusercontent.com/WeChatCV/opencv_3rdparty/'
    'wechat_qrcode/'
)
# Python 字符串隐式拼接：相邻的两个字符串字面量会自动合并为一个
# 等价于: 'https://raw.githubusercontent.com/WeChatCV/opencv_3rdparty/wechat_qrcode/'
# 这种写法用于避免单行过长，提高可读性

# 需要下载的 4 个模型文件
MODELS = [
    'detect.prototxt',     # 检测网络的结构定义（Caffe Protobuf 文本格式）
    'detect.caffemodel',   # 检测网络的训练权重（Caffe 二进制格式，约 1.2MB）
    'sr.prototxt',         # 超分辨率网络的结构定义
    'sr.caffemodel',       # 超分辨率网络的训练权重（Caffe 二进制格式，约 5.4MB）
]
# Caffe 模型格式说明：
#   .prototxt   — 使用 Protocol Buffers 文本格式描述网络拓扑结构
#                 包含每一层的类型、参数、输入输出维度等
#   .caffemodel — 二进制文件，存储每一层训练好的权重和偏置
#                 由 Caffe 框架训练得到，OpenCV 的 DNN 模块可直接加载推理


# ============================================================================
# 下载函数
# ============================================================================

def download(url: str, dest: str):
    """
    从 URL 下载单个文件到本地路径。

    参数:
        url:  文件的完整下载地址（如 https://...detect.prototxt）
        dest: 本地保存路径（如 /home/ubuntu/.../models/detect.prototxt）

    行为：
        - 如果目标文件已存在 → 跳过（幂等性，可重复运行）
        - 如果目标文件不存在 → 下载并保存
        - 如果下载失败 → 打印错误到 stderr 并退出程序
    """
    # 检查目标文件是否已经存在
    # os.path.isfile() 返回 True 表示路径存在且是普通文件
    # 这个检查使得脚本具有幂等性：多次运行不会重复下载
    if os.path.isfile(dest):
        # os.path.basename() 提取路径中的文件名部分
        # 例如: '/home/ubuntu/models/detect.prototxt' → 'detect.prototxt'
        print(f'  [跳过] {os.path.basename(dest)} 已存在')
        return  # 直接返回，不执行下载

    print(f'  [下载] {os.path.basename(dest)} ...')

    try:
        # urllib.request.urlretrieve(url, filename) 是 Python 内置的下载方法
        # 它会将 url 指向的远程文件下载到本地 filename 路径
        # 底层使用 HTTP GET 请求，支持 HTTP/HTTPS 协议
        # 注意：此方法没有进度条显示，大文件下载时看起来像卡住了
        urllib.request.urlretrieve(url, dest)
        print(f'  [完成] {os.path.basename(dest)}')
    except Exception as e:
        # 捕获所有异常（网络超时、DNS 解析失败、404 等）
        # file=sys.stderr 将错误信息输出到标准错误流（而非标准输出）
        # 这样在 shell 中可以用 2>error.log 单独捕获错误信息
        print(f'  [错误] 下载 {os.path.basename(dest)} 失败: {e}', file=sys.stderr)
        # sys.exit(1) 以非零退出码终止程序
        # 退出码 1 表示异常退出（0 表示正常退出）
        # 在 CI/CD 或 shell 脚本中，非零退出码会触发错误处理逻辑
        sys.exit(1)


# ============================================================================
# 主函数
# ============================================================================

def main():
    """
    主函数：确定模型保存目录，依次下载所有模型文件。
    """
    # ---- 确定脚本所在目录 ----
    # __file__ 是 Python 内置变量，值为当前脚本的文件路径
    # 例如: '/home/ubuntu/ros2_ws/src/qrcode_detector/scripts/download_models.py'

    # os.path.abspath(__file__) 将路径转为绝对路径（消除 . 和 .. 等相对引用）
    # os.path.dirname(path)     取路径的目录部分
    # 第一步：得到 scripts/ 目录的绝对路径
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # 例如: '/home/ubuntu/ros2_ws/src/qrcode_detector/scripts'

    # 第二步：再往上一级，得到功能包根目录 qrcode_detector/
    # os.path.dirname() 再次调用，去掉末尾的 'scripts'
    pkg_dir = os.path.dirname(script_dir)
    # 例如: '/home/ubuntu/ros2_ws/src/qrcode_detector'

    # 第三步：拼接出模型目录路径
    # os.path.join() 安全地拼接路径（自动处理分隔符）
    model_dir = os.path.join(pkg_dir, 'models')
    # 例如: '/home/ubuntu/ros2_ws/src/qrcode_detector/models'

    # 创建 models/ 目录（如果不存在）
    # exist_ok=True 表示目录已存在时不报错（默认会抛 FileExistsError）
    os.makedirs(model_dir, exist_ok=True)

    print(f'模型保存目录: {model_dir}\n')

    # ---- 依次下载每个模型文件 ----
    for name in MODELS:
        # 拼接完整的下载 URL
        # 例如: 'https://...wechat_qrcode/' + 'detect.prototxt'
        url = BASE_URL + name
        # 拼接完整的本地保存路径
        # 例如: '/home/ubuntu/.../models/' + 'detect.prototxt'
        dest = os.path.join(model_dir, name)
        # 调用下载函数
        download(url, dest)

    # ---- 下载完成提示 ----
    print('\n✅ 所有模型文件下载完成！')
    # 提示用户重新编译功能包
    # colcon build 会将 models/ 目录下的文件复制到 install/ 目录
    # 因为 setup.py 中通过 data_files 指定了 models/ 的安装规则
    # 节点运行时通过 get_package_share_directory() 从 install/ 目录查找模型
    print('请重新编译功能包: colcon build --packages-select qrcode_detector')


# Python 标准入口点：
# 只有直接运行此脚本时（python3 download_models.py）才执行 main()
# 如果被其他模块 import，则不会自动执行
if __name__ == '__main__':
    main()
