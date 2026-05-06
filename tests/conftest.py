"""pytest configuration — shared fixtures and hooks"""

import pytest
import numpy as np
import random


@pytest.fixture(autouse=True)
def deterministic_rng():
    """Reset numpy/Python random state before every test for deterministic behavior.

    Bayesian tests use Monte Carlo sampling (np.random.beta) and assert tight
    thresholds (e.g. P(variant wins) > 0.99). Without a fixed seed, CI runs
    can intermittently fail.
    """
    # Python random
    random.seed(42)
    # NumPy random — both global and Generator
    np.random.seed(42)
    yield
    # No need to restore — each test gets its own seed


@pytest.fixture
def bayes_result_strong_positive():
    """A BayesOutput with strong positive signal (variant clearly wins)."""
    from src.bayes import calculate_bayes_ab
    return calculate_bayes_ab({
        "control_conversions": 100,
        "control_total": 5000,
        "variant_conversions": 150,
        "variant_total": 5000
    }, n_samples=20000)


@pytest.fixture
def bayes_result_strong_negative():
    """A BayesOutput with strong negative signal (variant clearly loses)."""
    from src.bayes import calculate_bayes_ab
    return calculate_bayes_ab({
        "control_conversions": 100,
        "control_total": 5000,
        "variant_conversions": 50,
        "variant_total": 5000
    }, n_samples=20000)


@pytest.fixture
def bayes_result_inconclusive():
    """A BayesOutput with inconclusive signal (rates nearly identical)."""
    from src.bayes import calculate_bayes_ab
    return calculate_bayes_ab({
        "control_conversions": 80,
        "control_total": 5000,
        "variant_conversions": 85,
        "variant_total": 5000
    }, n_samples=20000)


@pytest.fixture
def bayes_result_low_traffic():
    """A BayesOutput with very low traffic (PRIOR_DOMINATES warning expected)."""
    from src.bayes import calculate_bayes_ab
    return calculate_bayes_ab({
        "control_conversions": 1,
        "control_total": 20,
        "variant_conversions": 2,
        "variant_total": 20
    }, n_samples=20000)