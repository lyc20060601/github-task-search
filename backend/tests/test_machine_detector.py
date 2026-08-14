import subprocess

from compatibility import machine_detector


def test_detect_machine_profile_collects_windows_and_tool_information(monkeypatch):
    monkeypatch.setattr(machine_detector.platform, "system", lambda: "Windows")
    monkeypatch.setattr(machine_detector.platform, "version", lambda: "10.0.26100")
    monkeypatch.setattr(machine_detector.platform, "machine", lambda: "AMD64")
    monkeypatch.setattr(machine_detector.platform, "processor", lambda: "Test CPU")
    monkeypatch.setattr(machine_detector.os, "cpu_count", lambda: 16)
    monkeypatch.setattr(machine_detector, "_get_total_memory_gb", lambda: 31.75)
    monkeypatch.setattr(machine_detector.sys, "version_info", (3, 12, 4))

    available = {"nvidia-smi", "docker", "git"}
    monkeypatch.setattr(
        machine_detector.shutil,
        "which",
        lambda command: f"C:/bin/{command}.exe" if command in available else None,
    )

    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        if command[0].endswith("nvidia-smi.exe") and "--query-gpu=name,memory.total" in command:
            return subprocess.CompletedProcess(command, 0, "NVIDIA RTX 4090, 24564\n", "")
        if command[0].endswith("nvidia-smi.exe"):
            return subprocess.CompletedProcess(command, 0, "NVIDIA-SMI 560.00 CUDA Version: 12.6", "")
        return subprocess.CompletedProcess(command, 0, "version output", "")

    monkeypatch.setattr(machine_detector.subprocess, "run", fake_run)

    profile = machine_detector.detect_machine_profile()

    assert profile.os_name == "Windows"
    assert profile.cpu_name == "Test CPU"
    assert profile.memory_total_gb == 31.75
    assert profile.gpu_vendor == "NVIDIA"
    assert profile.gpu_name == "NVIDIA RTX 4090"
    assert profile.gpu_memory_gb == 23.99
    assert profile.cuda_available is True
    assert profile.cuda_version == "12.6"
    assert profile.python_available is True
    assert profile.python_version == "3.12.4"
    assert profile.docker_available is True
    assert profile.git_available is True
    assert all(kwargs["timeout"] > 0 for _, kwargs in calls)
    assert all(kwargs.get("shell") is not True for _, kwargs in calls)


def test_detect_machine_profile_handles_missing_or_failed_commands(monkeypatch):
    monkeypatch.setattr(machine_detector.platform, "system", lambda: "Windows")
    monkeypatch.setattr(machine_detector.platform, "version", lambda: "unknown")
    monkeypatch.setattr(machine_detector.platform, "machine", lambda: "AMD64")
    monkeypatch.setattr(machine_detector.platform, "processor", lambda: "")
    monkeypatch.setattr(machine_detector.os, "cpu_count", lambda: None)
    monkeypatch.setattr(machine_detector, "_get_total_memory_gb", lambda: None)
    monkeypatch.setattr(machine_detector.sys, "version_info", (3, 11, 0))
    monkeypatch.setattr(
        machine_detector.shutil,
        "which",
        lambda command: f"C:/bin/{command}.exe" if command in {"nvidia-smi", "docker"} else None,
    )

    def failed_run(command, **kwargs):
        if command[0].endswith("nvidia-smi.exe"):
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])
        return subprocess.CompletedProcess(command, 1, "", "not available")

    monkeypatch.setattr(machine_detector.subprocess, "run", failed_run)

    profile = machine_detector.detect_machine_profile()

    assert profile.cpu_name == "unknown"
    assert profile.nvidia_gpu_available is False
    assert profile.gpu_vendor is None
    assert profile.gpu_name is None
    assert profile.gpu_memory_gb is None
    assert profile.cuda_available is False
    assert profile.cuda_version is None
    assert profile.docker_available is False
    assert profile.git_available is False
