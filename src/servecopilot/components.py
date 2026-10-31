"""Derive a component label from the file paths a PR changed.

Labels come from *where the fix landed*, not from issue-title keywords:
predicting a label that was set from the title text would be circular.
"""

from collections import Counter

# Ordered: the first matching prefix wins, so specific paths come before
# broader ones (e.g. csrc/attention before csrc, arg_utils.py before vllm/engine).
COMPONENT_PREFIXES = [
    ("attention", ("vllm/v1/attention", "vllm/attention", "csrc/attention")),
    ("scheduler", ("vllm/v1/core",)),
    (
        "decoding",
        ("vllm/v1/spec_decode", "vllm/v1/structured_output", "vllm/v1/sample"),
    ),
    ("distributed_kv", ("vllm/distributed", "vllm/v1/kv_offload")),
    (
        "config",
        (
            "vllm/config",
            "vllm/config.py",
            "vllm/engine/arg_utils.py",
            "vllm/envs.py",
            "vllm/transformers_utils/config.py",
        ),
    ),
    (
        "engine",
        ("vllm/v1/engine", "vllm/engine", "vllm/v1/executor", "vllm/v1/metrics"),
    ),
    ("worker", ("vllm/v1/worker",)),
    (
        "models",
        (
            "vllm/models",
            "vllm/model_executor/models",
            "vllm/model_executor/model_loader",
            "vllm/transformers_utils",
            "vllm/multimodal",
        ),
    ),
    ("layers", ("vllm/model_executor/layers", "vllm/lora")),
    ("frontend", ("vllm/entrypoints", "vllm/reasoning")),
    ("compile", ("vllm/compilation",)),
    (
        "kernels",
        (
            "csrc",
            "vllm/_custom_ops.py",
            "vllm/platforms",
            "vllm/triton_utils",
            "cmake",
            "CMakeLists.txt",
            "rust",
        ),
    ),
    (
        "build_ci",
        (
            ".buildkite",
            ".github",
            "docker",
            "Dockerfile",
            "requirements",
            "benchmarks",
            "vllm/benchmarks",
            "setup.py",
            "pyproject.toml",
        ),
    ),
]

# Tests, docs and examples change alongside almost every fix, so they say
# nothing about which part of the system broke. They only count when a PR
# touches nothing else (e.g. a docs-only fix).
FALLBACK_PREFIXES = [
    ("docs", ("docs", "examples")),
    ("tests", ("tests",)),
]

OTHER = "other"


def _matches(path, prefix):
    # Segment-aware: "vllm/v1/core" matches "vllm/v1/core/sched.py",
    # not "vllm/v1/core_utils.py".
    return path == prefix or path.startswith(prefix + "/")


def _lookup(path, table):
    for component, prefixes in table:
        if any(_matches(path, prefix) for prefix in prefixes):
            return component
    return None


def path_component(path):
    return (
        _lookup(path, COMPONENT_PREFIXES) or _lookup(path, FALLBACK_PREFIXES) or OTHER
    )


def files_component(paths):
    """Majority component over the changed files.

    Tests/docs only decide when the PR touches nothing else. Code files that
    match no rule count as "other", so an unmapped code directory can't be
    mislabelled as "tests" just because the PR also added a test.
    """
    code_paths = [path for path in paths if not _lookup(path, FALLBACK_PREFIXES)]
    if code_paths:
        votes = Counter(
            _lookup(path, COMPONENT_PREFIXES) or OTHER for path in code_paths
        )
        mapped = Counter({c: n for c, n in votes.items() if c != OTHER})
        votes = mapped or votes
    else:
        votes = Counter(_lookup(path, FALLBACK_PREFIXES) for path in paths)
    if not votes:
        return OTHER

    # Ties go to the component listed first in the tables (deterministic).
    order = [name for name, _ in COMPONENT_PREFIXES + FALLBACK_PREFIXES] + [OTHER]
    return min(votes, key=lambda component: (-votes[component], order.index(component)))
