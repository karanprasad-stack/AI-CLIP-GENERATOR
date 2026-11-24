"""System Health Check & Diagnostics for AI Gaming Shorts Generator."""

import os
import sys
import shutil
import subprocess
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import psutil
import ctranslate2

from backend.app.config import DEFAULT_OUTPUT_DIR, MIN_FREE_DISK_GB


class HealthChecker:
    """Performs pre-flight and runtime diagnostics for CPU, GPU, disk, FFmpeg, and models."""

    @staticmethod
    def get_ffmpeg_info() -> Dict[str, Any]:
        """Inspects FFmpeg binary location and version."""
        ffmpeg_bin = shutil.which("ffmpeg")
        if not ffmpeg_bin:
            # Check common Windows winget path
            local_app_data = os.environ.get("LOCALAPPDATA", "")
            if local_app_data:
                winget_base = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
                if winget_base.exists():
                    for candidate in winget_base.glob("**/ffmpeg.exe"):
                        ffmpeg_bin = str(candidate)
                        break

        if not ffmpeg_bin:
            return {"available": False, "path": None, "version": None}

        version_str = "unknown"
        try:
            res = subprocess.run([ffmpeg_bin, "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
            if res.returncode == 0:
                first_line = res.stdout.splitlines()[0] if res.stdout else ""
                version_str = first_line.split("Copyright")[0].strip()
        except Exception:
            pass

        return {
            "available": True,
            "path": ffmpeg_bin,
            "version": version_str,
        }

    @staticmethod
    def get_gpu_info() -> Dict[str, Any]:
        """Detects NVIDIA GPU availability via CTranslate2."""
        try:
            cuda_count = ctranslate2.get_cuda_device_count()
            if cuda_count > 0:
                return {
                    "cuda_available": True,
                    "device_count": cuda_count,
                    "acceleration": "NVIDIA NVENC / CUDA",
                }
        except Exception:
            pass

        return {
            "cuda_available": False,
            "device_count": 0,
            "acceleration": "CPU Fallback (libx264)",
        }

    @staticmethod
    def get_storage_info(target_dir: Optional[Path] = None) -> Dict[str, Any]:
        """Checks target storage directory writability and free disk space."""
        check_dir = Path(target_dir) if target_dir else Path(DEFAULT_OUTPUT_DIR)
        check_dir.mkdir(parents=True, exist_ok=True)

        writable = os.access(str(check_dir), os.W_OK)
        usage = shutil.disk_usage(str(check_dir))
        total_gb = round(usage.total / (1024 ** 3), 2)
        free_gb = round(usage.free / (1024 ** 3), 2)
        sufficient = free_gb >= MIN_FREE_DISK_GB

        return {
            "path": str(check_dir.resolve()),
            "writable": writable,
            "total_gb": total_gb,
            "free_gb": free_gb,
            "min_required_gb": MIN_FREE_DISK_GB,
            "sufficient_space": sufficient,
        }

    @staticmethod
    def get_memory_info() -> Dict[str, Any]:
        """Returns host RAM metrics."""
        vm = psutil.virtual_memory()
        return {
            "total_gb": round(vm.total / (1024 ** 3), 2),
            "available_gb": round(vm.available / (1024 ** 3), 2),
            "percent_used": vm.percent,
        }

    @classmethod
    def get_full_health(cls, output_dir: Optional[Path] = None) -> Dict[str, Any]:
        """Returns comprehensive diagnostic status."""
        ffmpeg_info = cls.get_ffmpeg_info()
        gpu_info = cls.get_gpu_info()
        storage_info = cls.get_storage_info(output_dir)
        memory_info = cls.get_memory_info()

        is_healthy = ffmpeg_info["available"] and storage_info["writable"] and storage_info["sufficient_space"]

        return {
            "status": "ok" if is_healthy else "degraded",
            "phase": "7A",
            "service": "ai-clipper",
            "version": "1.0.0",
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "ffmpeg": ffmpeg_info,
            "gpu": gpu_info,
            "storage": storage_info,
            "memory": memory_info,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
