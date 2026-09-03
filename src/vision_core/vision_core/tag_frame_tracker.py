"""Track which AprilTag TF frames are active and resolve candidate frames."""

from __future__ import annotations

import time


class TagFrameTracker:
    """Track which AprilTag TF frames are active and resolve candidate frames."""

    def __init__(
        self,
        *,
        tag_frame_id: str = '',
        tag_family: str = '',
        tag_id: int = -1,
        tag_frame_prefix: str = '',
        publish_all_tags: bool = False,
        tag_timeout_s: float = 1.0,
    ) -> None:
        self.tag_frame_id = tag_frame_id
        self.tag_family = tag_family
        self.tag_id = tag_id
        self.tag_frame_prefix = tag_frame_prefix
        self.publish_all_tags = publish_all_tags
        self.tag_timeout_s = tag_timeout_s

        self.known_frames: set[str] = set()
        self._last_seen: dict[str, float] = {}
        self._cache: set[str] | None = None
        self._cache_dirty = True
        self.latest_hint: str | None = None

    @staticmethod
    def normalize_family(family: str) -> str:
        family = str(family).strip()
        if not family or family.startswith('tag'):
            return family
        return f'tag{family}'

    def frame_from_detection(self, detection) -> str:
        family = self.normalize_family(getattr(detection, 'family', ''))
        detection_id = int(getattr(detection, 'id', -1))
        if family and detection_id >= 0:
            frame = f'{family}:{detection_id}'
            if self.tag_frame_prefix:
                frame = f'{self.tag_frame_prefix}/{frame}'
            return frame
        return ''

    def is_auto_tag_frame(self, frame_id: str) -> bool:
        frame_id = frame_id.lstrip('/')
        prefix = ''
        if '/' in frame_id:
            prefix, frame_id = frame_id.rsplit('/', 1)
        family, separator, raw_id = frame_id.partition(':')
        if not separator or not raw_id.isdigit():
            return False
        family = self.normalize_family(family)
        if not family.startswith('tag'):
            return False
        tag_id = int(raw_id)
        return (
            (not self.tag_frame_prefix or prefix == self.tag_frame_prefix)
            and (not self.tag_family or family == self.tag_family)
            and (self.tag_id < 0 or tag_id == self.tag_id)
        )

    def remember(self, frame_id: str) -> None:
        is_new = frame_id not in self.known_frames
        self.known_frames.add(frame_id)
        self._last_seen[frame_id] = time.monotonic()
        if is_new or self.latest_hint != frame_id:
            self._cache_dirty = True
        self.latest_hint = frame_id

    def expire_stale(self) -> None:
        if self.tag_timeout_s <= 0.0:
            return
        now = time.monotonic()
        active = {f for f in self.known_frames if now - self._last_seen.get(f, 0.0) <= self.tag_timeout_s}
        if active != self.known_frames:
            self.known_frames = active
            self._cache_dirty = True
        self._last_seen = {f: ts for f, ts in self._last_seen.items() if now - ts <= self.tag_timeout_s}

    def candidate_frames(self) -> set[str]:
        if not self._cache_dirty and self._cache is not None:
            return self._cache
        resolved = self._resolve()
        self._cache = resolved
        self._cache_dirty = False
        return resolved

    def _resolve(self) -> set[str]:
        if self.tag_frame_id:
            return {self.tag_frame_id}
        if self.tag_family and self.tag_id >= 0:
            frame = f'{self.tag_family}:{self.tag_id}'
            if self.tag_frame_prefix:
                frame = f'{self.tag_frame_prefix}/{frame}'
            return {frame}
        if self.publish_all_tags:
            return set(self.known_frames)
        if self.latest_hint in self.known_frames:
            return {self.latest_hint}
        self.latest_hint = None
        return set()