"""Process lifecycle helpers."""

from __future__ import annotations

import logging
import os
import signal
import subprocess

_log = logging.getLogger(__name__)


def terminate_process(
    process: subprocess.Popen[str],
    *,
    gentle_timeout: float = 5.0,
    term_timeout: float = 3.0,
    kill_timeout: float = 3.0,
) -> None:
    """Terminate a subprocess with escalating signals: SIGINT → SIGTERM → SIGKILL."""
    try:
        os.killpg(process.pid, signal.SIGINT)
        process.wait(timeout=gentle_timeout)
    except ProcessLookupError:
        pass
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=term_timeout)
        except ProcessLookupError:
            pass
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=kill_timeout)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                pass
    if process.poll() is None:
        _log.warning('Process (pid=%d) still alive after SIGKILL', process.pid)
    else:
        _log.info(
            'Process (pid=%d) terminated with code %d',
            process.pid, process.returncode,
        )