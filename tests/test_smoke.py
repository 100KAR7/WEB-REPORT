"""Baseline smoke tests for CI wiring."""


def test_main_module_imports() -> None:
    """Ensure the entrypoint module imports without errors."""
    import main  # noqa: F401
