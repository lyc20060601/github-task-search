from query_planner import generate_queries
from task_parser import TaskSpec


def test_generate_queries_creates_five_useful_github_queries() -> None:
    task_spec = TaskSpec(
        task="semantic segmentation",
        domain=["drone", "aerial imagery"],
        framework=["PyTorch"],
        must_have=["custom dataset"],
        preferences=["high accuracy"],
    )

    assert generate_queries(task_spec) == [
        "drone semantic segmentation pytorch",
        "aerial semantic segmentation pytorch",
        "UAV semantic segmentation",
        "remote sensing semantic segmentation pytorch",
        "aerial image segmentation custom dataset",
    ]


def test_generate_queries_limits_and_deduplicates_results() -> None:
    task_spec = TaskSpec(
        task="object detection",
        domain=["drone", "Drone", "aerial imagery", "robotics"],
        framework=["PyTorch"],
        must_have=["custom dataset"],
    )

    queries = generate_queries(task_spec)

    assert len(queries) <= 5
    assert len({query.casefold() for query in queries}) == len(queries)


def test_generate_queries_returns_empty_list_for_empty_task_spec() -> None:
    assert generate_queries(TaskSpec()) == []
