"""Reports package exports."""

__all__ = ["ReportGenerator"]


def __getattr__(name: str):
    if name == "ReportGenerator":
        from .report_generator import ReportGenerator
        return ReportGenerator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
