"""Process Tracker: tracks and guarantees cleanup/termination of active child subprocesses."""

import subprocess
import threading
from typing import Dict, List, Optional
import psutil


class ProcessTracker:
    """Thread-safe registry mapping project IDs to active subprocesses."""

    _lock = threading.Lock()
    _active_processes: Dict[str, List[subprocess.Popen]] = {}

    @classmethod
    def register_process(cls, project_id: str, proc: subprocess.Popen) -> None:
        """Registers a child subprocess under a project ID."""
        with cls._lock:
            if project_id not in cls._active_processes:
                cls._active_processes[project_id] = []
            cls._active_processes[project_id].append(proc)

    @classmethod
    def unregister_process(cls, project_id: str, proc: subprocess.Popen) -> None:
        """Removes a finished subprocess from the registry."""
        with cls._lock:
            if project_id in cls._active_processes:
                if proc in cls._active_processes[project_id]:
                    cls._active_processes[project_id].remove(proc)

    @classmethod
    def kill_project_processes(cls, project_id: str) -> int:
        """Terminates and kills all active child subprocesses associated with a project."""
        killed_count = 0
        with cls._lock:
            procs = list(cls._active_processes.get(project_id, []))
            cls._active_processes[project_id] = []

        for p in procs:
            try:
                if p.poll() is None:
                    # Terminate child process tree
                    try:
                        parent = psutil.Process(p.pid)
                        for child in parent.children(recursive=True):
                            try:
                                child.kill()
                            except Exception:
                                pass
                        parent.kill()
                    except Exception:
                        p.kill()
                    killed_count += 1
            except Exception:
                pass

        return killed_count
