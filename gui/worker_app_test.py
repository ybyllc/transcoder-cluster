#!/usr/bin/env python3
"""GUI Worker test entry with simulated FFmpeg unavailable state."""

from __future__ import annotations

from typing import Optional

import gui.worker_app as worker_app


SIMULATE_FFMPEG_NOT_INSTALLED = True

_ORIGINAL_GET_FFMPEG_VERSION = worker_app.get_ffmpeg_version


def _simulated_get_ffmpeg_version(ffmpeg_path: str) -> Optional[str]:
    if SIMULATE_FFMPEG_NOT_INSTALLED:
        return None
    return _ORIGINAL_GET_FFMPEG_VERSION(ffmpeg_path)


worker_app.get_ffmpeg_version = _simulated_get_ffmpeg_version

WorkerGuiLogHandler = worker_app.WorkerGuiLogHandler
WorkerApp = worker_app.WorkerApp
main = worker_app.main


if __name__ == "__main__":
    main()
