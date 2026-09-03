"""Hand-eye calibration (eye-in-hand) HTTP API backed by vision_core solver.

Robot poses are entered manually via the web form (no direct robot communication).
AprilTag poses come from the dashboard node's TransformStamped subscriber.
"""

from __future__ import annotations

import json
import math
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
from fastapi.responses import FileResponse, JSONResponse
from fastapi.responses import StreamingResponse

from vision_core import (
    HAND_EYE_ALGORITHMS,
    closed_loop_errors,
    homogeneous_matrix,
    rotation_angle,
    solve_hand_eye,
    should_collect_sample,
    write_handeye_yaml,
    xarm_pose_to_transform,
)

try:
    from apriltag import apriltag as AprilTagDetector
except (ImportError, OSError):
    AprilTagDetector = None


RUNNING_PHASES = {'solving'}

# Minimum sample count for the solver frontend gate.
MIN_SAMPLES = 4


class HandEyeCalibrationStore:
    """Stateful store for a single ongoing hand-eye calibration session."""

    def __init__(self, node):
        self._node = node
        self._root = Path(node.handeye_calibration_dir).expanduser().resolve()
        self._history_dir = self._root / 'history'
        self._root.mkdir(parents=True, exist_ok=True)
        self._history_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._session_id = ''
        self._session_dir: Path | None = None
        self._samples: list[dict] = []
        self._detector = AprilTagDetector('tag36h11') if AprilTagDetector else None
        self._state = self._empty_state()

    @staticmethod
    def _empty_state() -> dict:
        return {
            'phase': 'idle',
            'message': '',
            'result': None,
        }

    def state(self) -> dict:
        with self._lock:
            return {
                **self._state,
                'session_id': self._session_id,
                'samples': list(self._samples),
                'diversity': self._diversity(),
                'history': self.history(),
                'target_frame': self._latest_target_frame(),
            }

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------
    def new_session(self) -> dict:
        with self._lock:
            self._session_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
            self._session_id += f'-{uuid.uuid4().hex[:6]}'
            self._session_dir = self._root / 'sessions' / self._session_id
            self._session_dir.mkdir(parents=True, exist_ok=True)
            self._samples = []
            self._state = self._empty_state()
            return self.state()

    # ------------------------------------------------------------------
    # Sample capture
    # ------------------------------------------------------------------
    def capture(self, robot_pose: dict) -> dict:
        """Capture a synchronized sample: photo + tag transform + robot pose.

        *robot_pose* keys: x_mm, y_mm, z_mm, roll_deg, pitch_deg, yaw_deg.
        """
        with self._lock:
            if self._session_dir is None:
                self.new_session()
            try:
                values = [
                    float(robot_pose['x_mm']), float(robot_pose['y_mm']),
                    float(robot_pose['z_mm']),
                    math.radians(float(robot_pose['roll_deg'])),
                    math.radians(float(robot_pose['pitch_deg'])),
                    math.radians(float(robot_pose['yaw_deg'])),
                ]
                robot_matrix = xarm_pose_to_transform([
                    values[0], values[1], values[2],
                    values[3], values[4], values[5],
                ])
            except (KeyError, ValueError, TypeError) as exc:
                raise RuntimeError(f'机械臂位姿格式错误：{exc}')

            tag_info = self._node.get_latest_tag_transform()
            if tag_info is None:
                raise RuntimeError(
                    '尚未接收到 AprilTag 位姿数据，请确认标签位于视野内且流水线正在运行'
                )
            target_matrix = np.asarray(tag_info['matrix_4x4'], dtype=np.float64)
            assert target_matrix.shape == (4, 4)

            # Sample diversity check vs previous sample.
            trans_delta_m, rot_delta_deg = 0.0, 0.0
            if self._samples:
                prev = self._samples[-1]
                prev_robot = np.asarray(prev['robot_matrix'], dtype=np.float64)
                prev_target = np.asarray(prev['target_matrix'], dtype=np.float64)
                now = time.monotonic()
                collect, trans_delta_m, rot_delta_deg = should_collect_sample(
                    robot_matrix, target_matrix,
                    now, now,
                    sync_tolerance_s=1e9,  # disable sync check for manual entry
                    min_translation_m=0.001,
                    min_rotation_deg=1.0,
                    min_target_motion_m=0.001,
                    previous_robot=prev_robot,
                    previous_target=prev_target,
                )
                if not collect:
                    raise RuntimeError(
                        f'与上一个样本位姿过于接近（平移 {trans_delta_m*1000:.1f} mm，'
                        f'旋转 {rot_delta_deg:.1f}°），请移动机械臂后再次采集'
                    )

            # Capture annotated image for this sample.
            self._node.mark_image_request()
            jpeg = self._node.get_latest_calibration_image()
            if jpeg is None:
                raise RuntimeError('实时画面尚未就绪，请先打开实时流后重试')
            assert self._session_dir is not None
            filename = f'sample_{len(self._samples) + 1:03d}.jpg'
            path = self._session_dir / filename
            annotated, detections = self._annotate(jpeg)
            path.write_bytes(annotated)

            sample = {
                'id': filename,
                'filename': filename,
                'created_at': datetime.now(timezone.utc).isoformat(),
                'robot_pose': {
                    'x_mm': float(values[0]), 'y_mm': float(values[1]),
                    'z_mm': float(values[2]),
                    'roll_deg': float(math.degrees(values[3])),
                    'pitch_deg': float(math.degrees(values[4])),
                    'yaw_deg': float(math.degrees(values[5])),
                },
                'robot_matrix': [[float(v) for v in row] for row in robot_matrix.tolist()],
                'target_frame': tag_info.get('child_frame_id', ''),
                'target_matrix': [[float(v) for v in row] for row in target_matrix.tolist()],
                'target_xyz_m': list(tag_info['translation_xyz_m']),
                'tag_detections': detections,
                'last_robot_translation_mm': round(trans_delta_m * 1000.0, 2),
                'last_robot_rotation_deg': round(rot_delta_deg, 2),
                'image_filename': filename,
            }
            self._samples.append(sample)
            return sample

    def preview(self) -> bytes | None:
        self._node.mark_image_request()
        jpeg = self._node.get_latest_image()
        if jpeg is None:
            return None
        return self._annotate(jpeg)[0]

    def _annotate(self, jpeg: bytes) -> tuple[bytes, int]:
        image = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            return jpeg, 0
        detections = [] if self._detector is None else self._detector.detect(
            cv2.cvtColor(image, cv2.COLOR_BGR2GRAY))
        for detection in detections:
            corners = np.asarray(
                detection['lb-rb-rt-lt'], dtype=np.int32,
            ).reshape(-1, 1, 2)
            cv2.polylines(image, [corners], True, (120, 180, 255), 2)
            center = tuple(np.asarray(detection['center'], dtype=np.int32))
            cv2.putText(image, str(detection['id']), center, cv2.FONT_HERSHEY_SIMPLEX,
                        0.5, (255, 255, 255), 1, cv2.LINE_AA)
        ok, encoded = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return (encoded.tobytes() if ok else jpeg), len(detections)

    def delete_sample(self, filename: str) -> bool:
        with self._lock:
            if self._session_dir is None or Path(filename).name != filename:
                return False
            path = self._session_dir / filename
            if not path.is_file():
                return False
            path.unlink()
            self._samples = [s for s in self._samples if s['filename'] != filename]
            return True

    def sample_path(self, filename: str) -> Path | None:
        with self._lock:
            if self._session_dir is None or Path(filename).name != filename:
                return None
            path = self._session_dir / filename
            return path if path.is_file() else None

    # ------------------------------------------------------------------
    # Diversity indicators
    # ------------------------------------------------------------------
    def _diversity(self) -> dict[str, float]:
        if not self._samples:
            return {
                'count': 0,
                'translation_span_mm': 0.0,
                'rotation_span_deg': 0.0,
                'consecutive_rotation_deg': 0.0,
            }
        robots = [np.asarray(s['robot_matrix'], dtype=np.float64) for s in self._samples]
        translations = np.array([m[:3, 3] for m in robots])
        rot_span = 0.0
        if len(robots) >= 2:
            ref = robots[0][:3, :3]
            angles = []
            for m in robots[1:]:
                rel = ref.T @ m[:3, :3]
                cosine = np.clip((np.trace(rel) - 1.0) / 2.0, -1.0, 1.0)
                angles.append(math.degrees(math.acos(cosine)))
            rot_span = max(angles)
        consec = 0.0
        if len(robots) >= 2:
            consec = max(
                math.degrees(rotation_angle(prev[:3, :3].T @ cur[:3, :3]))
                for prev, cur in zip(robots, robots[1:])
            )
        t_span = float(np.max(np.ptp(translations, axis=0)))
        return {
            'count': len(self._samples),
            'translation_span_mm': round(t_span * 1000.0, 1),
            'rotation_span_deg': round(rot_span, 1),
            'consecutive_rotation_deg': round(consec, 1),
        }

    def _latest_target_frame(self) -> str:
        tag = self._node.get_latest_tag_transform()
        return (tag or {}).get('child_frame_id', '') or ''

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------
    def history(self) -> list[dict]:
        records = []
        for path in sorted(self._history_dir.glob('*.json'), reverse=True)[:30]:
            try:
                records.append(json.loads(path.read_text(encoding='utf-8')))
            except (OSError, json.JSONDecodeError):
                continue
        return records

    # ------------------------------------------------------------------
    # Calibration solving
    # ------------------------------------------------------------------
    def start(self, payload: dict) -> dict:
        with self._lock:
            if self._state['phase'] in RUNNING_PHASES:
                raise RuntimeError('已有标定任务正在运行')
            if len(self._samples) < MIN_SAMPLES:
                raise RuntimeError(
                    f'至少需要 {MIN_SAMPLES} 组姿态样本，当前只有 {len(self._samples)} 组'
                )
            algorithm = str(payload.get('algorithm') or 'tsai')
            if algorithm not in HAND_EYE_ALGORITHMS:
                raise RuntimeError(
                    f'未知算法 {algorithm}，可选: {", ".join(HAND_EYE_ALGORITHMS)}'
                )
            rows = []
            for sample in self._samples:
                r = np.asarray(sample['robot_matrix'], dtype=np.float64)
                t = np.asarray(sample['target_matrix'], dtype=np.float64)
                rows.append((
                    r[:3, :3].copy(),
                    r[:3, 3:].copy(),
                    t[:3, :3].copy(),
                    t[:3, 3:].copy(),
                ))
            self._state.update(phase='solving', message='正在求解手眼标定矩阵…')
            thread = threading.Thread(
                target=self._solve_worker,
                args=(rows, algorithm, payload),
                daemon=True,
            )
            thread.start()
            return self.state()

    def _solve_worker(self, rows, algorithm, payload) -> None:
        try:
            result_r, result_t = solve_hand_eye(rows, algorithm)
        except (ValueError, RuntimeError) as exc:
            with self._lock:
                self._state.update(phase='failed', message=f'求解失败：{exc}')
            return

        camera_to_gripper = homogeneous_matrix(result_r, result_t)
        gripper_to_camera = np.linalg.inv(camera_to_gripper)
        errors = closed_loop_errors(rows, camera_to_gripper)

        mean_trans = float(np.mean([e['translation_m'] for e in errors]))
        max_trans = float(np.max([e['translation_m'] for e in errors]))
        mean_rot = float(np.mean([e['rotation_deg'] for e in errors]))
        max_rot = float(np.max([e['rotation_deg'] for e in errors]))

        max_trans_thresh = float(payload.get('max_closed_loop_translation_m') or 0.0)
        max_rot_thresh = float(payload.get('max_closed_loop_rotation_deg') or 0.0)
        if max_trans_thresh > 0 and max_trans > max_trans_thresh:
            with self._lock:
                self._state.update(
                    phase='failed',
                    message=(
                        f'闭环平移误差 {max_trans*1000:.2f} mm 超过阈值 '
                        f'{max_trans_thresh*1000:.2f} mm'
                    ),
                )
            return
        if max_rot_thresh > 0 and max_rot > max_rot_thresh:
            with self._lock:
                self._state.update(
                    phase='failed',
                    message=(
                        f'闭环旋转误差 {max_rot:.3f}° 超过阈值 {max_rot_thresh:.3f}°'
                    ),
                )
            return

        yaml_filename = f'{self._session_id}.yaml'
        yaml_path = self._history_dir / yaml_filename
        preview_filename = f'{self._session_id}_preview.jpg'
        preview_path = self._history_dir / preview_filename

        try:
            write_handeye_yaml(
                str(yaml_path),
                algorithm=algorithm,
                result_r=result_r,
                result_t=result_t,
                camera_to_gripper=camera_to_gripper,
                gripper_to_camera=gripper_to_camera,
                sample_count=len(rows),
                errors=errors,
                base_frame=payload.get('base_frame', 'base_link'),
                gripper_frame=payload.get('gripper_frame', 'tool0'),
                camera_frame=payload.get('camera_frame', 'camera_optical_frame'),
                target_frame=payload.get('target_frame', 'apriltag_board'),
            )
        except RuntimeError as exc:
            with self._lock:
                self._state.update(phase='failed', message=str(exc))
            return

        if self._samples and self._session_dir:
            last = self._samples[-1]
            src = self._session_dir / last['filename']
            if src.is_file():
                try:
                    img = cv2.imread(str(src), cv2.IMREAD_COLOR)
                    if img is not None:
                        cv2.imwrite(str(preview_path), img)
                except cv2.error:
                    pass

        record = {
            'id': self._session_id,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'parameters': payload,
            'samples_used': len(rows),
            'algorithm_used': algorithm,
            'mean_translation_error_mm': round(mean_trans * 1000.0, 3),
            'max_translation_error_mm': round(max_trans * 1000.0, 3),
            'mean_rotation_error_deg': round(mean_rot, 4),
            'max_rotation_error_deg': round(max_rot, 4),
            'camera_to_gripper_matrix': [
                float(v) for v in camera_to_gripper.reshape(-1)
            ],
            'gripper_to_camera_matrix': [
                float(v) for v in gripper_to_camera.reshape(-1)
            ],
            'translation_xyz_mm': [
                round(float(result_t[i, 0]) * 1000.0, 3) for i in range(3)
            ],
            'yaml_filename': yaml_filename,
            'preview_filename': preview_filename if preview_path.is_file() else '',
        }
        (self._history_dir / f'{self._session_id}.json').write_text(
            json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8'
        )
        with self._lock:
            self._state.update(phase='done', message='手眼标定完成', result=record)

    # ------------------------------------------------------------------
    # Apply / download
    # ------------------------------------------------------------------
    def apply(self, payload: dict) -> dict:
        """Copy stored hand-eye YAML to the active path and hot-reload TF."""
        record_id = str(payload.get('id') or '').strip()
        if not record_id:
            raise RuntimeError('缺少标定记录 ID')
        record_path = self._history_dir / f'{record_id}.json'
        if not record_path.is_file():
            raise RuntimeError(f'标定记录不存在：{record_id}')
        try:
            record = json.loads(record_path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f'标定记录读取失败：{exc}') from exc
        yaml_path = self._history_dir / str(record.get('yaml_filename') or '')
        if not record.get('yaml_filename') or not yaml_path.is_file():
            raise RuntimeError('标定结果 YAML 文件不存在')

        target_file = self._node.handeye_calibration_file
        if not target_file:
            raise RuntimeError(
                '未配置 handeye_calibration_file 参数，无法应用手眼标定结果。'
                '请在启动参数中指定 handeye_calibration_file 路径。'
            )
        target_path = Path(target_file).expanduser().resolve()
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(yaml_path.read_bytes())

        reload_message = ''
        client = getattr(self._node, 'handeye_reload_client', None)
        if client is not None and client.service_is_ready():
            try:
                from apriltag_pose_reader_interfaces.srv import ReloadCalibration
                req = ReloadCalibration.Request()
                req.calibration_file = str(target_path)
                future = client.call_async(req)
                deadline = time.monotonic() + 3.0
                while not future.done() and time.monotonic() < deadline:
                    time.sleep(0.05)
                if future.done():
                    resp = future.result()
                    reload_message = (
                        f'；TF 广播器重载{"成功" if resp.success else "失败"}'
                        f'：{resp.message}'
                    )
                else:
                    reload_message = '；TF 广播器重载超时'
            except Exception as exc:  # noqa: BLE001 - best-effort only
                reload_message = f'；TF 广播器重载跳过：{exc}'

        return {
            'success': True,
            'message': f'手眼标定结果已写入 {target_path}{reload_message}',
            'target_path': str(target_path),
        }


def register_handeye_routes(app, dashboard_runtime):
    """Register stateful hand-eye calibration HTTP routes."""
    store_holder: dict[str, HandEyeCalibrationStore] = {}

    def store() -> HandEyeCalibrationStore:
        node = dashboard_runtime.get_node()
        existing = store_holder.get('store')
        if existing is None or existing._node is not node:
            existing = HandEyeCalibrationStore(node)
            store_holder['store'] = existing
        return existing

    @app.get('/api/handeye')
    async def handeye_state():
        s = store()
        result = s.state()
        result['latest_tag_available'] = (
            s._node.get_latest_tag_transform() is not None  # noqa: SLF001
        )
        return JSONResponse(result)

    @app.get('/api/handeye/preview')
    async def handeye_preview():
        preview = store().preview()
        if preview is None:
            return JSONResponse({'error': 'No image available'}, status_code=404)
        return StreamingResponse(iter([preview]), media_type='image/jpeg')

    @app.post('/api/handeye/session')
    async def handeye_new_session():
        return JSONResponse(store().new_session())

    @app.post('/api/handeye/samples')
    async def handeye_capture_sample(payload: dict):
        required = ('x_mm', 'y_mm', 'z_mm', 'roll_deg', 'pitch_deg', 'yaw_deg')
        if not payload or any(k not in payload for k in required):
            return JSONResponse({'error': '机械臂位姿字段不完整'}, status_code=422)
        try:
            return JSONResponse(store().capture(payload))
        except RuntimeError as exc:
            return JSONResponse({'error': str(exc)}, status_code=409)

    @app.get('/api/handeye/samples/{filename}')
    async def handeye_sample_file(filename: str):
        path = store().sample_path(filename)
        if path is None:
            return JSONResponse({'error': 'Sample not found'}, status_code=404)
        return FileResponse(path, media_type='image/jpeg')

    @app.delete('/api/handeye/samples/{filename}')
    async def handeye_sample_delete(filename: str):
        if not store().delete_sample(filename):
            return JSONResponse({'error': 'Sample not found'}, status_code=404)
        return JSONResponse({'success': True})

    @app.post('/api/handeye/start')
    async def handeye_start(payload: dict):
        try:
            return JSONResponse(store().start(payload or {}))
        except (RuntimeError, ValueError) as exc:
            return JSONResponse({'error': str(exc)}, status_code=409)

    @app.post('/api/handeye/apply')
    async def handeye_apply(payload: dict):
        try:
            return JSONResponse(store().apply(payload or {}))
        except RuntimeError as exc:
            return JSONResponse({'error': str(exc)}, status_code=409)

    @app.get('/api/handeye/history/{filename}')
    async def handeye_history_file(filename: str):
        safe_name = Path(filename).name
        path = store()._history_dir / safe_name  # noqa: SLF001
        if not path.is_file() or path.suffix not in {'.yaml', '.jpg', '.json'}:
            return JSONResponse({'error': 'File not found'}, status_code=404)
        if path.suffix == '.yaml':
            media_type = 'application/x-yaml'
        elif path.suffix == '.jpg':
            media_type = 'image/jpeg'
        else:
            media_type = 'application/json'
        return FileResponse(path, media_type=media_type, filename=path.name)

    return (lambda: None)
