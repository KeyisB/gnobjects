import re
import threading
from typing import Iterable, Optional, List, NamedTuple, Dict
from functools import lru_cache
from collections import OrderedDict

# ------------------------------ версии ---------------------------------

_VERSION_RE = re.compile(r"^\d+(?:\.\d+)*(?:-\d+(?:\.\d+)*)?$").match
_is_ver = _VERSION_RE

def _to_list(v: Optional[str]) -> List[int]:
    if not v:
        return []
    return [int(x) for x in v.split(".")]

def _cmp(a: List[int], b: List[int]) -> int:
    n = max(len(a), len(b))
    a += [0] * (n - len(a))
    b += [0] * (n - len(b))
    return (a > b) - (a < b)

class _VersionRange:
    """Одиночная версия, диапазон a-b или wildcard(None)."""
    __slots__ = ("raw", "kind", "lo", "hi", "single")

    def __init__(self, raw: Optional[str]):
        self.raw = None if (raw is None or (isinstance(raw, str) and raw.lower() == "last")) else raw
        if self.raw is None:
            self.kind = "wild"
            return
        if "-" in self.raw:
            self.kind = "range"
            lo, hi = self.raw.split("-", 1)
            self.lo = _to_list(lo)
            self.hi = _to_list(hi)
        else:
            self.kind = "single"
            self.single = _to_list(self.raw)

    def contains(self, ver: Optional[str]) -> bool:
        if self.kind == "wild":
            return True
        if ver is None or (isinstance(ver, str) and ver.lower() == "last"):
            return False
        v = _to_list(ver)
        if self.kind == "single":
            return _cmp(self.single[:], v) == 0
        return _cmp(self.lo[:], v) <= 0 <= _cmp(v, self.hi[:])

    def __str__(self) -> str:
        return self.raw or "None"

# ------------------------------ паттерны --------------------------------

class _Pat(NamedTuple):
    gn_ver: _VersionRange
    p1_name: Optional[str]
    p1_ver: _VersionRange
    p1_need_last: bool
    p2_name: Optional[str]
    p2_ver: _VersionRange
    p2_need_last: bool

@lru_cache(maxsize=2048)
def _compile_full_pattern(pat: str) -> _Pat:
    t = pat.split(":")
    gn_ver = _VersionRange(None)
    if t and t[0].lower() == "gn":
        t.pop(0)
        gn_ver = _VersionRange(t.pop(0)) if t and (_is_ver(t[0]) or t[0].lower() == "last") else _VersionRange(None)

    p2_name = p2_ver = p1_name = p1_ver = None
    p2_need_last = p1_need_last = False

    if t:
        if _is_ver(t[-1]) or t[-1].lower() == "last":
            p2_ver = _VersionRange(t.pop())
        else:
            p2_need_last = True
        p2_name = t.pop() if t else None

    if t:
        if _is_ver(t[-1]) or t[-1].lower() == "last":
            p1_ver = _VersionRange(t.pop())
        else:
            p1_need_last = True
        p1_name = t.pop() if t else None

    if t:
        raise ValueError(f"bad pattern {pat!r}")

    return _Pat(
        gn_ver=gn_ver,
        p1_name=None if p1_name is None else p1_name.lower(),
        p1_ver=p1_ver or _VersionRange(None),
        p1_need_last=p1_need_last,
        p2_name=None if p2_name is None else p2_name.lower(),
        p2_ver=p2_ver or _VersionRange(None),
        p2_need_last=p2_need_last,
    )

class _LeafPat(NamedTuple):
    name: Optional[str]
    ver: _VersionRange
    need_last: bool

@lru_cache(maxsize=4096)
def _compile_leaf_pattern(pat: str) -> _LeafPat:
    """
    pattern ::= NAME | NAME ':' VERSION | VERSION
    """
    if ":" not in pat:
        if _is_ver(pat) or pat.lower() == "last":
            return _LeafPat(name=None, ver=_VersionRange(pat), need_last=False)
        return _LeafPat(name=pat.lower(), ver=_VersionRange(None), need_last=True)

    name, ver = pat.split(":", 1)
    name = name.lower() or None
    need_last = False
    if not ver:
        need_last = True
        ver_range = _VersionRange(None)
    else:
        ver_range = _VersionRange(ver)
    return _LeafPat(name=name, ver=ver_range, need_last=need_last)

# ------------------------ протокол + быстрые флаги ----------------------

class _LeafProto:
    __slots__ = ("_name", "_ver_raw", "dev", "real", "quik", "quiks")

    def __init__(self, name: str, ver_raw: Optional[str]):
        self._name = name
        self._ver_raw = None if (ver_raw is None or (isinstance(ver_raw, str) and ver_raw.lower() == "last")) else ver_raw
        # популярные флаги (O(1))
        nm = self._name
        self.dev = (nm == "dev")
        self.real = (nm == "real")
        self.quik = (nm == "quik")
        self.quiks = (nm == "quiks")

    def protocol(self) -> str:
        return self._name

    def version(self) -> Optional[str]:
        return self._ver_raw  # None == версия не указана

    def matches_any(self, *patterns) -> bool:
        if len(patterns) == 1 and not isinstance(patterns[0], str):
            patterns_iter = patterns[0]
        else:
            patterns_iter = patterns

        nm = self._name
        vr = self._ver_raw
        for p in patterns_iter:
            pat = _compile_leaf_pattern(p)
            if pat.name is not None and pat.name != nm:
                continue
            if pat.need_last:
                if vr is not None:
                    continue
                return True
            if pat.ver.contains(vr):
                return True
        return False

    def __repr__(self) -> str:
        return f"<Proto {self._name}:{self._ver_raw or 'None'}>"

class GNTransportProtocol:
    """
    Формат: gn[:gnVer]:transport[:ver1]:route[:ver2]
    Части: systemProtocol / transportProtocol / routeProtocol
    Все доступы O(1) после первого парса (из общего кэша).
    """
    __slots__ = (
        "raw",
        # system
        "systemProtocol_name", "systemProtocol_ver_raw", "systemProtocol",
        # transport
        "transportProtocol_name", "transportProtocol_ver_raw", "transportProtocol",
        # route
        "routeProtocol_name", "routeProtocol_ver_raw", "routeProtocol",
    )

    @staticmethod
    def _take_ver(tokens: List[str]) -> Optional[str]:
        return tokens.pop(0) if tokens and (_is_ver(tokens[0]) or tokens[0].lower() == "last") else None

    def __init__(self, raw: str):
        self.raw = raw
        self._parse()

    def _parse(self) -> None:
        t = self.raw.split(":")
        if not t or t[0].lower() != "gn":
            raise ValueError("must start with 'gn'")
        t.pop(0)

        self.systemProtocol_ver_raw = self._take_ver(t)
        self.systemProtocol_name = "gn"
        self.systemProtocol = _LeafProto("gn", self.systemProtocol_ver_raw)

        if not t:
            raise ValueError("missing transport proto")
        self.transportProtocol_name = t.pop(0).lower()
        self.transportProtocol_ver_raw = self._take_ver(t)
        self.transportProtocol = _LeafProto(self.transportProtocol_name, self.transportProtocol_ver_raw)

        if not t:
            raise ValueError("missing route proto")
        self.routeProtocol_name = t.pop(0).lower()
        self.routeProtocol_ver_raw = self._take_ver(t)
        self.routeProtocol = _LeafProto(self.routeProtocol_name, self.routeProtocol_ver_raw)

        if t:
            raise ValueError(f"extra tokens: {t!r}")

    def structure(self) -> dict:
        return {
            "systemProtocol": {"version": self.systemProtocol.version()},
            self.transportProtocol_name: {"version": self.transportProtocol.version()},
            self.routeProtocol_name: {"version": self.routeProtocol.version()},
        }

    def matches_any(self, patterns: Iterable[str]) -> bool:
        gv = self.systemProtocol_ver_raw
        c_name, c_ver = self.transportProtocol_name, self.transportProtocol_ver_raw
        r_name, r_ver = self.routeProtocol_name, self.routeProtocol_ver_raw

        for pat in patterns:
            gn_v, p1n, p1v, p1need, p2n, p2v, p2need = _compile_full_pattern(pat)

            if not gn_v.contains(gv):
                continue

            if p1n and p1n != c_name:
                continue
            if p1need:
                if c_ver is not None:
                    continue
            elif not p1v.contains(c_ver):
                continue

            if p2n and p2n != r_name:
                continue
            if p2need:
                if r_ver is not None:
                    continue
            elif not p2v.contains(r_ver):
                continue

            return True
        return False

    def __repr__(self) -> str:
        return (f"<GNTransportProtocol system:{self.systemProtocol.version() or 'None'} "
                f"{self.transportProtocol_name}:{self.transportProtocol.version() or 'None'} "
                f"{self.routeProtocol_name}:{self.routeProtocol.version() or 'None'}>")

# --------------------------- общий LRU-кэш по байтам ---------------------

class GNProtocolParser:
    """
    Менеджер кэша распарсенных GNTransportProtocol.
    - Общий для процесса.
    - Лимит по размеру (байты), eviction = LRU.
    """
    __slots__ = ("_lock", "_cache", "_sizes", "_total_bytes", "max_cache_bytes")

    def __init__(self, max_cache_bytes: int = 1 << 20):
        self._lock = threading.RLock()
        self._cache: "OrderedDict[str, GNTransportProtocol]" = OrderedDict()
        self._sizes: Dict[str, int] = {}
        self._total_bytes = 0
        self.max_cache_bytes = max_cache_bytes

    def _approx_size(self, p: GNTransportProtocol) -> int:
        # быстрая оценка: длины всех строк + небольшой оверхед
        s = 64  # базовый оверхед объекта
        s += len(p.raw)
        s += len(p.systemProtocol_name)
        s += len(p.transportProtocol_name)
        s += len(p.routeProtocol_name)
        if p.systemProtocol_ver_raw: s += len(p.systemProtocol_ver_raw)
        if p.transportProtocol_ver_raw: s += len(p.transportProtocol_ver_raw)
        if p.routeProtocol_ver_raw: s += len(p.routeProtocol_ver_raw)
        return s

    def _touch(self, key: str) -> None:
        # переместить в конец как «самый недавно использованный»
        self._cache.move_to_end(key, last=True)

    def _evict_if_needed(self) -> None:
        while self._total_bytes > self.max_cache_bytes and self._cache:
            k, _ = self._cache.popitem(last=False)  # LRU
            sz = self._sizes.pop(k, 0)
            self._total_bytes -= sz

    def get(self, raw: str) -> GNTransportProtocol:
        p = self._cache.get(raw)
        if p is not None:
            self._cache.move_to_end(raw, last=True)
            return p

        # медленный путь: редкий miss
        parsed = GNTransportProtocol(raw)
        sz = self._approx_size(parsed)
        with self._lock:
            existing = self._cache.get(raw)
            if existing is not None:
                self._cache.move_to_end(raw, last=True)
                return existing
            self._cache[raw] = parsed
            self._sizes[raw] = sz
            self._total_bytes += sz
            self._evict_if_needed()
        return parsed


# единый экземпляр (общий кэш)
GN_PARSER = GNProtocolParser(max_cache_bytes=8 << 20)  # 8 MB по умолчанию

def parse_gn_protocol(raw: str) -> GNTransportProtocol:
    return GN_PARSER.get(raw)
