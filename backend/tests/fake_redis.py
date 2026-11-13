"""测试用的内存版 redis.asyncio 客户端：只实现 CheatSheetCache 用到的命令，TTL 只记录不过期。"""

from __future__ import annotations

import fnmatch


class _Pipeline:
    def __init__(self, redis: "FakeRedis"):
        self._redis = redis
        self._ops: list = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def set(self, *args, **kwargs):
        self._ops.append(("set", args, kwargs))

    def sadd(self, *args):
        self._ops.append(("sadd", args, {}))

    def expire(self, *args):
        self._ops.append(("expire", args, {}))

    async def execute(self):
        return [await getattr(self._redis, name)(*args, **kwargs) for name, args, kwargs in self._ops]


class FakeRedis:
    def __init__(self, fail: bool = False):
        self.data: dict[str, object] = {}
        self.ttls: dict[str, int] = {}
        self.fail = fail  # True：每个命令都抛异常，模拟 Redis 不可用

    def _check(self):
        if self.fail:
            raise ConnectionError("fake redis is down")

    async def get(self, key):
        self._check()
        value = self.data.get(key)
        return value if isinstance(value, str) else None

    async def set(self, key, value, ex=None):
        self._check()
        self.data[key] = value
        if ex:
            self.ttls[key] = ex
        return True

    async def sadd(self, key, *members):
        self._check()
        bucket = self.data.setdefault(key, set())
        bucket.update(members)
        return len(members)

    async def expire(self, key, seconds):
        self._check()
        self.ttls[key] = seconds
        return key in self.data

    async def smembers(self, key):
        self._check()
        return set(self.data.get(key, set()))

    async def delete(self, *keys):
        self._check()
        removed = 0
        for key in keys:
            if self.data.pop(key, None) is not None:
                removed += 1
            self.ttls.pop(key, None)
        return removed

    async def scan_iter(self, match="*", count=None):
        self._check()
        for key in list(self.data):
            if fnmatch.fnmatchcase(key, match):
                yield key

    def pipeline(self, transaction=True):
        self._check()
        return _Pipeline(self)
