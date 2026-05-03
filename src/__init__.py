# src/__init__.py
from importlib.metadata import version as _pkg_version

from .ab_test import calculate_ab
from .did import calculate_did

__version__ = _pkg_version("agent-causal-decision-tool")
__all__ = ["calculate_ab", "calculate_did", "__version__"]