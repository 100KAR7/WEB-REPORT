"""
ai_analysis/ai_analyzer.py
---------------------------
Uses either Anthropic or local Ollama to analyse page content for UX,
clarity, and actionable improvement suggestions.
"""

import subprocess

import requests

from crawler.models import PageData
from config.settings import settings
from config.logging_config import logger


SYSTEM_PROMPT = """You are an expert web analyst. Given a webpage's title and 
text content, provide a concise audit covering:
1. Content clarity (is the purpose of the page immediately clear?)
2. User experience issues (confusing language, missing calls-to-action, etc.)
3. Three specific, actionable improvement suggestions

Keep the response under 200 words and use plain language."""


class AIAnalyzer:
    """Sends page content to Anthropic or Ollama and returns AI-generated insights."""

    def __init__(self):
        self.provider = None
        self.client = None
        self.last_model_used = None

        if settings.anthropic_api_key:
            try:
                import anthropic
            except ImportError as exc:
                raise ImportError(
                    "Anthropic support is not installed. "
                    "Run `pip install anthropic` to enable AI analysis."
                ) from exc

            self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
            self.provider = "anthropic"
            self.last_model_used = settings.ai_model
            return

        if self._ollama_available():
            self.provider = "ollama"
            return

        raise RuntimeError(
            "No LLM backend is available. Set ANTHROPIC_API_KEY or start Ollama "
            f"at {settings.ollama_url} with model {settings.ollama_model}."
        )

    def analyze(self, pages: list[PageData]) -> list[dict]:
        """Analyse each page and return a list of AI insight records."""
        eligible_pages = self.eligible_pages(pages)

        if self.provider == "ollama":
            if not eligible_pages:
                return []
            logger.info(
                f"AI analysing via {self.provider}: {len(eligible_pages)} page(s)"
            )
            insight = self._analyze_pages_with_ollama(eligible_pages)
            return [{
                "url": f"Site-wide analysis ({len(eligible_pages)} page(s))",
                "insight": insight,
            }]

        results = []
        for page in eligible_pages:
            logger.info(f"AI analysing via {self.provider}: {page.url}")
            insight = self._analyze_page(page)
            results.append({"url": page.url, "insight": insight})
        return results

    # ------------------------------------------------------------------

    def _analyze_page(self, page: PageData) -> str:
        user_message = (
            f"Page title: {page.title}\n\n"
            f"Page content (first 1500 chars):\n{page.text_content[:1500]}"
        )
        try:
            if self.provider == "anthropic":
                message = self.client.messages.create(
                    model=settings.ai_model,
                    max_tokens=512,
                    system=SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": user_message}],
                )
                return message.content[0].text

            return self._analyze_with_ollama(user_message)
        except Exception as exc:
            logger.error(f"AI analysis failed for {page.url}: {exc}")
            return f"Analysis unavailable: {exc}"

    def eligible_pages(self, pages: list[PageData]) -> list[PageData]:
        """Return pages that are suitable for AI analysis."""
        return [
            page for page in pages
            if page.is_ok and page.text_content
        ]

    def backend_details(self) -> dict:
        """Return the current AI backend metadata for reporting."""
        details = {
            "provider": self.provider,
            "model": self.last_model_used or "",
            "endpoint": "",
        }

        if self.provider == "anthropic":
            details["model"] = self.last_model_used or settings.ai_model
            return details

        if self.provider == "ollama":
            details["model"] = self.last_model_used or settings.ollama_model
            details["endpoint"] = settings.ollama_url

        return details

    def _ollama_available(self) -> bool:
        try:
            response = requests.get(f"{settings.ollama_url.rstrip('/')}/api/tags", timeout=5)
            if response.status_code != 200:
                return bool(self._list_ollama_models_cli())
            models = [model.get("name", "") for model in response.json().get("models", [])]
            if not models:
                return True
            return any(settings.ollama_model in model for model in models) or bool(
                self._list_ollama_models_cli()
            )
        except Exception:
            return bool(self._list_ollama_models_cli())

    def _analyze_with_ollama(self, user_message: str) -> str:
        candidate_models = self._candidate_ollama_models()

        last_error = None
        for model_name in candidate_models:
            try:
                payload = {
                    "model": model_name,
                    "system": SYSTEM_PROMPT,
                    "prompt": user_message,
                    "stream": False,
                    "options": {
                        "temperature": 0.2,
                        "num_predict": 128,
                    },
                }
                response = requests.post(
                    f"{settings.ollama_url.rstrip('/')}/api/generate",
                    json=payload,
                    timeout=settings.ai_timeout_seconds,
                )
                if response.ok:
                    self.last_model_used = model_name
                    return response.json().get("response", "").strip()

                last_error = f"{response.status_code} {response.text.strip()}"
                if response.status_code != 404:
                    response.raise_for_status()
            except requests.RequestException as exc:
                last_error = str(exc)
                continue

        for model_name in candidate_models:
            try:
                completed = subprocess.run(
                    ["ollama", "run", model_name, user_message],
                    capture_output=True,
                    text=True,
                    timeout=max(settings.ai_timeout_seconds, 180),
                    check=False,
                )
            except Exception as exc:
                last_error = str(exc)
                continue

            stdout = (completed.stdout or "").strip()
            stderr = (completed.stderr or "").strip()
            if completed.returncode == 0 and stdout:
                self.last_model_used = model_name
                return stdout

            last_error = stderr or stdout or f"ollama CLI exited with code {completed.returncode}"

        raise RuntimeError(
            "Ollama generation failed. "
            f"Tried models: {candidate_models}. Last error: {last_error}"
        )

    def _analyze_pages_with_ollama(self, pages: list[PageData]) -> str:
        prompt_parts = [
            "Review this website audit data and provide a concise site-wide analysis.",
            "Return under 180 words covering: clarity, UX issues, and 3 actionable improvements.",
            "",
        ]

        for idx, page in enumerate(pages[:3], 1):
            excerpt = page.text_content[:500]
            prompt_parts.extend([
                f"Page {idx}: {page.url}",
                f"Title: {page.title or '(untitled)'}",
                f"Load time: {page.load_time_ms:.0f} ms",
                f"Meta description: {page.meta_description or '(missing)'}",
                f"H1 tags: {', '.join(page.h1_tags) if page.h1_tags else '(missing)'}",
                f"Content excerpt: {excerpt}",
                "",
            ])

        return self._analyze_with_ollama("\n".join(prompt_parts))

    def _candidate_ollama_models(self) -> list[str]:
        candidates = [settings.ollama_model]
        if ":" not in settings.ollama_model:
            candidates.append(f"{settings.ollama_model}:latest")

        for model_name in self._list_ollama_models_cli():
            if model_name:
                candidates.append(model_name)

        seen = set()
        ordered = []
        for model_name in candidates:
            if model_name not in seen:
                seen.add(model_name)
                ordered.append(model_name)
        return ordered

    def _list_ollama_models_cli(self) -> list[str]:
        try:
            completed = subprocess.run(
                ["ollama", "list"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except Exception:
            return []

        if completed.returncode != 0:
            return []

        lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
        if not lines:
            return []

        models = []
        for line in lines[1:]:
            parts = line.split()
            if parts:
                models.append(parts[0])
        return models
