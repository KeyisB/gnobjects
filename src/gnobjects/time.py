import time
from datetime import datetime, timezone


class GNTime:
    _default_base = int(datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp())
    _set: datetime | None = None

    @classmethod
    def _get_base(cls) -> int:
        if cls._set is None:
            return cls._default_base
        return int(cls._set.replace(tzinfo=timezone.utc).timestamp())

    @classmethod
    def fromUNIX(cls, unix: float | int | None = None) -> float:
        if unix is None:
            unix = time.time()
        base = cls._get_base()

        if cls._set is None:
            return base - float(unix)
        else:
            return float(unix) - base

    @classmethod
    def toUNIX(cls, gn: float) -> float:
        base = cls._get_base()

        if cls._set is None:
            return base - float(gn)
        else:
            return base + float(gn)

