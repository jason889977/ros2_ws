"""Image capture utility for AprilGrid calibration.

This utility can either:
  - capture frames from a camera device using OpenCV if a camera index/device is provided
  - or simply enumerate image files in a folder for batch calibration

This is intended as a bridge between live Basler camera streams and the offline
AprilGrid calibration workflow demanded by the project.
"""

from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path

import cv2


def capture_from_camera(camera_index: int, output_dir: str, prefix: str = 'calib', max_frames: int = 20) -> list[str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        raise RuntimeError(f'Unable to open camera index {camera_index}')

    saved: list[str] = []
    frame_idx = 0
    while frame_idx < max_frames:
        ok, frame = cap.read()
        if not ok:
            break
        image_name = output_path / f'{prefix}_{frame_idx:03d}.png'
        cv2.imwrite(str(image_name), frame)
        saved.append(str(image_name))
        frame_idx += 1

    cap.release()
    return saved


def collect_images(input_dir: str, output_dir: str, prefix: str = 'calib_') -> list[str]:
    src_dir = Path(input_dir)
    dst_dir = Path(output_dir)
    dst_dir.mkdir(parents=True, exist_ok=True)

    saved: list[str] = []
    for index, image_path in enumerate(sorted(src_dir.iterdir())):
        if image_path.suffix.lower() not in {'.png', '.jpg', '.jpeg', '.bmp'}:
            continue
        target = dst_dir / f'{prefix}{index:03d}{image_path.suffix}'
        shutil.copy2(str(image_path), str(target))
        saved.append(str(target))
    return saved


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Collect calibration images for the AprilGrid board.')
    parser.add_argument('--camera-index', type=int, default=-1, help='OpenCV camera index; if omitted, the script assumes input_dir is used.')
    parser.add_argument('--input-dir', type=str, default='', help='Folder containing calibration images for batch collection.')
    parser.add_argument('--output-dir', type=str, default='calibration_images', help='Folder where calibration images will be written.')
    parser.add_argument('--prefix', type=str, default='calib', help='Filename prefix for saved images.')
    parser.add_argument('--max-frames', type=int, default=20, help='Maximum number of frames to capture from a live camera.')
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.camera_index >= 0:
        saved = capture_from_camera(args.camera_index, args.output_dir, args.prefix, args.max_frames)
        print('Captured images:')
        for item in saved:
            print(item)
        return 0

    if args.input_dir:
        saved = collect_images(args.input_dir, args.output_dir, args.prefix)
        print('Collected images:')
        for item in saved:
            print(item)
        return 0

    raise RuntimeError('Provide either --camera-index or --input-dir for calibration image collection.')


if __name__ == '__main__':
    raise SystemExit(main())
