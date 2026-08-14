from compatibility.models import MachineProfile


def test_machine_profile_accepts_complete_profile():
    profile = MachineProfile(
        os_name="Windows",
        os_version="11",
        architecture="x86_64",
        cpu_name="Test CPU",
        cpu_cores=16,
        memory_total_gb=64.0,
        gpu_vendor="NVIDIA",
        gpu_name="RTX 4090",
        gpu_memory_gb=24.0,
        nvidia_gpu_available=True,
        cuda_available=True,
        cuda_version="12.4",
        python_available=True,
        python_version="3.12",
        docker_available=True,
        git_available=True,
    )

    assert profile.model_dump()["gpu_name"] == "RTX 4090"
    assert profile.cpu_cores == 16


def test_machine_profile_accepts_unknown_or_null_values():
    profile = MachineProfile(
        os_name=None,
        os_version="unknown",
        architecture=None,
        cpu_name="unknown",
        cpu_cores=None,
        memory_total_gb=None,
        gpu_vendor=None,
        gpu_name="unknown",
        gpu_memory_gb=None,
        nvidia_gpu_available=None,
        cuda_available=None,
        cuda_version="unknown",
        python_available=None,
        python_version=None,
        docker_available=None,
        git_available=None,
    )

    assert profile.os_name is None
    assert profile.gpu_name == "unknown"
    assert profile.docker_available is None
