"""Threaded, model-neutral episode recorder used by the web controller."""
from __future__ import annotations

import json
import os
import shutil
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np


class EpisodeRecorder:
    def __init__(self, root: Path, joint_names: list[str], snapshot, fps: int = 20):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.joint_names = list(joint_names)
        self.snapshot = snapshot
        self.fps = fps
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._episode = None
        self._error = ""
        self._frames = 0
        self._started_monotonic = 0.0

    def status(self):
        with self._lock:
            return {
                "active": self._thread is not None and self._thread.is_alive(),
                "episode_index": None if self._episode is None else self._episode[0],
                "task": None if self._episode is None else self._episode[2],
                "frames": self._frames,
                "duration_s": 0 if not self._started_monotonic else round(time.monotonic()-self._started_monotonic, 1),
                "fps": self.fps,
                "error": self._error,
            }

    def start(self, task: str):
        task = " ".join(str(task).split())
        if not task or len(task) > 300:
            raise ValueError("Task instruction must contain 1-300 characters")
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                raise ValueError("An episode is already recording")
            indices = []
            for path in self.root.glob("episode_*"):
                try: indices.append(int(path.name.rsplit("_", 1)[1]))
                except ValueError: pass
            index = max(indices, default=-1) + 1
            temp = self.root / f".recording_episode_{index:06d}"
            if temp.exists(): shutil.rmtree(temp)
            temp.mkdir()
            self._episode = (index, temp, task)
            self._frames = 0
            self._error = ""
            self._started_monotonic = time.monotonic()
            self._stop.clear()
            self._thread = threading.Thread(target=self._record_loop, daemon=True, name="episode-recorder")
            self._thread.start()
        return self.status()

    def finish(self, success: bool):
        with self._lock:
            thread = self._thread
        if thread is None:
            raise ValueError("No episode is recording")
        self._stop.set()
        thread.join(timeout=5)
        if thread.is_alive():
            raise RuntimeError("Recorder did not stop")
        with self._lock:
            index, temp, task = self._episode
            if self._error:
                raise RuntimeError(self._error)
            metadata = {
                "format": "xlerobot-raw-v1", "episode_index": index, "task": task,
                "success": bool(success), "frames": self._frames, "fps": self.fps,
                "joint_names": self.joint_names,
                "state_units": ["percent" if n.endswith("gripper") else "degree" for n in self.joint_names],
                "started_at": datetime.fromtimestamp(self._started_wall, timezone.utc).isoformat(),
                "finished_at": datetime.now(timezone.utc).isoformat(),
            }
            (temp/"episode.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2)+"\n")
            final = self.root / f"episode_{index:06d}"
            os.replace(temp, final)
            self._thread = None; self._episode = None; self._started_monotonic = 0
        return {**metadata, "path": str(final)}

    def discard(self):
        with self._lock:
            thread, episode = self._thread, self._episode
        if thread is None: raise ValueError("No episode is recording")
        self._stop.set(); thread.join(timeout=5)
        if thread.is_alive(): raise RuntimeError("Recorder did not stop")
        with self._lock:
            shutil.rmtree(episode[1], ignore_errors=True)
            self._thread = None; self._episode = None; self._started_monotonic = 0; self._frames = 0
        return self.status()

    def _record_loop(self):
        index, path, task = self._episode
        self._started_wall = time.time()
        writers = {}
        next_frame = time.monotonic()
        try:
            with (path/"frames.jsonl").open("w", buffering=1) as rows:
                while not self._stop.is_set():
                    snap = self.snapshot()
                    elapsed = time.monotonic()-self._started_monotonic
                    images = snap.pop("images")
                    if not all(images.values()):
                        raise RuntimeError("Both camera frames are required for recording")
                    row = {"frame_index": self._frames, "timestamp": elapsed, "task": task, **snap}
                    rows.write(json.dumps(row, ensure_ascii=False, separators=(",", ":"))+"\n")
                    for side, encoded in images.items():
                        frame = cv2.imdecode(np.frombuffer(encoded, np.uint8), cv2.IMREAD_COLOR)
                        if frame is None: raise RuntimeError(f"Could not decode {side} camera frame")
                        if side not in writers:
                            h, w = frame.shape[:2]
                            writers[side] = cv2.VideoWriter(str(path/f"{side}.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), self.fps, (w,h))
                            if not writers[side].isOpened(): raise RuntimeError(f"Could not open {side}.mp4")
                        writers[side].write(frame)
                    self._frames += 1
                    next_frame += 1/self.fps
                    self._stop.wait(max(0, next_frame-time.monotonic()))
        except Exception as exc:
            self._error = str(exc)
            self._stop.set()
        finally:
            for writer in writers.values(): writer.release()
