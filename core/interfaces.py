"""Market data provider using Groq for AI-powered signal analysis."""

import os
from pathlib import Path
from typing import Any

import httpx
from loguru import logger


class GroqSignalProvider:
    """
    AI signal analysis provider using Groq's inference API.

    Groq offers extremely fast LLM inference for real-time market signal
    processing and trade decision support.
    """

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("GROQ_API_KEY")
        self.api_url = "https://api.groq.com/openai/v1/chat/completions"

    async def analyze(self, market_data: str | Path) -> str:
        """
        Analyze market data snapshot using Groq.

        Args:
            market_data: Path to a market data file or raw OHLCV string.

        Returns:
            AI-generated signal summary (BUY / SELL / HOLD + reasoning).
        """
        if not self.api_key:
            logger.warning("Groq API key not configured for signal analysis")
            return ""

        path = Path(market_data) if isinstance(market_data, (str, Path)) else None
        if path and not path.exists():
            logger.error(f"Market data file not found: {market_data}")
            return ""

        try:
            async with httpx.AsyncClient() as client:
                with open(path, "rb") as f:
                    files = {
                        "file": (path.name, f),
                        "model": (None, "llama3-70b-8192"),
                    }
                    headers = {
                        "Authorization": f"Bearer {self.api_key}",
                    }

                    response = await client.post(
                        self.api_url,
                        headers=headers,
                        files=files,
                        timeout=60.0
                    )

                    response.raise_for_status()
                    data = response.json()
                    return data.get("text", "")

        except Exception as e:
            logger.error(f"Groq signal analysis error: {e}")
            return ""
