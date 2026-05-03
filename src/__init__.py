# src/__init__.py
from importlib.metadata import version as _pkg_version

from .ab_test import calculate_ab
from .did import calculate_did
from .planning import calculate_plan
from .bayes import calculate_bayes_ab
from .cohort import cohort_breakdown
from . import store

__version__ = _pkg_version("agent-causal-decision-tool")
__all__ = [
    "calculate_ab", "calculate_did", "calculate_plan", "calculate_bayes_ab",
    "cohort_breakdown", "store", "__version__"
]