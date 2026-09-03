"""Image collection utilities for the web-driven AprilGrid calibration."""

from __future__ import annotations

from pathlib import Path
import shutil


def collect_images(input_dir: str, output_dir: str, prefix: str = 'calib_') -> list[str]:
    src_dir = Path(input_dir)
    dst_dir = Path(output_dir)
    dst_dir.mkdir(parents=True, exist_ok=True)

    saved: list[str] = []
    for index, image_path in enumerate(sorted(src_dir.iterdir())):
        if not image_path.is_file():
            continue
        if image_path.suffix.lower() not in {'.png', '.jpg', '.jpeg', '.bmp'}:
            continue
        target = dst_dir / f'{prefix}{index:03d}{image_path.suffix}'
        shutil.copy2(str(image_path), str(target))
        saved.append(str(target))
    return saved
