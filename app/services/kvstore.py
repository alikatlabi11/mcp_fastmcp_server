# app/services/kvstore.py
from typing import Optional

import redis


class KvService:
    """
    Simple Redis-backed KV with optional TTL. Synchronous client for simplicity.
    """

    def __init__(self, url: str):
        self._client = redis.from_url(url, decode_responses=True)

    def put(self, key: str, value: str, ttl_sec: Optional[int] = None) -> str:
        if ttl_sec:
            self._client.set(key, value, ex=int(ttl_sec))
        else:
            self._client.set(key, value)
        return "OK"

    def get(self, key: str) -> Optional[str]:
        return self._client.get(key)
