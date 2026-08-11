#!/usr/bin/env python3
"""Download WeChatQRCode model files into the package models directory."""

import os
import sys
import urllib.request

# 模型文件下载地址（OpenCV contrib wechat_qrcode 官方仓库）
BASE_URL = (
    'https://raw.githubusercontent.com/WeChatCV/opencv_3rdparty/'
    'wechat_qrcode/'
)

MODELS = [
    'detect.prototxt',
    'detect.caffemodel',
    'sr.prototxt',
    'sr.caffemodel',
]


def download(url: str, dest: str):
    if os.path.isfile(dest):
        print(f'  [跳过] {os.path.basename(dest)} 已存在')
        return
    print(f'  [下载] {os.path.basename(dest)} ...')
    try:
        urllib.request.urlretrieve(url, dest)
        print(f'  [完成] {os.path.basename(dest)}')
    except Exception as e:
        print(f'  [错误] 下载 {os.path.basename(dest)} 失败: {e}', file=sys.stderr)
        sys.exit(1)


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    pkg_dir = os.path.dirname(script_dir)          # 功能包根目录
    model_dir = os.path.join(pkg_dir, 'models')
    os.makedirs(model_dir, exist_ok=True)

    print(f'模型保存目录: {model_dir}\n')
    for name in MODELS:
        url = BASE_URL + name
        dest = os.path.join(model_dir, name)
        download(url, dest)

    print('\n✅ 所有模型文件下载完成！')
    print('请重新编译功能包: colcon build --packages-select qrcode_detector')


if __name__ == '__main__':
    main()
