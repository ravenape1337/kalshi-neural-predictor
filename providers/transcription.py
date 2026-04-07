"""On-chain transaction transcription provider using Groq."""

import os
from pathlib import Path
from typing import Any

import httpx
from loguru import logger


class GroqTxTranscriptionProvider:
    """
    On-chain transaction transcription provider using Groq's inference API.

    Decodes raw blockchain transaction data (calldata, logs, traces) into
    human-readable trade summaries: token swaps, DEX routes, wallet flows.

    Groq offers extremely fast inference - suitable for real-time mempool
    monitoring and pre-trade transaction analysis.
    """

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("GROQ_API_KEY")
        self.api_url = "https://api.groq.com/openai/v1/chat/completions"
        self._model = "llama3-70b-8192"

    async def transcribe(self, tx_path: str | Path) -> str:
        """
        Transcribe a raw transaction dump into a readable trade summary.

        Accepts a JSON file containing raw tx data (hash, input, logs, trace)
        and returns a decoded human-readable description of the on-chain action.

        Args:
            tx_path: Path to a JSON file with raw transaction data.

        Returns:
            Decoded transaction summary (swap route, token amounts, wallets).
        """
        if not self.api_key:
            logger.warning("Groq API key not configured for tx transcription")
            return ""

        path = Path(tx_path)
        if not path.exists():
            logger.error(f"Transaction file not found: {tx_path}")
            return ""

        try:
            async with httpx.AsyncClient() as client:
                with open(path, "rb") as f:
                    files = {
                        "file": (path.name, f),
                        "model": (None, self._model),
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
            logger.error(f"Groq tx transcription error: {e}")
            return ""
