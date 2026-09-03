"""Apply web calibration results to the camera's camera_info file.

The camera config YAML (e.g. ``deploy/basler_camera/config/aca2500_*.yaml``)
declares ``camera_info_url`` (``package://`` or ``file://``).  Applying a
calibration result rewrites that target YAML with the fresh intrinsics so the
pipeline picks them up after the next restart.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml


def _load_yaml(path: Path) -> dict:
    with Path(path).open('r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    return data or {}


def resolve_camera_info_path(url: str) -> Path:
    """Resolve a ``package://``/``file://``/plain-path camera_info URL."""
    url = str(url).strip()
    if url.startswith('package://'):
        rest = url[len('package://'):]
        package, _, relative = rest.partition('/')
        if not package or not relative:
            raise RuntimeError(f'非法的 camera_info_url：{url}')
        from ament_index_python.packages import get_package_share_directory
        return Path(get_package_share_directory(package)) / relative
    if url.startswith('file://'):
        return Path(url[len('file://'):])
    return Path(url)


def resolve_camera_info_url(camera_config: str) -> Path:
    """Resolve the camera_info file declared by the camera config YAML."""
    config_path = Path(camera_config).expanduser().resolve()
    if not config_path.is_file():
        raise RuntimeError(f'相机配置文件不存在：{config_path}')
    params = (_load_yaml(config_path).get('/**') or {}).get('ros__parameters') or {}
    url = str(params.get('camera_info_url') or '').strip()
    if not url:
        raise RuntimeError(f'相机配置未声明 camera_info_url：{config_path}')
    return resolve_camera_info_path(url)


def _sync_to_source(install_path: Path, content: str) -> str | None:
    """Sync written content back to the src/ copy to survive colcon rebuilds.

    Install path pattern: <ws>/install/<pkg>/share/<pkg>/<rest>
    Source path pattern:  <ws>/src/<pkg>/<rest>
    """
    parts = install_path.resolve().parts
    for i, part in enumerate(parts):
        if part == 'install' and i + 2 < len(parts):
            pkg = parts[i + 1]
            # Skip the 'share/<pkg>' segment in the install tree
            rest_start = i + 4 if parts[i + 2] == 'share' else i + 2
            if rest_start >= len(parts):
                break
            src_path = Path(*parts[:i], 'src', pkg, *parts[rest_start:])
            if src_path.is_file():
                src_path.write_text(content, encoding='utf-8')
                return str(src_path)
            break
    return None


def apply_camera_intrinsics(camera_config: str, result_yaml: str | Path) -> dict:
    """Write calibrated intrinsics into the camera's camera_info YAML."""
    target = resolve_camera_info_url(camera_config)
    if not target.is_file():
        raise RuntimeError(f'相机内参文件不存在：{target}')

    result = _load_yaml(Path(result_yaml))
    matrix_data = [float(v) for v in ((result.get('camera_matrix') or {}).get('data') or [])]
    dist_data = [float(v) for v in ((result.get('distortion_coefficients') or {}).get('data') or [])]
    if len(matrix_data) != 9:
        raise RuntimeError('标定结果缺少有效的 camera_matrix')
    if not dist_data:
        raise RuntimeError('标定结果缺少有效的 distortion_coefficients')
    width = int(result.get('image_width') or 0)
    height = int(result.get('image_height') or 0)
    if width <= 0 or height <= 0:
        raise RuntimeError('标定结果缺少有效的图像尺寸')

    existing = _load_yaml(target)
    mapping = {
        'image_width': width,
        'image_height': height,
        'camera_name': str(existing.get('camera_name') or 'camera'),
        'camera_matrix': {'rows': 3, 'cols': 3, 'data': matrix_data},
        'distortion_model': str(result.get('distortion_model') or 'plumb_bob'),
        'distortion_coefficients': {
            'rows': 1, 'cols': len(dist_data), 'data': dist_data,
        },
        'rectification_matrix': {
            'rows': 3, 'cols': 3,
            'data': [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0],
        },
        'projection_matrix': {
            'rows': 3, 'cols': 4,
            'data': [value for row in range(3)
                     for value in [*matrix_data[row * 3:row * 3 + 3], 0.0]],
        },
    }

    backup = target.with_suffix(target.suffix + '.bak')
    backup.write_bytes(target.read_bytes())
    content = yaml.safe_dump(mapping, sort_keys=False)
    tmp = target.with_suffix(target.suffix + '.tmp')
    tmp.write_text(content, encoding='utf-8')
    os.replace(tmp, target)

    synced = _sync_to_source(target, content)

    return {
        'target': str(target),
        'backup': str(backup),
        'source_synced': synced,
        'message': f'内参已写入 {target}，重启流水线容器后生效',
    }
