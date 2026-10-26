"""Client for the language model through ProxyAPI (OpenAI-compatible chat completions)."""
import asyncio
import logging

import aiohttp

log = logging.getLogger("llm")


class LLMError(RuntimeError):
    pass


class LLM:
    def __init__(self, session: aiohttp.ClientSession, key: str, model: str, base_url: str) -> None:
        self._session = session
        self._key = key
        self.model = model
        self._url = f"{base_url}/chat/completions"

    async def chat(self, messages: list[dict], tools: list[dict] | None = None, max_tokens: int = 450) -> dict:
        body: dict = {"model": self.model, "messages": messages, "temperature": 0.3, "max_tokens": max_tokens}
        if tools:
            body["tools"] = tools
        headers = {"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"}

        last_error = "unknown error"
        for attempt in range(2):
            try:
                async with self._session.post(
                    self._url, json=body, headers=headers, timeout=aiohttp.ClientTimeout(total=45)
                ) as response:
                    data = await response.json(content_type=None)
                    if response.status == 200:
                        return data["choices"][0]["message"]
                    last_error = f"HTTP {response.status}: {str(data)[:200]}"
                    retryable = response.status in (429, 500, 502, 503, 504)
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                retryable = True
            if attempt == 0 and retryable:
                log.warning("LLM call failed (%s), retrying", last_error)
                await asyncio.sleep(2)
                continue
            break
        raise LLMError(last_error)
