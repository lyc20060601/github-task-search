from task_parser import TaskSpec


MAX_QUERIES = 5

DOMAIN_EXPANSIONS: dict[str, tuple[str, ...]] = {
    "drone": ("drone", "UAV"),
    "aerial imagery": ("aerial", "remote sensing", "aerial image"),
}


def _normalize(value: str) -> str:
    return " ".join(value.split())


def _join_terms(*terms: str) -> str:
    return " ".join(term for term in terms if term)


def generate_queries(task_spec: TaskSpec) -> list[str]:
    """Generate distinct English-oriented GitHub repository search queries."""

    task = _normalize(task_spec.task or "").casefold()
    frameworks = [
        normalized.casefold()
        for value in task_spec.framework
        if (normalized := _normalize(value))
    ]
    must_haves = [
        normalized.casefold()
        for value in task_spec.must_have
        if (normalized := _normalize(value))
    ]
    hardware = [
        normalized
        for value in task_spec.hardware
        if (normalized := _normalize(value))
    ]
    preferences = [
        normalized.casefold()
        for value in task_spec.preferences
        if (normalized := _normalize(value))
    ]
    framework = frameworks[0] if frameworks else ""
    must_have = must_haves[0] if must_haves else ""

    domain_groups: list[tuple[str, ...]] = []
    seen_domains: set[str] = set()
    for value in task_spec.domain:
        domain = _normalize(value).casefold()
        if not domain or domain in seen_domains:
            continue
        seen_domains.add(domain)
        domain_groups.append(DOMAIN_EXPANSIONS.get(domain, (domain,)))

    candidates: list[str] = []
    primary_domains = domain_groups[:2]

    for terms in primary_domains:
        candidates.append(_join_terms(terms[0], task, framework))

    for terms in primary_domains:
        if len(terms) < 2:
            continue
        alias = terms[1]
        alias_framework = "" if alias.casefold() == "uav" else framework
        candidates.append(_join_terms(alias, task, alias_framework))

    for terms in reversed(primary_domains):
        if len(terms) > 2 and must_have:
            task_keyword = task.split()[-1] if task else ""
            candidates.append(_join_terms(terms[-1], task_keyword, must_have))
            break

    candidates.extend(
        [
            _join_terms(task, framework),
            _join_terms(task, must_have),
            _join_terms(task, hardware[0] if hardware else ""),
            _join_terms(task, preferences[0] if preferences else ""),
            task,
        ]
    )
    candidates.extend(
        _join_terms(terms[0], task) for terms in domain_groups[2:]
    )

    queries: list[str] = []
    seen_queries: set[str] = set()
    for candidate in candidates:
        query = _normalize(candidate)
        key = query.casefold()
        if not query or key in seen_queries:
            continue
        seen_queries.add(key)
        queries.append(query)
        if len(queries) == MAX_QUERIES:
            break

    return queries
