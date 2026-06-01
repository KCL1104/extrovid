"""HTTP with retry/backoff for flaky provider calls (DashScope rate limits / 5xx).

Retries 429 + 5xx + transport errors with exponential backoff, honoring Retry-After.
``client`` is injectable so tests can pass an httpx MockTransport.
"""

import asyncio

import httpx

from app.core.config import get_settings

_RETRYABLE = {429, 500, 502, 503, 504}


async def request_with_retry(
    method: str,
    url: str,
    *,
    headers: dict | None = None,
    json: dict | None = None,
    timeout_sec: float = 120.0,
    client: httpx.AsyncClient | None = None,
) -> httpx.Response:
    s = get_settings()
    retries = s.http_max_retries
    delay = s.http_retry_base_sec
    owns = client is None
    client = client or httpx.AsyncClient(timeout=timeout_sec)
    try:
        resp: httpx.Response | None = None
        for attempt in range(retries + 1):
            try:
                resp = await client.request(method, url, headers=headers, json=json)
            except httpx.TransportError:
                if attempt >= retries:
                    raise
                await asyncio.sleep(delay)
                delay *= 2
                continue
            if resp.status_code in _RETRYABLE and attempt < retries:
                ra = resp.headers.get("retry-after")
                wait = float(ra) if (ra and ra.replace(".", "", 1).isdigit()) else delay
                await asyncio.sleep(min(wait, 30.0))
                delay *= 2
                continue
            return resp
        return resp  # type: ignore[return-value]
    finally:
        if owns:
            await client.aclose()
