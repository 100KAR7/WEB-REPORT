"""Test helpers package exports."""

__all__ = ["LinkChecker", "PerformanceChecker"]


def __getattr__(name: str):
    if name == "LinkChecker":
        from .link_checker import LinkChecker
        return LinkChecker
    if name == "PerformanceChecker":
        from .performance_checker import PerformanceChecker
        return PerformanceChecker
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
