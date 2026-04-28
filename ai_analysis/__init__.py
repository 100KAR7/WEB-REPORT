"""AI analysis package exports."""

__all__ = ["AIAnalyzer"]


def __getattr__(name: str):
    if name == "AIAnalyzer":
        from .ai_analyzer import AIAnalyzer
        return AIAnalyzer
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
