"""Read-only detection of the current machine's compatibility profile."""

from __future__ import annotations

import ctypes
import os
import platform
import re
import shutil
import subprocess
import sys
from typing import Optional, Sequence

from .models import MachineProfile

_COMMAND_TIMEOUT_SECONDS = 5


def _run_read_only_command(command: Sequence[str]) -> Optional[subprocess.CompletedProcess[str]]:
    """Run one allowlisted-style read-only command without invoking a shell."""

    try:
        return subprocess.run(
            list(command),
            capture_output=True,
            text=True,
            timeout=_COMMAND_TIMEOUT_SECONDS,
            check=False,
            shell=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _get_total_memory_gb() -> Optional[float]:
    """Read physical memory through Windows' read-only API when available."""

    class _MemoryStatusEx(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    try:
        status = _MemoryStatusEx()
        status.dwLength = ctypes.sizeof(_MemoryStatusEx)
        if not hasattr(ctypes, "windll"):
            return None
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return None
        return round(status.ullTotalPhys / (1024**3), 2)
    except (AttributeError, OSError, TypeError):
        return None


def _python_version() -> Optional[str]:
    try:
        return ".".join(str(part) for part in sys.version_info[:3])
    except (AttributeError, TypeError):
        return None


def _detect_nvidia() -> dict[str, object]:
    executable = shutil.which("nvidia-smi")
    if not executable:
        return {
            "nvidia_gpu_available": False,
            "gpu_vendor": None,
            "gpu_name": None,
            "gpu_memory_gb": None,
            "cuda_available": False,
            "cuda_version": None,
        }

    query = _run_read_only_command(
        [executable, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"]
    )
    if query is None or query.returncode != 0 or not query.stdout.strip():
        return {
            "nvidia_gpu_available": False,
            "gpu_vendor": None,
            "gpu_name": None,
            "gpu_memory_gb": None,
            "cuda_available": False,
            "cuda_version": None,
        }

    first_line = query.stdout.strip().splitlines()[0]
    name, _, memory_text = first_line.partition(",")
    gpu_name = name.strip() or "unknown"
    gpu_memory_gb = None
    try:
        gpu_memory_gb = round(float(memory_text.strip()) / 1024, 2)
    except (TypeError, ValueError):
        pass

    version = _run_read_only_command([executable])
    version_output = "" if version is None else f"{version.stdout}\n{version.stderr}"
    cuda_match = re.search(r"CUDA Version:\s*([\d.]+)", version_output, flags=re.IGNORECASE)
    return {
        "nvidia_gpu_available": True,
        "gpu_vendor": "NVIDIA",
        "gpu_name": gpu_name,
        "gpu_memory_gb": gpu_memory_gb,
        "cuda_available": cuda_match is not None,
        "cuda_version": cuda_match.group(1) if cuda_match else None,
    }


def _command_available(command: str) -> Optional[bool]:
    executable = shutil.which(command)
    if not executable:
        return False
    result = _run_read_only_command([executable, "--version"])
    return result is not None and result.returncode == 0


def detect_machine_profile() -> MachineProfile:
    """Return a best-effort profile without changing the host system."""

    try:
        os_name = platform.system() or None
    except Exception:
        os_name = None
    try:
        os_version = platform.version() or None
    except Exception:
        os_version = None
    try:
        architecture = platform.machine() or None
    except Exception:
        architecture = None
    try:
        cpu_name = platform.processor() or "unknown"
    except Exception:
        cpu_name = "unknown"
    try:
        cpu_cores = os.cpu_count()
    except Exception:
        cpu_cores = None

    profile_data: dict[str, object] = {
        "os_name": os_name,
        "os_version": os_version,
        "architecture": architecture,
        "cpu_name": cpu_name,
        "cpu_cores": cpu_cores,
        "memory_total_gb": _get_total_memory_gb(),
        "python_available": _python_version() is not None,
        "python_version": _python_version(),
        "docker_available": _command_available("docker"),
        "git_available": _command_available("git"),
    }
    profile_data.update(_detect_nvidia())
    return MachineProfile(**profile_data)
