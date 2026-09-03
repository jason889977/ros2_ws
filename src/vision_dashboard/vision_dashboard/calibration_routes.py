"""Camera-calibration HTTP API backed by the AprilGrid ROS action."""

from __future__ import annotations

import json
import subprocess
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
from fastapi.responses import FileResponse, JSONResponse
from fastapi.responses import StreamingResponse
from vision_core import terminate_process

try:
    from apriltag import apriltag as AprilTagDetector
except (ImportError, OSError):
    AprilTagDetector = None


class CalibrationStore:
    """Keep short-lived capture sessions and persisted calibration results."""

    def __init__(self, node):
        self._node = node
        self._root = Path(node.calibration_dir).expanduser().resolve()
        self._history_dir = self._root / 'history'
        self._root.mkdir(parents=True, exist_ok=True)
        self._history_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._session_id = ''
        self._session_dir: Path | None = None
        self._captures: list[dict] = []
        self._detector = AprilTagDetector('tag36h11') if AprilTagDetector else None
        self._goal_handle = None
        self._state = self._empty_state()

    @staticmethod
    def _empty_state() -> dict:
        return {
            'phase': 'idle', 'images_processed': 0, 'last_detection_count': 0,
            'message': '', 'result': None,
        }

    def state(self) -> dict:
        with self._lock:
            return {**self._state, 'session_id': self._session_id,
                    'captures': list(self._captures), 'coverage': self._coverage(),
                    'history': self.history()}

    def _coverage(self) -> dict[str, int]:
        samples = [item['coverage'] for item in self._captures if item.get('coverage')]
        if not samples:
            return {'x': 0, 'y': 0, 'size': 0, 'skew': 0}
        def spread(key: str, scale: float) -> int:
            values = [sample[key] for sample in samples]
            return min(100, round((max(values) - min(values)) / scale * 100))
        return {
            'x': spread('x', 0.65), 'y': spread('y', 0.65),
            'size': spread('size', 0.30), 'skew': min(100, round(
                max(sample['skew'] for sample in samples) * 200)),
        }

    def history(self) -> list[dict]:
        records = []
        for path in sorted(self._history_dir.glob('*.json'), reverse=True)[:30]:
            try:
                records.append(json.loads(path.read_text(encoding='utf-8')))
            except (OSError, json.JSONDecodeError):
                continue
        return records

    def new_session(self) -> dict:
        with self._lock:
            self._session_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
            self._session_id += f'-{uuid.uuid4().hex[:6]}'
            self._session_dir = self._root / 'sessions' / self._session_id
            self._session_dir.mkdir(parents=True, exist_ok=True)
            self._captures = []
            self._goal_handle = None
            self._state = self._empty_state()
            return self.state()

    def capture(self) -> dict:
        with self._lock:
            if self._session_dir is None:
                self.new_session()
            self._node.mark_image_request()
            jpeg = self._node.get_latest_calibration_image()
            if jpeg is None:
                raise RuntimeError('实时画面尚未就绪，请先打开实时流后重试')
            assert self._session_dir is not None
            filename = f'calib_{len(self._captures) + 1:03d}.jpg'
            path = self._session_dir / filename
            annotated, detections, coverage = self._annotate(jpeg)
            path.write_bytes(annotated)
            capture = {'id': filename, 'filename': filename,
                       'created_at': datetime.now(timezone.utc).isoformat(),
                       'detections': detections, 'coverage': coverage}
            self._captures.append(capture)
            return capture

    def preview(self) -> bytes | None:
        self._node.mark_image_request()
        jpeg = self._node.get_latest_image()
        if jpeg is None:
            return None
        return self._annotate(jpeg)[0]

    def _annotate(self, jpeg: bytes) -> tuple[bytes, int, dict | None]:
        image = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            return jpeg, 0, None
        detections = [] if self._detector is None else self._detector.detect(
            cv2.cvtColor(image, cv2.COLOR_BGR2GRAY))
        coverage_samples = []
        height, width = image.shape[:2]
        for detection in detections:
            corners = np.asarray(detection['lb-rb-rt-lt'], dtype=np.int32).reshape(-1, 1, 2)
            cv2.polylines(image, [corners], True, (78, 232, 215), 2)
            center = tuple(np.asarray(detection['center'], dtype=np.int32))
            cv2.putText(image, str(detection['id']), center, cv2.FONT_HERSHEY_SIMPLEX,
                        0.5, (255, 255, 255), 1, cv2.LINE_AA)
            points = corners.reshape(4, 2).astype(np.float64)
            edge_lengths = np.linalg.norm(points - np.roll(points, -1, axis=0), axis=1)
            coverage_samples.append({
                'x': float(detection['center'][0]) / width,
                'y': float(detection['center'][1]) / height,
                'size': float(np.mean(edge_lengths)) / max(width, height),
                'skew': float(abs(edge_lengths[0] - edge_lengths[2]) +
                              abs(edge_lengths[1] - edge_lengths[3])) / max(sum(edge_lengths), 1.0),
            })
        ok, encoded = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 85])
        coverage = None if not coverage_samples else {
            key: float(np.mean([sample[key] for sample in coverage_samples]))
            for key in ('x', 'y', 'size', 'skew')
        }
        return (encoded.tobytes() if ok else jpeg), len(detections), coverage

    def delete_capture(self, filename: str) -> bool:
        with self._lock:
            if self._session_dir is None or Path(filename).name != filename:
                return False
            path = self._session_dir / filename
            if not path.is_file():
                return False
            path.unlink()
            self._captures = [item for item in self._captures if item['filename'] != filename]
            return True

    def capture_path(self, filename: str) -> Path | None:
        with self._lock:
            if self._session_dir is None or Path(filename).name != filename:
                return None
            path = self._session_dir / filename
            return path if path.is_file() else None

    def start(self, payload: dict) -> dict:
        from apriltag_pose_reader_interfaces.action import CalibrateCamera

        with self._lock:
            if self._state['phase'] in {'collecting', 'detecting', 'calibrating'}:
                raise RuntimeError('已有标定任务正在运行')
            if self._session_dir is None or not self._captures:
                raise RuntimeError('请至少采集一张 AprilGrid 图像')
            if len(self._captures) < 3:
                raise RuntimeError(
                    f'至少需要 3 张标定图像，当前只有 {len(self._captures)} 张'
                )
            # Note: self._captures[i].detections is the count of single tags found
            # by the optional Python apriltag library used only for preview
            # overlays. The actual Action server uses OpenCV's AprilGrid corner
            # detector which operates on the raw saved images independently, so
            # we do NOT gate the backend on that preview-only count.
            client = self._node.calibration_action_client
            if client is None or not client.server_is_ready():
                raise RuntimeError('AprilGrid 标定服务不可用')
            goal = CalibrateCamera.Goal()
            goal.input_dir = str(self._session_dir)
            goal.output_dir = str(self._history_dir)
            goal.rows = int(payload['rows'])
            goal.cols = int(payload['cols'])
            goal.tag_size_m = float(payload['tag_size_m'])
            goal.tag_spacing_m = float(payload['tag_spacing_m'])
            goal.tag_family = str(payload['tag_family'])
            goal.output_name = f'{self._session_id}.yaml'
            goal.max_reprojection_error = float(payload['max_reprojection_error'])
            goal.timeout_s = float(payload['timeout_s'])
            self._state = {**self._empty_state(), 'phase': 'queued',
                           'message': '等待标定服务接收任务'}
            client.send_goal_async(goal, feedback_callback=self._on_feedback).add_done_callback(
                lambda future: self._on_goal_response(future, payload))
            return self.state()

    def _on_goal_response(self, future, payload: dict) -> None:
        try:
            goal_handle = future.result()
        except Exception as error:
            with self._lock:
                self._state.update(phase='failed', message=f'提交标定失败：{error}')
            return
        with self._lock:
            if not goal_handle.accepted:
                self._state.update(phase='failed', message='标定服务拒绝了任务')
                return
            self._goal_handle = goal_handle
            self._state.update(phase='collecting', message='正在准备标定图像')
        goal_handle.get_result_async().add_done_callback(
            lambda result_future: self._on_result(result_future, payload))

    def _on_feedback(self, feedback_message) -> None:
        feedback = feedback_message.feedback
        with self._lock:
            self._state.update(phase=feedback.phase,
                               images_processed=int(feedback.images_processed),
                               last_detection_count=int(feedback.last_detection_count),
                               message=f'正在{feedback.phase}')

    def _on_result(self, future, payload: dict) -> None:
        try:
            result = future.result().result
        except Exception as error:
            with self._lock:
                self._state.update(phase='failed', message=f'读取标定结果失败：{error}')
            return
        with self._lock:
            if not result.success:
                self._state.update(phase='failed', message=result.message)
                return
            yaml_path = Path(result.output_yaml)
            preview_filename = f'{self._session_id}_undistorted.jpg'
            preview_path = self._history_dir / preview_filename
            source_path = self._session_dir / self._captures[-1]['filename']
            image = cv2.imread(str(source_path), cv2.IMREAD_COLOR)
            if image is not None:
                camera_matrix = np.asarray(result.camera_matrix, dtype=np.float64).reshape(3, 3)
                distortion = np.asarray(result.distortion_coefficients, dtype=np.float64)
                undistorted = cv2.undistort(image, camera_matrix, distortion)
                cv2.imwrite(str(preview_path), undistorted)
            record = {
                'id': self._session_id, 'created_at': datetime.now(timezone.utc).isoformat(),
                'parameters': payload, 'images_used': int(result.images_used),
                'reprojection_error': float(result.reprojection_error),
                'image_width': int(result.image_width), 'image_height': int(result.image_height),
                'camera_matrix': list(result.camera_matrix),
                'distortion_coefficients': list(result.distortion_coefficients),
                'yaml_filename': yaml_path.name,
                'undistorted_filename': preview_filename if preview_path.is_file() else '',
            }
            (self._history_dir / f'{self._session_id}.json').write_text(
                json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
            self._state.update(phase='done', message=result.message, result=record)
            self._goal_handle = None

    def cancel(self) -> dict:
        with self._lock:
            if self._goal_handle is None:
                raise RuntimeError('没有可取消的标定任务')
            self._goal_handle.cancel_goal_async()
            self._state.update(phase='cancelling', message='正在取消标定任务')
            return self.state()

    def apply(self, payload: dict) -> dict:
        """Write a stored calibration result into the camera's camera_info file."""
        from vision_dashboard.apply_intrinsics import apply_camera_intrinsics

        record_id = str(payload.get('id') or '').strip()
        if not record_id:
            raise RuntimeError('缺少标定记录 ID')
        record_path = self._history_dir / f'{record_id}.json'
        if not record_path.is_file():
            raise RuntimeError(f'标定记录不存在：{record_id}')
        try:
            record = json.loads(record_path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeError(f'标定记录读取失败：{error}') from error
        yaml_path = self._history_dir / str(record.get('yaml_filename') or '')
        if not record.get('yaml_filename') or not yaml_path.is_file():
            raise RuntimeError('标定结果 YAML 文件不存在')
        if not self._node.camera_config:
            raise RuntimeError('未配置相机参数文件（camera_config），无法应用内参')
        return apply_camera_intrinsics(self._node.camera_config, yaml_path)


class CalibrationServiceManager:
    """Start and stop only the calibration server owned by this dashboard."""

    def __init__(self, node):
        self._node = node
        self._lock = threading.RLock()
        self._process: subprocess.Popen[str] | None = None

    def shutdown(self) -> None:
        """Stop the calibration server started by this dashboard."""
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                terminate_process(self._process)
            self._process = None

    def state(self) -> dict:
        with self._lock:
            managed_running = self._process is not None and self._process.poll() is None
            available = bool(
                self._node.calibration_action_client
                and self._node.calibration_action_client.server_is_ready())
            if managed_running:
                status = 'ready' if available else 'starting'
            elif available:
                status = 'external'
            else:
                status = 'stopped'
            return {
                'running': managed_running or available,
                'managed': managed_running,
                'available': available,
                'status': status,
                'pid': self._process.pid if managed_running else None,
            }

    def toggle(self) -> dict:
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                terminate_process(self._process)
                self._process = None
                return {'success': True, 'message': '标定服务已停止', **self.state()}
            if self._node.calibration_action_client and self._node.calibration_action_client.server_is_ready():
                return {
                    'success': False,
                    'message': '标定服务由外部进程运行，Dashboard 不会停止它',
                    'status_code': 409,
                    **self.state(),
                }
            try:
                self._process = subprocess.Popen(
                    ['ros2', 'run', 'aprilgrid_calibration', 'aprilgrid_calibration_server'],
                    start_new_session=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.STDOUT,
                )
            except OSError as error:
                return {
                    'success': False,
                    'message': f'无法启动标定服务：{error}',
                    'status_code': 503,
                    **self.state(),
                }
            return {'success': True, 'message': '正在启动标定服务', **self.state()}


def register_calibration_routes(app, dashboard_runtime):
    """Register stateful calibration APIs once the dashboard node exists."""
    store_holder: dict[str, CalibrationStore] = {}
    service_holder: dict[str, CalibrationServiceManager] = {}

    def store() -> CalibrationStore:
        node = dashboard_runtime.get_node()
        existing = store_holder.get('store')
        if existing is None or existing._node is not node:
            existing = CalibrationStore(node)
            store_holder['store'] = existing
        return existing

    def service() -> CalibrationServiceManager:
        node = dashboard_runtime.get_node()
        existing = service_holder.get('service')
        if existing is None or existing._node is not node:
            existing = CalibrationServiceManager(node)
            service_holder['service'] = existing
        return existing

    @app.get('/api/calibration')
    async def calibration_state():
        return JSONResponse({**store().state(), 'service': service().state()})

    @app.get('/api/calibration/service')
    async def calibration_service_state():
        return JSONResponse(service().state())

    @app.post('/api/calibration/service/toggle')
    async def calibration_service_toggle():
        result = service().toggle()
        return JSONResponse(result, status_code=result.pop('status_code', 200))

    def shutdown() -> None:
        manager = service_holder.get('service')
        if manager is not None:
            manager.shutdown()

    @app.post('/api/calibration/session')
    async def calibration_session():
        return JSONResponse(store().new_session())

    @app.post('/api/calibration/captures')
    async def calibration_capture():
        try:
            return JSONResponse(store().capture())
        except RuntimeError as error:
            return JSONResponse({'error': str(error)}, status_code=409)

    @app.get('/api/calibration/preview')
    async def calibration_preview():
        preview = store().preview()
        if preview is None:
            return JSONResponse({'error': 'No image available'}, status_code=404)
        return StreamingResponse(iter([preview]), media_type='image/jpeg')

    @app.get('/api/calibration/captures/{filename}')
    async def calibration_capture_file(filename: str):
        path = store().capture_path(filename)
        if path is None:
            return JSONResponse({'error': 'Capture not found'}, status_code=404)
        return FileResponse(path, media_type='image/jpeg')

    @app.delete('/api/calibration/captures/{filename}')
    async def calibration_capture_delete(filename: str):
        if not store().delete_capture(filename):
            return JSONResponse({'error': 'Capture not found'}, status_code=404)
        return JSONResponse({'success': True})

    @app.post('/api/calibration/start')
    async def calibration_start(payload: dict):
        required = ('rows', 'cols', 'tag_size_m', 'tag_spacing_m', 'tag_family',
                    'max_reprojection_error', 'timeout_s')
        if any(key not in payload for key in required):
            return JSONResponse({'error': '标定参数不完整'}, status_code=422)
        try:
            return JSONResponse(store().start(payload))
        except (RuntimeError, ValueError) as error:
            return JSONResponse({'error': str(error)}, status_code=409)

    @app.post('/api/calibration/cancel')
    async def calibration_cancel():
        try:
            return JSONResponse(store().cancel())
        except RuntimeError as error:
            return JSONResponse({'error': str(error)}, status_code=409)

    @app.post('/api/calibration/apply')
    async def calibration_apply(payload: dict):
        try:
            return JSONResponse(store().apply(payload))
        except RuntimeError as error:
            return JSONResponse({'error': str(error)}, status_code=409)

    @app.get('/api/calibration/history/{filename}')
    async def calibration_file(filename: str):
        path = store()._history_dir / Path(filename).name
        if not path.is_file() or path.suffix not in {'.yaml', '.jpg'}:
            return JSONResponse({'error': 'Calibration file not found'}, status_code=404)
        media_type = 'application/x-yaml' if path.suffix == '.yaml' else 'image/jpeg'
        return FileResponse(path, media_type=media_type, filename=path.name)

    return shutdown