import re
import os
import ast
import asyncio
import zstandard as zstd
from collections import deque
from typing import Optional, Dict, Any, List, Union, Literal, Tuple, cast, overload, Iterable, Iterator, AsyncIterable, AsyncGenerator
import anyio
from pathlib import Path

from KeyisBTools.models.serialization import serialize, deserialize, SerializableType

from .gnTransportProtocolParser import GNTransportProtocol, parse_gn_protocol
from .values import tablex_file_extension_to_inType
from ._data_pack import (
    pack_gnrequest,
    pack_gnrequest_header,
    unpack_gnrequest,
    unpack_gnrequest_header,
    pack_gnresponse,
    pack_gnresponse_header,
    unpack_gnresponse,
    unpack_gnresponse_header,
    unpack_temp_data_header,
    IncompleteGNFrameError,
    VFSDFrame,
    _Aracada_container_packer
    )


from .domains import GNDomain
from ..gwis.values import tablex_gwis_object_types_int_to_str



class Url:
    
    __slots__ = (
        "transport", "route", "scheme",
        "hostname", "port", "path", "params", "fragment", "isIp"
    )

    _re_hostport = re.compile(r"^(?P<host>\[[^\]]+\]|[a-zA-Z0-9.~<>\-_@]+)(?::(?P<port>\d+))?$", re.X)

    @overload
    def __init__(self): ...
    
    @overload
    def __init__(self, url: str): ...

    @overload
    def __init__(self, url: 'Url'): ...

    def __init__(self, url: Optional[Union[str, 'Url']] = None):
        self.transport: Optional[str] = None
        self.route: Optional[str] = None
        self.scheme: str = None # type: ignore
        self.hostname: str = None # type: ignore
        self.path: str = "/"
        self.params: Dict[str, Any] = {}
        self.fragment: Optional[str] = None
        self.isIp: bool = False

        if url:
            self.setUrl(url)

    def setUrl(self, url: Union[str, 'Url']):
        if isinstance(url, Url):
            self.transport = url.transport
            self.route = url.route
            self.scheme = url.scheme
            self.hostname = url.hostname
            self.path = url.path
            self.params = url.params
            self.fragment = url.fragment
            return
            
        proto, _, rest = url.partition("://")
        if not rest:
            raise ValueError(f"Invalid URL: {url}")

        if "~~" in proto:
            t, _, s = proto.partition("~~")
            self.transport, self.route, self.scheme = t, None, s or "gn"
        elif "~" in proto:
            parts = proto.split("~")
            if len(parts) == 3:
                self.transport, self.route, self.scheme = parts
            elif len(parts) == 2:
                self.transport, self.route, self.scheme = None, parts[0], parts[1]
            else:
                raise ValueError(f"Invalid protocol chain: {proto}")
        else:
            self.transport, self.route, self.scheme = None, None, proto or "gn"

        if not self.scheme:
            self.scheme = "gn"

        hostpath, _, frag = rest.partition("#")
        self.fragment = frag if frag != "" else None

        hostpath, _, query = hostpath.partition("?")
        if self.scheme == 'lib':
            host, self.path = 'libs.gn', hostpath
        elif "/" in hostpath:
            host, path = hostpath.split("/", 1)
            self.path = "/" + path
        else:
            host, self.path = hostpath, "/"

        if not host and self.scheme != "file":
            raise ValueError(f"Missing hostname in URL: {url}")

        if host:
            m = self._re_hostport.match(host)
            if not m:
                raise ValueError(f"Invalid hostname: {host}")
            self.hostname = m.group("host")
            if self.hostname.startswith("[") and self.hostname.endswith("]"):
                self.hostname = self.ip_to_ipv6(self.hostname[1:-1]) # type: ignore
                self.isIp = True
            else:
                self.isIp = False
            p = m.group("port")
            if p is not None:
                self.hostname = self.ip_and_port_to_ipv6_with_port(self.hostname, int(p))

        self.params = {}
        if query:
            for part in query.split("&"):
                if not part:
                    continue
                k, eq, v = part.partition("=")
                if not eq:
                    self.params[k] = None
                    continue
                try:
                    val = ast.literal_eval(v)
                except Exception:
                    val = v
                self.params[k] = val

    def _build_query(self) -> str:
        if not self.params:
            return ""
        out = []
        for k, v in self.params.items():
            if v is None:
                out.append(k)
            elif isinstance(v, str):
                out.append(f"{k}={v}")
            else:
                out.append(f"{k}={repr(v)}")
        return "&".join(out)

    def build(self, parts: List[str]) -> str:
        url = ""

        if "scheme" in parts or "transport" in parts or "route" in parts:
            if self.transport and self.route:
                proto = f"{self.transport}~{self.route}~{self.scheme}"
            elif self.transport and not self.route:
                proto = f"{self.transport}~~{self.scheme}"
            elif self.route and not self.transport:
                proto = f"{self.route}~{self.scheme}"
            else:
                proto = self.scheme or "gn"
            url += proto + "://"

        if "hostname" in parts and self.hostname:
            if self.isIp and not self.hostname.startswith("["):
                host = f"[{self.hostname}]"
            else:
                host = self.hostname
            url += host

        if "path" in parts and self.path:
            url += self.path

        if "params" in parts and self.params:
            q = self._build_query()
            if q:
                url += f"?{q}"

        if "fragment" in parts and self.fragment is not None:
            url += f"#{self.fragment}"

        return url

    def toString(self) -> str:
        return self.build(["transport", "route", "scheme", "hostname", "path", "params", "fragment"])

    def __str__(self):
        return self.toString()

    @staticmethod
    def ipv4_with_port_to_ipv6_with_port(ipv4: str) -> str:
        if ipv4.count(':') == 1:
            ip, port = ipv4.split(':')
            if ip == '127.0.0.1':
                return f'[::1]:{port}'
            else:
                return f'[::ffff:{ip}]:{port}'
        
        return ipv4
    
    @staticmethod
    def ip_and_port_to_ipv6_with_port(ip: str, port: int) -> str:
        if ':' not in ip:
            if ip == '127.0.0.1':
                return f'[::1]:{port}'
            else:
                return f'[::ffff:{ip}]:{port}'
        
        return f'[{ip}]:{port}'
    
    @staticmethod
    def ip_to_ipv6(ip: str) -> str:
        if ':' not in ip:
            if ip == '127.0.0.1':
                return '::1'
            else:
                return f'::ffff:{ip}'
        
        return ip
    
    @staticmethod
    def ipv6_with_port_to_ipv6_and_port(ipv6: str) -> Tuple[str, int]:
        i, p = ipv6.split(']:')
        return i[1:], int(p)


class FileObject:
    """
    # Объект сборки для файлов в ITP контейнер.

    :param path: `str` Путь к файлу для сборки. Если указано, будет использоваться для чтения данных при сборке.
    :param data: `bytes` Данные для сборки. Если указано, будет использоваться напрямую при сборке.
    :param inType: `str` Тип содержимого файла в соответствии с стандартом ITP interpreters (например, 'html', 'css', 'js', 'svg', 'png', 'py').
    """
    @overload
    def __init__(
        self,
        path: str | Path
    ) -> None: ...

    @overload
    def __init__(
        self,
        path: str | Path,
        inType: Union[Literal['html', 'css', 'js', 'svg', 'png', 'py'], str]
    ) -> None: ...

    @overload
    def __init__(
        self,
        data: bytes,
        inType: Union[Literal['html', 'css', 'js', 'svg', 'png', 'py'], str],
    ) -> None: ...

    def __init__(  # type: ignore
        self,
        path_or_data: Union[str | Path, bytes],
        inType: Optional[str] = None
    ) -> None:
        self._path: Optional[str | Path] = None
        self._data: Optional[bytes] = None
        self._inType: Optional[str] = None
        self._is_assembly: Optional[Tuple[bytes, str]] = None

        if isinstance(path_or_data, (str, Path)):
            self._path = path_or_data

            if inType is None:
                ext = os.path.splitext(str(path_or_data))[1]
                if ext.startswith('.'):
                    ext = ext[1:]
                guessed = tablex_file_extension_to_inType.get(ext)
                self._inType = guessed or 'bin'
            else:
                self._inType = inType

        elif isinstance(path_or_data, bytes):
            if inType is None:
                raise ValueError('Для данных bytes требуется указать inType')
            self._data = path_or_data
            self._inType = inType

        else:
            raise TypeError(f"path_or_data: ожидается str или bytes, получено {type(path_or_data)!r}")


    async def assembly(self) -> Tuple[bytes, str]:
        if self._is_assembly is not None:
            return self._is_assembly

        if self._data is None:
            if not isinstance(self._path, (str, Path)):
                raise Exception('Ошибка сборки файла -> Путь к файлу не str или Path')
            
            if not os.path.exists(self._path):
                raise Exception(f'Ошибка сборки файла -> Файл не найден {self._path}')

            try:
                async with await anyio.open_file(str(self._path), mode="rb") as file:
                    self._data = await file.read()
            except Exception as e:
                raise Exception(f'Ошибка сборки файла -> Ошиибка при чтении файла: {e}')

        self._is_assembly = (self._data, self._inType)

        return self._is_assembly # type: ignore
    
    @staticmethod
    def deserialize(data: bytes, inType: str):
        return FileObject(data, inType)
    
    async def toTempDataObject(self, interpreterType: int | str | None = None, interpretatorVersion: int = 0, compression_info: tuple[int, int, int, int] | None = None) -> 'TempDataObject':
        d, m = await self.assembly()

        if m.count(':') == 1 and '/' not in m: # one interpret with version
            m, v = m.rsplit(':', 1)
            v = int(v)
        else:
            v = 0

        tdo = TempDataObject.ITP(m if interpreterType is None else interpreterType, d, v if interpretatorVersion == 0 else interpretatorVersion, compression_info)
        return tdo

    async def _iter_data(self, chunk_size: int) -> AsyncGenerator[bytes, None]:
        if chunk_size <= 0:
            raise ValueError('chunk_size must be > 0')

        if self._data is not None:
            for i in range(0, len(self._data), chunk_size):
                yield self._data[i:i + chunk_size]
            return

        if not isinstance(self._path, (str, Path)):
            raise Exception('File assembly error -> Path is not str or Path')

        if not os.path.exists(self._path):
            raise Exception(f'File assembly error -> File not found {self._path}')

        try:
            async with await anyio.open_file(str(self._path), mode="rb") as file:
                while True:
                    chunk = await file.read(chunk_size)
                    if not chunk:
                        break
                    yield chunk
        except Exception as e:
            raise Exception(f'File assembly error -> File read error: {e}')

    async def toIterTempDataObject(
        self,
        interpreterType: int | str | None = None,
        interpretatorVersion: int = 0,
        compression_info: tuple[int, int, int, int] | None = None,
        chunk_size: int = 1024 * 1024
    ) -> AsyncGenerator[bytes, None]:
        m = cast(str, self._inType)

        if m.count(':') == 1 and '/' not in m: # one interpret with version
            m, v_raw = m.rsplit(':', 1)
            v = int(v_raw)
        else:
            v = 0

        header, compression_support = _Aracada_container_packer.encode_itp_header(
            m if interpreterType is None else interpreterType,
            v if interpretatorVersion == 0 else interpretatorVersion,
            compression_info
        )
        yield header

        on, use_map, alg, level = compression_support
        if not on:
            async for chunk in self._iter_data(chunk_size):
                if chunk:
                    yield chunk
            return

        if use_map:
            raise NotImplementedError("Pretrained map compression not implemented")
        if alg != 0:
            raise NotImplementedError(f"Unknown compression algorithm code: {alg}")

        cobj = _Aracada_container_packer._new_zstd_compressor(level).compressobj()
        async for chunk in self._iter_data(chunk_size):
            out = cobj.compress(chunk)
            if out:
                yield out

        tail = cobj.flush(zstd.COMPRESSOBJ_FLUSH_FINISH)
        if tail:
            yield tail


class STPContainer:
    __slots__ = ['version', 'payload', 'compression_info']
    def __init__(self, payload: SerializableType, version: int = 0, compression_info: tuple[int, int, int, int] | None = None) -> None:
        """
        # Контейнер для STP (Serializable Temporary Payload)

        :param payload: Полезная нагрузка в виде сериализуемого объекта, которая будет упакована в формате STP для использования с данным типом интерпретатора и версией.
        :param version: Версия интерпретатора. Например, `1`, `2` и т.д.
        :param compression_info: Информация о сжатии в виде кортежа (например, (algorithm, level, ...)). Если None, сжатие не используется.
        """
        self.version = version
        self.payload = payload
        self.compression_info = compression_info

    def serialize(self) -> bytes:
        return _Aracada_container_packer.encode_stp(serialize(self.payload), self.version, self.compression_info)

    @staticmethod
    def deserialize(data: bytes) -> 'STPContainer':
        r = _Aracada_container_packer.decode_stp(data)
        if r is None:
            raise ValueError('Invalid STP container data')
        version, payload_bytes, compression_info = r
        payload = deserialize(payload_bytes)
        return STPContainer(payload, version, compression_info)
    
class ITPContainer:
    __slots__ = ['interpreterType', 'interpretatorVersion', 'payload', 'compression_info']
    def __init__(self, interpreterType: int | str, payload: bytes, interpretatorVersion: int,  compression_info: tuple[int, int, int, int] | None = None) -> None:
        """
        # Контейнер для ITP (Interpretable Temporary Payload)

        :param interpreterType: Тип интерпретатора. Например, `js`, `html`, `py` и т.д. (как mime-type в http).
        :param interpretatorVersion: Версия интерпретатора. Например, `1`, `2` и т.д.
        :param payload: Полезная нагрузка в виде байтов, которая будет упакована в формате ITP для использования с данным типом интерпретатора и версией.
        :param compression_info: Информация о сжатии в виде кортежа (например, (algorithm, level, ...)). Если None, сжатие не используется.
        """
        self.interpreterType = interpreterType
        self.interpretatorVersion = interpretatorVersion
        self.payload = payload
        self.compression_info = compression_info
    
    def serialize(self) -> bytes:
        return _Aracada_container_packer.encode_itp(self.payload, self.interpreterType, self.interpretatorVersion, self.compression_info)
    
    @staticmethod
    def deserialize(data: bytes) -> 'ITPContainer':
        r = _Aracada_container_packer.decode_itp(data)
        if r is None:
            raise ValueError('Invalid ITP container data')
        interpreterType, interpretatorVersion, payload, compression_info = r
        return ITPContainer(interpreterType, payload, interpretatorVersion, compression_info)


class VFSDContainer:
    __slots__ = ['version', 'path', 'count', 'created_ns', 'updated_ns', 'epoch', 'payload', 'compression_info']

    def __init__(
        self,
        path: str,
        payload: Iterable[VFSDFrame] | None = None,
        version: int = 0,
        created_ns: int = 0,
        updated_ns: int = 0,
        epoch: int = 0,
        count: int | None = None,
        compression_info: tuple[int, int, int, int] | None = None,
    ) -> None:
        """
        # Контейнер VFSD (VFS Directory)

        Payload состоит из последовательных msgpack-фреймов. Каждый фрейм
        хранит tuple `(type, name, abs_id, updated_ns, payload)`.
        """
        if not isinstance(path, str):
            raise TypeError('path must be str')

        self.version = version
        self.path = path
        self.payload = [
            _Aracada_container_packer.normalize_vfsd_frame(frame)
            for frame in ([] if payload is None else payload)
        ]
        self.count = len(self.payload) if count is None else count
        self.created_ns = created_ns
        self.updated_ns = updated_ns
        self.epoch = epoch
        self.compression_info = compression_info

    @property
    def frames(self) -> list[VFSDFrame]:
        return self.payload

    def serialize(self) -> bytes:
        if len(self.payload) != self.count:
            raise ValueError(f'VFSD frame count mismatch: count={self.count}, payload={len(self.payload)}')
        return _Aracada_container_packer.encode_vfsd(
            self.payload,
            self.path,
            self.created_ns,
            self.updated_ns,
            self.epoch,
            self.version,
            self.compression_info,
        )

    @staticmethod
    def deserialize(data: bytes) -> 'VFSDContainer':
        version, path, count, created_ns, updated_ns, epoch, payload, compression_info = _Aracada_container_packer.decode_vfsd(data)
        return VFSDContainer(path, payload, version, created_ns, updated_ns, epoch, count, compression_info)

    @staticmethod
    def iterFramesFromPayload(payload: bytes | bytearray | memoryview, count: Optional[int] = None) -> Iterator[VFSDFrame]:
        emitted = 0
        for frame in _Aracada_container_packer.iter_vfsd_payload_frames(payload):
            emitted += 1
            yield frame
        if count is not None and emitted != count:
            raise ValueError(f'VFSD frame payload count mismatch: header={count}, payload={emitted}')

    @staticmethod
    def iterFramesFromChunks(chunks: Iterable[bytes | bytearray | memoryview], count: Optional[int] = None) -> Iterator[VFSDFrame]:
        unpacker = _Aracada_container_packer.new_vfsd_msgpack_unpacker()
        emitted = 0
        total = 0
        last_frame_end = 0
        for chunk in chunks:
            blob = bytes(chunk)
            if not blob:
                continue
            total += len(blob)
            unpacker.feed(blob)
            for frame in unpacker:
                normalized = _Aracada_container_packer.normalize_vfsd_frame(frame)
                last_frame_end = unpacker.tell()
                emitted += 1
                yield normalized
        if last_frame_end != total:
            raise ValueError('VFSD frame stream has trailing incomplete msgpack frame')
        if count is not None and emitted != count:
            raise ValueError(f'VFSD frame stream count mismatch: header={count}, payload={emitted}')

    @staticmethod
    async def aiterFramesFromChunks(chunks: AsyncIterable[bytes | bytearray | memoryview | None], count: Optional[int] = None) -> AsyncGenerator[VFSDFrame, None]:
        unpacker = _Aracada_container_packer.new_vfsd_msgpack_unpacker()
        emitted = 0
        total = 0
        last_frame_end = 0
        async for chunk in chunks:
            if chunk is None:
                raise ValueError('VFSD frame stream ended before payload was complete')
            blob = bytes(chunk)
            if not blob:
                continue
            total += len(blob)
            unpacker.feed(blob)
            for frame in unpacker:
                normalized = _Aracada_container_packer.normalize_vfsd_frame(frame)
                last_frame_end = unpacker.tell()
                emitted += 1
                yield normalized
        if last_frame_end != total:
            raise ValueError('VFSD frame stream has trailing incomplete msgpack frame')
        if count is not None and emitted != count:
            raise ValueError(f'VFSD frame stream count mismatch: header={count}, payload={emitted}')


class TempDataObject:
    __slots__ = ['_container']

    @overload
    def __init__(self,
                interpreterType: int | str,
                payload: bytes,
                interpretatorVersion: int = 0
    ) -> None: ...

    @overload
    def __init__(self,
                interpreterType: int | str,
                payload: bytes,
                interpretatorVersion: int = 0,
                compression_info: tuple[int, int, int, int] | None = None
    ) -> None: ...

    @overload
    def __init__(self,
                container: STPContainer | ITPContainer | VFSDContainer | bytes | None = None
    ) -> None:
        """
        # Временный объект данных

        :param container: Контейнер данных, который может быть контейнером или сериализованным контейнером (`bytes`).

        Если контейнер сериализован, то при запросе .container он будет распакован в контейнер.
        """
        ...
    
    def __init__(self, *args, **kwargs) -> None:
        self._container = None

        if 'container' in kwargs or len(args) == 1:
            container = kwargs.get('container', args[0] if args else None)
            if isinstance(container, (bytearray, memoryview)):
                container = bytes(container)
            self._container = container
            return

        interpreterType = kwargs.get('interpreterType', args[0] if len(args) > 0 else None)
        payload = kwargs.get('payload', args[1] if len(args) > 1 else None)
        interpretatorVersion = kwargs.get('interpretatorVersion', args[2] if len(args) > 2 else None)
        compression_info = kwargs.get('compression_info', args[3] if len(args) > 3 else None)

        if interpreterType is not None and payload is not None:
            if interpretatorVersion is None:
                interpretatorVersion = 0
            self._container = ITPContainer(interpreterType, payload, interpretatorVersion, compression_info)

    def setContainer(self, container: STPContainer | ITPContainer | VFSDContainer | bytes):
        if isinstance(container, (bytearray, memoryview)):
            container = bytes(container)
        self._container = container
    
    def serialize(self) -> bytes | None:
        """
        # Сериализация контейнера данных
        Сериализует контейнер данных, если он установлен в сериализованный объект `TempDataObject`.
        """
        if self._container is None:
            return None
        
        if isinstance(self._container, (bytes, bytearray, memoryview)):
            self._container = bytes(self._container)
            return self._container
        return self._container.serialize()
    
    @property
    def container(self) -> STPContainer | ITPContainer | VFSDContainer | None:
        """
        # Контейнер данных

        Возвращает контейнер данных, распаковывая его при необходимости. Если контейнер не установлен, возвращает None.
        """
        if self._container is None:
            return None

        if isinstance(self._container, (bytes, bytearray, memoryview)):
            self._unpack_container()
        
        return self._container # type: ignore

    @staticmethod
    def deserialize(data: bytes, unpack_container: bool = False) -> 'TempDataObject':
        tdo = TempDataObject(container=data)

        if unpack_container:
            tdo._unpack_container()

        return tdo
    
    def _unpack_container(self) -> STPContainer | ITPContainer | VFSDContainer:
        if self._container is None:
            raise ValueError('TempDataObject container is None')
        
        if isinstance(self._container, (bytes, bytearray, memoryview)):
            self._container = bytes(self._container)
            t = int.from_bytes(self._container[0:2], "big")
            if t == 1:  # ITP
                self._container = ITPContainer.deserialize(self._container)
            elif t == 2:  # STP
                self._container = STPContainer.deserialize(self._container)
            elif t == 3:  # VFSD
                self._container = VFSDContainer.deserialize(self._container)
            else:
                raise ValueError('Invalid TempDataObject data')
        
        return self._container
    
    @staticmethod
    def STP(payload: SerializableType, version: int = 0, compression_info: tuple[int, int, int, int] | None = None) -> 'TempDataObject':
        return TempDataObject(STPContainer(payload, version, compression_info))
    
    @staticmethod
    def ITP(interpreterType: int | str, payload: bytes, interpretatorVersion: int = 0, compression_info: tuple[int, int, int, int] | None = None) -> 'TempDataObject':
        return TempDataObject(ITPContainer(interpreterType, payload, interpretatorVersion, compression_info))

    @staticmethod
    def VFSD(
        path: str,
        payload: Optional[Iterable[VFSDFrame]] = None,
        version: int = 0,
        created_ns: int = 0,
        updated_ns: int = 0,
        epoch: int = 0,
        count: Optional[int] = None,
        compression_info: tuple[int, int, int, int] | None = None,
    ) -> 'TempDataObject':
        return TempDataObject(VFSDContainer(path, payload, version, created_ns, updated_ns, epoch, count, compression_info))
    
    def __repr__(self) -> str:
        return "<TempDataObject>"

class TempDataGroup:
    __slots__ = ['objects']
    def __init__(self, objects: list[TempDataObject] | None = None) -> None:
        """
        # Временная группа данных
        """
        self.objects = objects or []


_PAYLOAD_NOT_READY = object()
_DEFAULT_ITER_PAYLOAD_CHUNK_SIZE = 1024 * 1024


class _AsyncPayloadState:
    __slots__ = [
        'payloadSize', 'hasPayload', '_chunks', '_buffered_size', '_received', '_consumed',
        '_payload_complete', '_payload_incomplete', '_waiters',
        '_container_header', '_container_header_len', '_container_waiters', '_failure',
        '_consumer', '_materialized_payload', '_header_probe', '_header_probe_target'
    ]

    def __init__(
        self,
        payload_size: Optional[int] = 0,
        initial_payload: bytes | None = None,
        complete: bool = False,
        has_payload: Optional[bool] = None
    ) -> None:
        self.payloadSize = payload_size
        self.hasPayload = bool(
            has_payload
            if has_payload is not None
            else (payload_size is None or bool(payload_size) or initial_payload is not None)
        )
        self._chunks: deque[bytes] = deque()
        self._buffered_size = 0
        self._received = 0
        self._consumed = 0
        self._payload_complete = False
        self._payload_incomplete = False
        self._waiters: list[asyncio.Future[None]] = []
        self._container_header: object | STPContainer | ITPContainer | VFSDContainer | None = _PAYLOAD_NOT_READY
        self._container_header_len: Optional[int] = None
        self._container_waiters: list[asyncio.Future[None]] = []
        self._failure: Optional[Exception] = None
        self._consumer: Optional[Literal['stream', 'materialize']] = None
        self._materialized_payload: Optional[bytes] = None
        self._header_probe = bytearray()
        self._header_probe_target = 64

        if initial_payload is not None:
            blob = bytes(initial_payload)
            if blob:
                self._chunks.append(blob)
                self._buffered_size = len(blob)
                self._received = len(blob)
            self._try_parse_container_header()

        if complete:
            self.finish(True)

    @property
    def payloadComplete(self) -> bool:
        return self._payload_complete

    @property
    def payloadIncomplete(self) -> bool:
        return self._payload_incomplete

    def _materialize_complete_payload(self) -> bytes:
        if self._consumed:
            raise RuntimeError('Payload is already being streamed; full payload is no longer available')
        if not self._payload_complete:
            raise RuntimeError('Payload is not complete')
        self._claim_consumer('materialize')
        if self._materialized_payload is not None:
            return self._materialized_payload
        self._materialized_payload = b''.join(self._chunks)
        self._chunks.clear()
        if self._materialized_payload:
            self._chunks.append(self._materialized_payload)
        self._buffered_size = len(self._materialized_payload)
        self._consumed = 0
        return self._materialized_payload

    @property
    def headerReady(self) -> bool:
        return self._container_header is not _PAYLOAD_NOT_READY

    @property
    def containerHeaderLength(self) -> Optional[int]:
        return self._container_header_len

    def feed(self, data: bytes | bytearray | memoryview) -> None:
        if self._payload_complete or self._payload_incomplete:
            return

        chunk = bytes(data)
        if not chunk:
            return

        self.hasPayload = True
        self._chunks.append(chunk)
        self._buffered_size += len(chunk)
        self._received += len(chunk)

        if self.payloadSize is not None and self._received > self.payloadSize:
            self._failure = ValueError('Payload exceeds declared payloadSize')

        self._try_parse_container_header()
        self._notify_all()

    def fail(self, exc: Exception) -> None:
        self._failure = exc
        self._payload_incomplete = True
        self._notify_all()

    def finish(self, end_stream: bool) -> None:
        if not end_stream:
            self._payload_incomplete = True
            self._notify_all()
            return

        if self.payloadSize is not None and self._received != self.payloadSize:
            self._payload_incomplete = True
        else:
            self._payload_complete = True

        self._try_parse_container_header()
        self._notify_all()

    def _notify_all(self) -> None:
        waiters = self._waiters
        self._waiters = []
        for fut in waiters:
            if not fut.done():
                fut.set_result(None)

        if self._container_header is not _PAYLOAD_NOT_READY or self._payload_incomplete or self._failure is not None:
            waiters = self._container_waiters
            self._container_waiters = []
            for fut in waiters:
                if not fut.done():
                    fut.set_result(None)

    def _raise_failure(self) -> None:
        if self._failure is not None:
            raise self._failure

    def _try_parse_container_header(self) -> None:
        if self._container_header is not _PAYLOAD_NOT_READY:
            return

        if self._consumed:
            return

        if not self.hasPayload or self.payloadSize == 0:
            self._container_header = None
            self._container_header_len = 0
            return

        while True:
            self._fill_header_probe()
            if not self._header_probe:
                return

            try:
                header, header_len = unpack_temp_data_header(bytes(self._header_probe))
            except IncompleteGNFrameError:
                if self._payload_complete or self._payload_incomplete:
                    self._container_header = None
                    self._container_header_len = 0
                    return
                if len(self._header_probe) >= self._header_probe_target and self._header_probe_target < self._received:
                    self._header_probe_target = min(self._received, self._header_probe_target * 2)
                    continue
                return
            except Exception as exc:
                self._failure = exc
                return
            break

        if header['container_type'] == 1:
            container: STPContainer | ITPContainer | VFSDContainer = ITPContainer(
                header['interpreterType'],
                b'',
                header['interpretatorVersion'],
                header['compression_info']
            )
        elif header['container_type'] == 2:
            container = STPContainer(b'', header['interpretatorVersion'], header['compression_info'])
        elif header['container_type'] == 3:
            container = VFSDContainer(
                header['path'],
                [],
                header['version'],
                header['created_ns'],
                header['updated_ns'],
                header['epoch'],
                header['count'],
                header['compression_info'],
            )
        else:
            self._failure = ValueError(f"Unsupported container type: {header['container_type']}")
            return

        self._container_header = container
        self._container_header_len = header_len

    def _fill_header_probe(self) -> None:
        if len(self._header_probe) >= self._header_probe_target:
            return

        need = self._header_probe_target - len(self._header_probe)
        copied = 0
        seen = 0
        for chunk in self._chunks:
            chunk_len = len(chunk)
            if seen + chunk_len <= len(self._header_probe):
                seen += chunk_len
                continue

            start = max(0, len(self._header_probe) - seen)
            take = min(chunk_len - start, need - copied)
            if take <= 0:
                break
            self._header_probe.extend(chunk[start:start + take])
            copied += take
            seen += chunk_len
            if copied >= need:
                break

    def _claim_consumer(self, consumer: Literal['stream', 'materialize']) -> None:
        if self._consumer is None:
            self._consumer = consumer
            return
        if self._consumer != consumer:
            if self._consumer == 'stream' and consumer == 'materialize':
                raise RuntimeError('Payload is already being streamed; await payload/tdo is not allowed')
            raise RuntimeError('Payload is already being materialized; streaming is not allowed')

    def _has_progress(self, container_wait: bool = False) -> bool:
        if self._failure is not None or self._payload_complete or self._payload_incomplete:
            return True
        if container_wait:
            return self._container_header is not _PAYLOAD_NOT_READY
        return self._buffered_size > 0

    def _has_completion(self) -> bool:
        return self._failure is not None or self._payload_complete or self._payload_incomplete

    async def _wait_for_progress(self, container_wait: bool = False) -> None:
        self._raise_failure()

        loop = asyncio.get_running_loop()
        fut: asyncio.Future[None] = loop.create_future()
        waiters = self._container_waiters if container_wait else self._waiters
        waiters.append(fut)

        self._raise_failure()
        if self._has_progress(container_wait):
            if not fut.done():
                fut.set_result(None)
        await fut
        self._raise_failure()

    async def _wait_for_completion(self) -> None:
        self._raise_failure()

        loop = asyncio.get_running_loop()
        fut: asyncio.Future[None] = loop.create_future()
        self._waiters.append(fut)

        self._raise_failure()
        if self._has_completion():
            if not fut.done():
                fut.set_result(None)
        await fut
        self._raise_failure()

    async def get_raw_payload(self) -> Optional[bytes]:
        if not self.hasPayload:
            return None
        self._claim_consumer('materialize')
        while True:
            self._raise_failure()
            if self._payload_complete:
                return self._materialize_complete_payload()
            if self._payload_incomplete:
                return None
            await self._wait_for_completion()

    async def get_container_header(self) -> Optional[STPContainer | ITPContainer | VFSDContainer]:
        while True:
            self._raise_failure()
            if self._container_header is not _PAYLOAD_NOT_READY:
                return cast(Optional[STPContainer | ITPContainer | VFSDContainer], self._container_header)
            if self._consumer == 'stream' and self._consumed:
                raise RuntimeError('Payload stream has already been consumed; container header is no longer available')
            if self._payload_incomplete:
                return None
            await self._wait_for_progress(container_wait=True)

    def _pop_chunk(self, max_size: int) -> bytes:
        if max_size <= 0 or self._buffered_size <= 0:
            return b''

        first = self._chunks.popleft()
        if len(first) <= max_size:
            self._buffered_size -= len(first)
            self._consumed += len(first)
            return first

        out = first[:max_size]
        rest = first[max_size:]
        self._chunks.appendleft(rest)
        self._buffered_size -= len(out)
        self._consumed += len(out)
        return out

    async def _discard_bytes(self, size: int) -> bool:
        remaining = size
        while remaining > 0:
            self._raise_failure()
            if self._buffered_size > 0:
                chunk = self._pop_chunk(remaining)
                remaining -= len(chunk)
                continue
            if self._payload_complete:
                return False
            if self._payload_incomplete:
                return False
            await self._wait_for_progress()
        return True

    async def iter_bytes(self, chunk_size: int, *, require_container_header: bool, payload_only: bool) -> AsyncGenerator[Optional[bytes], None]:
        if chunk_size <= 0:
            raise ValueError('chunk_size must be > 0')

        compression_info = (0, 0, 0, 0)
        header_len = 0
        if require_container_header or payload_only:
            header = await self.get_container_header()
            if header is None:
                yield None
                return
            if payload_only:
                header_len = cast(int, self._container_header_len)
                compression_info = cast(Tuple[int, int, int, int], header.compression_info or (0, 0, 0, 0))

        if not self.hasPayload:
            return

        self._claim_consumer('stream')

        if payload_only and header_len:
            if not await self._discard_bytes(header_len):
                yield None
                return

        if payload_only and compression_info[0]:
            on, use_map, alg, level = compression_info
            if use_map:
                raise NotImplementedError('Pretrained map decompression not implemented')
            if alg != 0:
                raise NotImplementedError(f'Unknown compression algorithm code: {alg}')

            decompressor = zstd.ZstdDecompressor().decompressobj(write_size=chunk_size)
            decompressed = bytearray()

            while True:
                self._raise_failure()

                while self._buffered_size > 0:
                    compressed = self._pop_chunk(chunk_size)
                    try:
                        decompressed.extend(decompressor.decompress(compressed))
                    except zstd.ZstdError as exc:
                        raise ValueError(f'Decompression failed: {exc}') from exc

                    while len(decompressed) >= chunk_size:
                        yield bytes(decompressed[:chunk_size])
                        del decompressed[:chunk_size]

                if self._payload_complete:
                    try:
                        tail = decompressor.flush()
                    except zstd.ZstdError as exc:
                        raise ValueError(f'Decompression failed: {exc}') from exc
                    if tail:
                        decompressed.extend(tail)
                    if not decompressor.eof:
                        raise ValueError('Compressed payload ended before zstd frame was complete')

                    if decompressed:
                        yield bytes(decompressed)
                    return

                if self._payload_incomplete:
                    if decompressed:
                        yield bytes(decompressed)
                    yield None
                    return

                await self._wait_for_progress()

        while True:
            self._raise_failure()
            while self._buffered_size > 0:
                yield self._pop_chunk(chunk_size)

            if self._payload_complete:
                return

            if self._payload_incomplete:
                yield None
                return

            await self._wait_for_progress()


class _PayloadIterProxy:
    """
    # Прокси для потокового чтения payload

    Экземпляр этого класса доступен как `request.iter` и `response.iter`.

    Прокси не хранит собственных данных. Он только предоставляет удобный API
    поверх внутреннего состояния загрузки payload.

    Основная идея следующая:

    - `await obj.iter.header` ждёт только header контейнера `TempDataObject`
    - `obj.iter.raw(chunk_size)` отдаёт весь wire-payload целиком, включая header контейнера
    - `obj.iter.tdo(chunk_size)` тоже отдаёт wire-payload контейнера, но начинает работу
        только после того, как header контейнера уже полностью собран
    - `obj.iter.payload(chunk_size)` отдаёт только внутренний payload контейнера,
        без header контейнера, а если в header указана компрессия, то потоково
        декомпрессирует bytes перед выдачей
    Во всех итераторах `chunk_size` задаёт желаемый размер выдачи. Данные режутся
    не так, как пришли по сети, а именно по указанному размеру чанка, за исключением
    последнего чанка.

    Если stream завершился до получения полного payload, итератор завершится чанком
    `None`, а `await payload` / `await tdo` вернёт `None`.
    """
    __slots__ = ['_state']

    def __init__(self, state: _AsyncPayloadState) -> None:
        self._state = state

    @property
    def header(self):
        """
        # Header контейнера `TempDataObject`

        Awaitable-свойство, которое дожидается только header контейнера во входящем
        payload, не ожидая полной загрузки всего контейнера.

        Возвращаемое значение:

        - `ITPContainer` с пустым `payload`, если во входящем payload находится ITP
        - `STPContainer` с пустым `payload`, если во входящем payload находится STP
        - `None`, если stream завершился раньше, чем удалось получить полный header
          контейнера или если payload отсутствует

        Это свойство полезно, когда нужно рано узнать метаданные payload:

        - тип контейнера
        - тип интерпретатора ITP
        - версию контейнера
        - параметры compression header

        При этом сам payload контейнера может ещё продолжать приходить.

        Пример:

        ```python
        container_header = await request.iter.header
        ```
        """
        return self._state.get_container_header()

    def raw(self, chunk_size: int) -> AsyncGenerator[Optional[bytes], None]:
        """
        # Итератор по полному wire-payload

        Возвращает async generator, который отдаёт payload уровня `GNRequest` /
        `GNResponse` как есть, без какой-либо дополнительной интерпретации.

        Это значит, что в поток входят:

        - header контейнера `TempDataObject`
        - payload контейнера

        То есть фактически это сериализованный `TempDataObject` целиком.

        `chunk_size` определяет размер выдаваемых чанков. Данные будут нарезаны
        ровно по этому размеру, кроме последнего чанка.

        Если stream оборвался до полного payload, последним значением будет `None`.
        """
        return self._state.iter_bytes(chunk_size, require_container_header=False, payload_only=False)

    def tdo(self, chunk_size: int) -> AsyncGenerator[Optional[bytes], None]:
        """
        # Итератор по сериализованному контейнеру

        Возвращает async generator, который отдаёт сериализованный контейнер
        `TempDataObject` по чанкам.

        По содержимому это почти то же самое, что `raw()`, но есть важная разница:
        выдача начинается только после того, как header контейнера уже полностью
        разобран. Это позволяет сначала безопасно получить `await iter.header`, а затем
        читать сериализованный контейнер потоково.

        Используется, когда нужно работать именно с контейнером как с объектом wire-format,
        а не только с его внутренним payload.

        Если stream оборвался до полного payload, последним значением будет `None`.
        """
        return self._state.iter_bytes(chunk_size, require_container_header=True, payload_only=False)

    def payload(self, chunk_size: int) -> AsyncGenerator[Optional[bytes], None]:
        """
        # Итератор по payload контейнера

        Возвращает async generator, который отдаёт только внутренний payload контейнера,
        без header контейнера `TempDataObject`.

        Семантика:

        - для `ITP` это байты содержимого контейнера, например содержимое файла
        - для `STP` это тоже байты payload контейнера, но без автоматической
          десериализации в Python-объект

        То есть этот метод всегда возвращает `bytes`, а не уже распакованный объект.

        Перед началом выдачи метод дожидается полного header контейнера, чтобы точно
        знать, где начинается внутренний payload.

        Если stream оборвался до полного payload, последним значением будет `None`.
        """
        return self._state.iter_bytes(chunk_size, require_container_header=True, payload_only=True)


def _is_async_payload_source(value: Any) -> bool:
    return hasattr(value, '__aiter__') and not isinstance(value, (bytes, bytearray, memoryview, TempDataObject))



class GNRequest:
    """
    # Запрос для сети `GN`

        Объект запроса теперь поддерживает два режима работы с payload:

        1. Обычный режим

        Когда payload уже полностью доступен в памяти. В этом случае можно работать
        с `await request.payload`, `await request.tdo`, `request.serialize()` и так далее
        как с цельным объектом.

        2. Потоковый режим

        Когда request был создан по header, а payload ещё продолжает приходить из сети,
        либо когда исходящий payload передан как `AsyncIterable[bytes]`.

        В потоковом режиме:

        - обработчик может стартовать сразу после полного header `GNRequest`
        - `await request.payload` ждёт полный payload
        - `await request.tdo` ждёт полный сериализованный контейнер
        - `await request.iter.header` ждёт только header контейнера `TempDataObject`
        - `async for chunk in request.iter.payload(...)` позволяет читать payload контейнера
            без ожидания полной загрузки

        Если stream оборвался до полного payload, `await request.payload` и
        `await request.tdo` вернут `None`, а потоковые итераторы завершатся чанком `None`.
    """
    def __init__(
        self,
        method: str,
        url: Url,
        payload: TempDataObject | SerializableType | AsyncIterable[bytes] | None = None,
        cookies: dict | None = None,
        transport: str | None = None,
        route: str | None = None,
        origin: str | None = None,
        payloadSize: Optional[int] = None
    ):
        """
        # Создание запроса

        :param method: HTTP-подобный метод запроса (`get`, `post`, `put`, `delete`, ...).
        :param url: URL запроса в формате `Url`.
        :param payload:
            Полезная нагрузка запроса. Поддерживаются три режима:

            - `SerializableType` или `TempDataObject`: payload сразу считается готовым
            - `AsyncIterable[bytes]`: payload будет отправляться потоково по чанкам
            - `None`: запрос без payload

        :param cookies: Словарь cookies/метаданных запроса.
        :param transport: Транспортный протокол запроса.
        :param route: Route bucket запроса.
        :param origin: Origin страницы или источника запроса.
        :param payloadSize:
            Полная длина wire-payload в байтах, если отправитель хочет объявить ее заранее.
            Для `AsyncIterable[bytes]` можно оставить `None`: header будет содержать маркер неизвестной длины,
            а transport завершит payload по end_stream.

        Важно:

        - Если `payload` передан как `SerializableType`, он будет автоматически упакован
          в `TempDataObject.STP(...)`
        - Если `payload` передан как `AsyncIterable[bytes]`, предполагается, что это уже
          готовый wire-payload контейнера `TempDataObject`, а не Python-объект для упаковки
        """
        self._method: str = method
        self._url = url
        self._cookies: dict = cookies
        self._transport: str = transport
        self._route: str = route
        self._origin = origin

        self._tdo: TempDataObject | None = None
        self._payload_source: Optional[AsyncIterable[bytes]] = None
        self._payload_source_consumed = False

        if _is_async_payload_source(payload):
            self._payload_source = cast(AsyncIterable[bytes], payload)
            self._payload_state = _AsyncPayloadState(payload_size=payloadSize, has_payload=True)
        else:
            if isinstance(payload, TempDataObject):
                self._tdo = payload
            else:
                self._tdo = TempDataObject.STP(cast(SerializableType, payload))

            raw_payload = self._tdo.serialize() if self._tdo is not None else None
            self._payload_state = _AsyncPayloadState(
                payload_size=len(raw_payload) if raw_payload is not None else 0,
                initial_payload=raw_payload,
                complete=True,
                has_payload=raw_payload is not None
            )

        if self._cookies is None:
            self._cookies = {}

        if transport is None:
            self.setTransport()
        
        if route is None:
            self.setRoute()


        self.object = self.__object(self)
        """
        # Информация об объекте

        `Доступена только на сервере`
        """

        self.client = self.__client(self)
        """
        # Информация о клиенте

        `Доступена только на сервере`
        """

        self.__raw_payload_cache: bytes | None = None
        self.iter = _PayloadIterProxy(self._payload_state)
        """
        # Потоковый доступ к payload

        Через `request.iter` доступны потоковые методы чтения payload:

        - `await request.iter.header`
        - `request.iter.raw(chunk_size)`
        - `request.iter.tdo(chunk_size)`
        - `request.iter.payload(chunk_size)`

        Этот API предназначен для сценариев, где обработка начинается сразу после
        получения header `GNRequest`, а payload продолжает догружаться позже.
        """

    class __object:
        def __init__(self, request: 'GNRequest') -> None:
            self.__request = request
            self._data: dict = self.__request._cookies.setdefault('gn', {}).setdefault('gwis', {})
            
        
        @property
        def gwisid(self) -> int:
            """
            # ID объекта

            Возвращает уникальный идентификатор объекта в системе `GW`

            Этот идентификатор используется для управления объектами в системе.

            Может использоваться для идентификации пользователя.
            
            :return: int
            """
            return self._data.get("gwisid", 0)
        
        @property
        def sessionId(self) -> int:
            """
            # ID сессии

            Возвращает уникальный идентификатор сессии пользователя в сети `GN`
            
            Этот идентификатор используется для отслеживания состояния сессии пользователя в системе.

            Может использоваться для идентификации пользователя.
            
            :return: int
            """
            return self._data.get("session_id", 0)
        
        @property
        def nickname(self) -> str:
            """
            # Никнейм объекта

            Возвращает никнейм объекта в системе `GW`

            Никнейм используется для идентификации объекта в системе пользователями.

            Может использоваться для идентификации пользователя.

            :return: str
            """
            return self._data.get("nickname", "")

        @property
        def typeInt(self) -> int:
            """
            # Тип объекта int

            Возвращает тип объекта в системе `GW`
            
            Тип объекта используется для определения роли и функциональности объекта в системе.

            Возможные значения:
            - `0`: `GBN`
            - `2`: `Пользователь`
            - `3`: `Компания`
            - `4`: `Проект`
            - `5`: `Продукт`
            - `6`: `Сервис`
            - `7`: `Объект распределенного владения`

            :return: int
            """
            return self._data.get("object_type", 0)
        
        @property
        def type(self) -> Literal['user', 'service', 'gbn', 'company', 'project', 'app', 'doo'] | str:
            """
            # Тип объекта

            Возвращает тип объекта в системе `GW`
            
            Тип объекта используется для определения роли и функциональности объекта в системе.

            Возможные значения:
            - `0`: `GBN`
            - `2`: `Пользователь`
            - `3`: `Компания`
            - `4`: `Проект`
            - `5`: `Продукт`
            - `6`: `Сервис`
            - `7`: `Объект распределенного владения`

            :return: Union[Literal['user', 'service', 'gbn', 'company', 'project', 'app', 'doo'], str]
            """
            return tablex_gwis_object_types_int_to_str.get(self._data.get("object_type", 0), 'gbn')
        
        @property
        def viewingType(self) -> int:
            """
            # Тип просмотра

            Возвращает тип просмотра объекта в системе `GW`

            Тип просмотра может быть установлен объекту для определения уровня доступа к объекту.

            Возможные значения:
            - `0`: Просмотр доступен только владельцу объекта
            - `1`: Просмотр не ограничен
            - `2`: Просмотр только авторизованным пользователям
            - `3`: Просмотр только для официально подтвержденных пользователей 

            :return: int
            """
            return self._data.get("viewing_type", 0)

        @property
        def description(self) -> str:
            """
            # Описание объекта

            Возвращает описание объекта в системе `GW`

            Описание может содержать дополнительную информацию о объекте.

            :return: str
            """
            return self._data.get("description", "")

        @property
        def name(self) -> str:
            """
            # Имя объекта

            Возвращает имя объекта в системе `GW`

            ```python
            Имя НЕ может быть использовано для идентификации объекта в системе пользователями.
            ```

            Может использоваться для определения объекта ТОЛЬКО пользователями.

            :return: str
            """
            return self._data.get("name", "")
        
        @property
        def owner(self) -> int | None:
            """
            # `gwisid` владельца объекта

            Возвращает уникальный идентификатор `gwisid` владельца объекта в системе `GW`

            Этот идентификатор используется для определения владельца объекта.

            :return: int | None
            Если владелец не установлен, возвращает None.
            """
            return self._data.get("owner", None)
        
        @property
        def officiallyConfirmed(self) -> bool:
            """
            # Официально подтвержденный объект

            Возвращает `True`, если объект официально подтвержден в системе `GW`

            Официально подтвержденные объекты могут иметь дополнительные права и возможности.

            :return: bool
            """
            return self._data.get("of_conf", False)

    class __client:
        model_client_types: Dict[int, str] = {
                0: 'gn',
                1: 'net',
                2: 'server',
                4: 'client',
                5: 'local'
            }
        
        def __init__(self, request: 'GNRequest') -> None:
            self.__request = request
            self._data = self.__request._cookies.setdefault('client', {})

        @property
        def remote_addr(self) -> Tuple[str, int]:
            """
            # `Tuple(IP, port)` клиента
            
            :return: Tuple[str, int]
            """
            return self._data.get("remote_addr", ())
        
        @property
        def ip(self) -> str:
            """
            # IP клиента
            
            :return: str
            """
            return self._data.get("remote_addr", ())[0]
        
        @property
        def port(self) -> int:
            """
            # Port клиента
            
            :return: int
            """
            return self._data.get("remote_addr", ())[1]
        
        @property
        def type(self) -> Literal['net', 'client', 'server', 'local']:
            """
            # Тип клиента

            - `net` - Пользователи и другие службы сети `GN`

            - `client` - Пользователи напрямую. Без использования прокси серверов сети `GN`

            - `server` - Другие `origin` сервера сети `GN`

            - `local` - Локальные клиенты

            :return: Literal['net', 'client', 'server', 'local']
            """
            return self.model_client_types[self._data.get('client-type', 1)] # type: ignore
        
        @property
        def type_int(self) -> Literal[1, 4, 2, 5]:
            """
            # Тип клиента (int)

            - `1` - net - Пользователи и другие службы сети `GN`

            - `4` - client - Пользователи напрямую. Без использования прокси серверов сети `GN`

            - `2` - server - Другие `origin` сервера сети `GN`

            - `5` - local - Локальные клиенты
            
            :return: int
            """
            return self._data['client-type']

        @property
        def domain(self) -> str | None:
            """
            # Домен объекта

            Для пользователей домен строится `{gwisid}~gwis`

            `None`, если запрос не поддерживает подпись домена
            
            :return: str | None
            """
            return self._data.get("domain", None)

    def serialize(self, version: int = 0) -> bytes:
        """
        # Полная сериализация запроса

        Возвращает полностью сериализованный `GNRequest`, включая payload.

        Этот метод подходит только тогда, когда payload уже полностью находится в памяти.
        Если request был создан с потоковым исходящим payload (`AsyncIterable[bytes]`) и
        этот поток ещё не был материализован, метод бросит `TypeError`.

        Для потоковой отправки нужно использовать пару:

        - `serializeHeader()`
        - `iterSerializedPayload()`
        """
        if self._payload_source is not None and not self._payload_source_consumed:
            raise TypeError('Async payload source requires async send path')

        if self._transport is None:
            self.setTransport()
        if self._route is None:
            self.setRoute()

        cookies = {}
        if self._cookies is not None:
            cookies.update(self._cookies)

        raw_cookies = serialize(cookies) if cookies != {} else None
        if self._tdo is not None:
            payload = self._tdo.serialize()
        elif self.hasPayload:
            payload = self._payload_state._materialize_complete_payload()
        else:
            payload = None

        return pack_gnrequest(
            version,
            self._transport,
            self._route,
            self._method,
            self.url.toString().encode(),
            payload,
            raw_cookies
        )

    def serializeHeader(self, version: int = 0) -> bytes:
        """
        # Сериализация только header запроса

        Возвращает только header `GNRequest`, без payload.

        Header уже содержит длину payload или маркер неизвестной длины, поэтому принимающая сторона может:

        - создать объект `GNRequest`
        - немедленно передать его в обработку
        - продолжать догружать payload независимо от жизненного цикла handler

        Этот метод используется transport-слоем для header-first отправки.
        """
        if self._transport is None:
            self.setTransport()
        if self._route is None:
            self.setRoute()

        cookies = {}
        if self._cookies is not None:
            cookies.update(self._cookies)
        raw_cookies = serialize(cookies) if cookies != {} else None

        return pack_gnrequest_header(
            version,
            self._transport,
            self._route,
            self._method,
            self.url.toString().encode(),
            -1 if self.hasPayload and self.payloadSize is None else (self.payloadSize if self.hasPayload else None),
            raw_cookies
        )

    async def _materialize_payload_source(self) -> Optional[bytes]:
        """
        # Материализация исходящего потокового payload

        Внутренний helper, который полностью вычитывает `AsyncIterable[bytes]` источника
        payload в память и возвращает собранные bytes.

        Используется тогда, когда к payload request обращаются как к цельному объекту
        (`await request.payload`, `await request.tdo`), хотя сам request был создан с
        потоковым исходящим payload.

        Если длина фактически полученных байтов не совпадает с `payloadSize`, будет брошено
        исключение.
        """
        if self._payload_source is None or self._payload_source_consumed:
            return await self._payload_state.get_raw_payload()

        total = 0
        try:
            async for chunk in self._payload_source:
                if not isinstance(chunk, (bytes, bytearray, memoryview)):
                    raise TypeError('Async payload source must yield bytes')
                blob = bytes(chunk)
                total += len(blob)
                self._payload_state.feed(blob)

            self._payload_source_consumed = True
            expected = self._payload_state.payloadSize
            if expected is not None and total != expected:
                raise ValueError('Async payload source length does not match payloadSize')
            self._payload_state.finish(True)
        except Exception as exc:
            self._payload_source_consumed = True
            self._payload_state.fail(exc)
            raise

        raw = await self._payload_state.get_raw_payload()
        if raw is None:
            return None
        self.setSerializedPayload(raw)
        return raw

    async def iterSerializedPayload(self, chunk_size: int = _DEFAULT_ITER_PAYLOAD_CHUNK_SIZE) -> AsyncGenerator[bytes, None]:
        """
        # Потоковая выдача сериализованного payload

        Возвращает async generator, который отдаёт wire-payload запроса в виде bytes.

        Это именно payload уровня `GNRequest`, то есть сериализованный контейнер
        `TempDataObject` целиком. Header самого `GNRequest` сюда не входит.

        Метод используется transport-слоем при потоковой отправке:

        - сначала вызывается `serializeHeader()`
        - затем transport читает чанки из `iterSerializedPayload()`

        Если request хранит payload уже в памяти, генератор просто вернёт один готовый блок.
        Если payload задан как `AsyncIterable[bytes]`, генератор будет отдавать чанки по мере
        их поступления из этого источника.
        """
        if chunk_size <= 0:
            raise ValueError('chunk_size must be > 0')

        if self._payload_source is None:
            if self._tdo is not None:
                raw = self._tdo.serialize()
            elif self.hasPayload:
                if self._payload_state.payloadComplete:
                    raw = self._payload_state._materialize_complete_payload()
                else:
                    async for chunk in self._payload_state.iter_bytes(
                        chunk_size,
                        require_container_header=False,
                        payload_only=False
                    ):
                        if chunk is None:
                            raise RuntimeError('Incoming request payload ended before it could be forwarded')
                        if chunk:
                            yield chunk
                    return
            else:
                raw = None
            if raw:
                yield raw
            return

        if self._payload_source_consumed:
            if self._tdo is None and not self._payload_state.payloadComplete:
                raise RuntimeError('Async payload source was already consumed')
            raw = self._tdo.serialize() if self._tdo is not None else self._payload_state._materialize_complete_payload()
            if raw:
                yield raw
            return

        total = 0
        try:
            async for chunk in self._payload_source:
                if not isinstance(chunk, (bytes, bytearray, memoryview)):
                    raise TypeError('Async payload source must yield bytes')
                blob = bytes(chunk)
                total += len(blob)
                yield blob

            self._payload_source_consumed = True
            expected = self._payload_state.payloadSize
            if expected is not None and total != expected:
                raise ValueError('Async payload source length does not match payloadSize')
        except Exception as exc:
            self._payload_source_consumed = True
            self._payload_state.fail(exc)
            raise

    @staticmethod
    def deserialize(data: bytes) -> 'GNRequest':
        """
        # Полная десериализация запроса

        Декодирует полностью собранный `GNRequest` из bytes, включая payload.

        Этот метод используется, когда весь запрос уже доступен целиком. Для header-first
        сценария используйте `try_deserialize_header()`.
        """
        data = bytes(data)
        d = unpack_gnrequest(data)

        version =  d['version']

        if version == 0:
            transport =  d['transport']
            method =  d['method']
            route =  d['route']
            url =  d['url']
            cookies =  d['cookies']
            cookies = cast(dict, deserialize(cookies) if cookies is not None else None)
            
            payload = cast(bytes | None, d.get('payload'))

            if payload is not None:
                payload = TempDataObject.deserialize(payload, unpack_container=False)


            return GNRequest(
                transport=transport,
                route=route,
                method=method,
                url=Url(url.decode()),
                payload=payload,
                cookies=cookies
            )
        else:
            raise Exception(f'Unsupported GNRequest version: {version}')

    @staticmethod
    def try_deserialize_header(data: bytes) -> Optional[Tuple['GNRequest', int, Optional[int]]]:
        """
        # Попытка разобрать только header запроса

        Пытается декодировать header `GNRequest` из частично собранного буфера.

        :param data: Текущий накопленный буфер bytes.
        :return:
            - `None`, если байтов пока недостаточно даже для полного header
            - `(request, payload_offset, payload_length)`, если header уже полностью разобран

        Где:

        - `request` — уже созданный объект `GNRequest` без полного payload
        - `payload_offset` — смещение в буфере, с которого начинаются байты payload
        - `payload_length` — ожидаемая длина payload в байтах или `None`, если длина неизвестна до end_stream

        Это ключевая точка для раннего запуска обработчика по одному только header.
        """
        try:
            d, payload_offset = unpack_gnrequest_header(bytes(data))
        except IncompleteGNFrameError:
            return None

        cookies = cast(dict, deserialize(d['cookies']) if d['cookies'] is not None else None)

        request = GNRequest(
            transport=d['transport'],
            route=d['route'],
            method=d['method'],
            url=Url(d['url'].decode()),
            payload=TempDataObject(container=None),
            cookies=cookies
        )
        request._tdo = None
        request.__raw_payload_cache = None
        request._payload_state = _AsyncPayloadState(
            payload_size=cast(Optional[int], d.get('payload_length', 0)),
            has_payload=bool(d.get('payload_present', False))
        )
        request.iter = _PayloadIterProxy(request._payload_state)

        return request, payload_offset, cast(Optional[int], d.get('payload_length', 0))

    def setSerializedPayload(self, payload: bytes | bytearray | memoryview | None):
        """
        # Установить готовый сериализованный payload

        Принимает уже полностью собранный wire-payload контейнера `TempDataObject` и
        связывает его с request.

        Метод не предназначен для пользовательского кода маршрутов. Обычно его вызывает
        transport-слой после того, как payload полностью дочитан.
        """
        if payload is None:
            self._tdo = None
            self.__raw_payload_cache = None
            return
        blob = bytes(payload)
        self._tdo = TempDataObject.deserialize(blob, unpack_container=False)
        self.__raw_payload_cache = None

    def _feedIncomingPayload(self, payload: bytes | bytearray | memoryview) -> None:
        """
        # Добавить очередную часть входящего payload

        Внутренний метод transport-слоя. Добавляет новый фрагмент payload в буфер
        request без завершения загрузки.
        """
        self._payload_state.feed(payload)

    def _finishIncomingPayload(self, end_stream: bool) -> None:
        """
        # Завершить входящий payload

        Внутренний метод transport-слоя. Помечает payload как завершённый или неполный.

        - `end_stream=True` означает, что stream завершился штатно
        - `end_stream=False` означает, что payload считается неполным

        После штатного завершения метод только помечает payload завершенным. `tdo` создается лениво,
        если принимающая сторона явно запросит `await request.tdo`.
        """
        self._payload_state.finish(end_stream)

    def _assembly_server(self):
        d: str = self.client._data['domain']

        ct = None
        if d.endswith(('.origin.shield.gn', '~origin.shield.gn')) and self._cookies and self._cookies.get('gn', {}).get('net', {}).get('gn', False):
            ct = 1
        elif d.endswith('~gwis'):
            ct = 4
        elif GNDomain.isCore(d):
            ct = 0
        elif self.client.remote_addr and self.client.remote_addr[0] in ('::1', '127.0.0.1', '::ffff:127.0.0.1', 'localhost'):
            ct = 5
        else:
            ct = 2

        self.client._data['client-type'] = ct

    @property
    def origin(self) -> str | None:
        """
        # url страницы с которой был сделан запрос
        
        :return: str | None
        """
        return self._cookies.get("gn", {}).get('origin', None)

    @property
    def method(self) -> str:
        """
        # Метод запроса

        get, post, put, delete и т.д.
        """
        return self._method
    
    def setMethod(self, method: str):
        """
        # Метод запроса
        
        :param method: Метод запроса (get, post, put, delete и т.д.)
        """
        self._method = method
    
    @property
    def url(self) -> Url:
        """
        # URL запроса.
        """
        return self._url

    def setUrl(self, url: Url):
        """
        # URL запроса
        
        :param url: `URL` запроса в виде объекта `Url`.
        """
        self._url = url

    @property
    def payload(self):
        """
        # Полезная нагрузка запроса

        Awaitable-свойство.

        Использование:

        ```python
        data = await request.payload
        ```

        Возвращает уже распакованный payload контейнера:

        - `dict`, `list`, `str`, `int`, `bytes` и другие `SerializableType` для STP
        - `bytes` для ITP
        - `None`, если payload отсутствует или stream завершился неполностью

        Если payload ещё не догружен, свойство дождётся его полного получения.
        После первого успешного чтения результат кэшируется.
        """
        return self._get_payload()

    async def _get_payload(self) -> SerializableType | bytes | None:
        if self.__raw_payload_cache is not None:
            return self.__raw_payload_cache

        if self._payload_source is not None and not self._payload_source_consumed:
            raw = await self._materialize_payload_source()
            if raw is None:
                return None

        elif self._tdo is None:
            raw = await self._payload_state.get_raw_payload()
            if raw is None:
                return None
            self.setSerializedPayload(raw)

        if self._tdo is None or self._tdo.container is None:
            return None

        p = self._tdo.container.payload
        self.__raw_payload_cache = p
        return p

    @property
    def tdo(self):
        """
        # Временный объект данных запроса `TempDataObject`

        Awaitable-свойство.

        Использование:

        ```python
        tdo = await request.tdo
        ```

        Свойство возвращает готовый `TempDataObject`, когда весь wire-payload контейнера
        уже получен целиком.

        Если payload ещё догружается, свойство будет ждать.
        Если stream оборвался и полный payload собрать не удалось, вернёт `None`.
        """
        return self._get_tdo()

    async def _get_tdo(self) -> TempDataObject | None:
        if self._payload_source is not None and not self._payload_source_consumed:
            raw = await self._materialize_payload_source()
            if raw is None:
                return None

        elif self._tdo is None:
            raw = await self._payload_state.get_raw_payload()
            if raw is None:
                return None
            self.setSerializedPayload(raw)

        return self._tdo

    @tdo.setter
    def tdo(self, value: TempDataObject | None):
        """
        # Установка готового `TempDataObject`

        Setter полностью заменяет текущий payload request новым контейнером и сбрасывает
        все промежуточные буферы/кэш потокового состояния.

        Это означает, что после установки:

        - `payloadSize` и `payloadSize` будут пересчитаны
        - `request.iter` будет привязан к новому payload
        - кэш значения `await request.payload` будет сброшен
        """
        self._tdo = value
        self.__raw_payload_cache = None
        raw_payload = value.serialize() if value is not None else None
        self._payload_source = None
        self._payload_source_consumed = False
        self._payload_state = _AsyncPayloadState(
            payload_size=len(raw_payload) if raw_payload is not None else 0,
            initial_payload=raw_payload,
            complete=True,
            has_payload=raw_payload is not None
        )
        self.iter = _PayloadIterProxy(self._payload_state)

    @property
    def hasPayload(self) -> bool:
        return self._payload_state.hasPayload

    @property
    def payloadSize(self) -> Optional[int]:
        """
        # Размер wire-payload в байтах

        Возвращает длину payload уровня `GNRequest` в байтах или `None`, если длина неизвестна до end_stream.

        Это не размер уже распакованного Python-объекта, а длина сериализованного payload,
        который идёт после header `GNRequest`.
        """
        return self._payload_state.payloadSize


    @property
    def cookies(self) -> dict | None:
        return self._cookies
    
    @cookies.setter
    def cookies(self, value: dict | None):
        self._cookies = value

    def setCookies(self, cookies: dict):
        self._cookies = cookies
        
    @property
    def transportObject(self) -> GNTransportProtocol:
        """
        # Транспортный протокол (объект)

        `GN` протокол используется для подключения к сети `GN`.
        """
        return parse_gn_protocol(self._transport)

    @property
    def transport(self) -> str:
        """
        # Транспортный протокол.

        """
        return self._transport
    
    def setTransport(self, transport: str | None = None):
        """
        Устанавливает `GN` протокол.

        :param transport: `GN` протокол (например, '`gn:tcp:quik`', '`gn:quik:real`',..).

        Если не указан, используется `gn:quik:real`.
        """
        if transport is None:
            transport = 'gn:quik:real'
        self._transport = transport

    @property
    def route(self) -> str | None:
        """
        # Маршрут запроса.

        Маршрут используется для определения пути запроса в сети `GN`.

        Если маршрут не установлен, возвращает `None`.
        """
        return self._route
    
    def setRoute(self, route: str | None = None):
        """
        # Маршрут запроса.

        :param route: Маршрут запроса (например, `gn:net` или `api`).

        Если не указан, используется `api`.
        """
        if route is None:
            route = 'api'
        self._route = route


    def __repr__(self):
        return f"<GNRequest [{self._transport}]: [{self._method} {self._url}]>"

class GNResponse(Exception):
    """
    # Ответ на запрос для сети `GN`

        По возможностям работы с payload объект ответа симметричен `GNRequest`.

        `GNResponse` можно использовать как:

        - полностью собранный объект с обычным `await response.payload`
        - header-first объект, который был возвращён сразу после header, а payload ещё
            продолжает загружаться
        - исходящий потоковый ответ, если payload задан как `AsyncIterable[bytes]`

        В результате клиент может получить `GNResponse` сразу после header и только затем,
        при необходимости, ждать полный payload или читать его потоково через `response.iter.*`.
    """
    def __init__(self,
                 command: str | int | bool | bytes,
                 payload: SerializableType | 'TempDataObject' | AsyncIterable[bytes] | None = None,
                 cookies: dict | None = None,
                 payloadSize: Optional[int] = None
                 ):
        """
        # Создание ответа

        :param command: Команда ответа. `str`, `int`, `bool`, `bytes`.
        :param payload:
            Полезная нагрузка ответа. Поддерживаются те же режимы, что и у `GNRequest`:

            - `SerializableType` или `TempDataObject` для полностью готового payload
            - `AsyncIterable[bytes]` для потоковой исходящей отправки
            - `None` для ответа без payload

        :param cookies: Метаданные ответа.
        :param payloadSize:
            Полная длина wire-payload, если отправитель хочет объявить ее заранее.
            Для `AsyncIterable[bytes]` можно оставить `None`: header будет содержать маркер неизвестной длины.

        Важно: если `payload` передаётся как поток bytes, предполагается, что это уже
        сериализованный payload контейнера `TempDataObject`, а не Python-объект, который
        нужно дополнительно упаковать.
        """
        self._command = command
        self._cookies = cookies
        self.command = CommandObject(command)
        """
        # Команда запроса `CommandObject`
        """

        self._tdo: TempDataObject | None = None

        self._payload_source: Optional[AsyncIterable[bytes]] = None
        self._payload_source_consumed = False

        if _is_async_payload_source(payload):
            self._payload_source = cast(AsyncIterable[bytes], payload)
            self._payload_state = _AsyncPayloadState(payload_size=payloadSize, has_payload=True)
        else:
            if isinstance(payload, TempDataObject):
                self._tdo = payload
            else:
                tdo = TempDataObject.STP(cast(SerializableType, payload))
                self._tdo = tdo

            raw_payload = self._tdo.serialize() if self._tdo is not None else None
            self._payload_state = _AsyncPayloadState(
                payload_size=len(raw_payload) if raw_payload is not None else 0,
                initial_payload=raw_payload,
                complete=True,
                has_payload=raw_payload is not None
            )

        self.__raw_payload_cache: SerializableType | None = None
        self.iter = _PayloadIterProxy(self._payload_state)
        """
        # Потоковый доступ к payload ответа

        Полностью симметричен `request.iter`.
        """

    def serialize(self) -> bytes:
        """
        # Полная сериализация ответа

        Возвращает полностью сериализованный `GNResponse`, включая payload.

        Для потокового исходящего payload этот метод использовать нельзя до тех пор,
        пока поток не был полностью материализован.
        """
        if self._payload_source is not None and not self._payload_source_consumed:
            raise TypeError('Async payload source requires async send path')

        if self._cookies is not None:
            cookies = serialize(self._cookies)
        else:
            cookies = None

        if self._tdo is not None:
            payload = self._tdo.serialize()
        elif self.hasPayload:
            payload = self._payload_state._materialize_complete_payload()
        else:
            payload = None
        
        return pack_gnresponse(
            version=0,
            command=self._command,
            payload=payload,
            cookies=cookies
        )

    def serializeHeader(self) -> bytes:
        """
        # Сериализация только header ответа

        Возвращает header `GNResponse`, в котором уже закодированы:

        - command
        - cookies
        - длина payload

        Это позволяет клиенту получить объект ответа сразу после header и не ждать,
        пока весь payload будет доставлен.
        """
        if self._cookies is not None:
            cookies = serialize(self._cookies)
        else:
            cookies = None

        return pack_gnresponse_header(
            version=0,
            command=self._command,
            payload_length=-1 if self.hasPayload and self.payloadSize is None else (self.payloadSize if self.hasPayload else None),
            cookies=cookies
        )

    async def _materialize_payload_source(self) -> Optional[bytes]:
        """
        # Материализация потокового исходящего payload ответа

        Полностью вычитывает исходящий `AsyncIterable[bytes]` payload в память и
        возвращает собранный wire-payload.
        """
        if self._payload_source is None or self._payload_source_consumed:
            return await self._payload_state.get_raw_payload()

        total = 0
        try:
            async for chunk in self._payload_source:
                if not isinstance(chunk, (bytes, bytearray, memoryview)):
                    raise TypeError('Async payload source must yield bytes')
                blob = bytes(chunk)
                total += len(blob)
                self._payload_state.feed(blob)

            self._payload_source_consumed = True
            expected = self._payload_state.payloadSize
            if expected is not None and total != expected:
                raise ValueError('Async payload source length does not match payloadSize')
            self._payload_state.finish(True)
        except Exception as exc:
            self._payload_source_consumed = True
            self._payload_state.fail(exc)
            raise

        raw = await self._payload_state.get_raw_payload()
        if raw is None:
            return None
        self.setSerializedPayload(raw)
        return raw

    async def iterSerializedPayload(self, chunk_size: int = _DEFAULT_ITER_PAYLOAD_CHUNK_SIZE) -> AsyncGenerator[bytes, None]:
        """
        # Потоковая выдача сериализованного payload ответа

        Возвращает async generator, который отдаёт payload уровня `GNResponse`
        как bytes для transport-слоя.

        Header `GNResponse` сюда не входит. Только payload, который должен быть отправлен
        после header.
        """
        if chunk_size <= 0:
            raise ValueError('chunk_size must be > 0')

        if self._payload_source is None:
            if self._tdo is not None:
                raw = self._tdo.serialize()
            elif self.hasPayload:
                if self._payload_state.payloadComplete:
                    raw = self._payload_state._materialize_complete_payload()
                else:
                    async for chunk in self._payload_state.iter_bytes(
                        chunk_size,
                        require_container_header=False,
                        payload_only=False
                    ):
                        if chunk is None:
                            raise RuntimeError('Incoming response payload ended before it could be forwarded')
                        if chunk:
                            yield chunk
                    return
            else:
                raw = None
            if raw:
                yield raw
            return

        if self._payload_source_consumed:
            if self._tdo is None and not self._payload_state.payloadComplete:
                raise RuntimeError('Async payload source was already consumed')
            raw = self._tdo.serialize() if self._tdo is not None else self._payload_state._materialize_complete_payload()
            if raw:
                yield raw
            return

        total = 0
        try:
            async for chunk in self._payload_source:
                if not isinstance(chunk, (bytes, bytearray, memoryview)):
                    raise TypeError('Async payload source must yield bytes')
                blob = bytes(chunk)
                total += len(blob)
                yield blob

            self._payload_source_consumed = True
            expected = self._payload_state.payloadSize
            if expected is not None and total != expected:
                raise ValueError('Async payload source length does not match payloadSize')
        except Exception as exc:
            self._payload_source_consumed = True
            self._payload_state.fail(exc)
            raise
    
    @staticmethod
    def deserialize(data: bytes) -> 'GNResponse':
        """
        # Полная десериализация ответа

        Декодирует полностью собранный `GNResponse`, включая payload.

        Для header-first сценария используйте `try_deserialize_header()`.
        """
        data = bytes(data)
        u = unpack_gnresponse(data)
        
        cookies =  u['cookies']
        cookies = cast(dict, deserialize(cookies)) if cookies is not None else None
        
        payload = TempDataObject.deserialize(u['payload'], unpack_container=False) if u.get('payload') is not None else None
        
        return GNResponse(
            command=u['command'],
            payload=payload,
            cookies=cookies
        )

    @staticmethod
    def try_deserialize_header(data: bytes) -> Optional[Tuple['GNResponse', int, Optional[int]]]:
        """
        # Попытка разобрать только header ответа

        Пытается декодировать header `GNResponse` из частично собранного буфера.

        Возвращает:

        - `None`, если header ещё не полный
        - `(response, payload_offset, payload_length)`, если header уже собран

        Это позволяет вернуть объект ответа вызывающему коду сразу после header и
        продолжать догружать payload асинхронно.
        """
        try:
            d, payload_offset, payload_length = unpack_gnresponse_header(bytes(data))
        except IncompleteGNFrameError:
            return None

        cookies = cast(dict, deserialize(d['cookies'])) if d['cookies'] is not None else None

        response = GNResponse(
            command=d['command'],
            payload=TempDataObject(container=None),
            cookies=cookies
        )
        response._tdo = None
        response.__raw_payload_cache = None
        response._payload_state = _AsyncPayloadState(
            payload_size=payload_length,
            has_payload=bool(d.get('payload_present', False))
        )
        response.iter = _PayloadIterProxy(response._payload_state)

        return response, payload_offset, payload_length

    def setSerializedPayload(self, payload: bytes | bytearray | memoryview | None):
        """
        # Установить готовый сериализованный payload ответа

        Принимает уже полностью собранный wire-payload контейнера и связывает его
        с текущим объектом `GNResponse`.
        """
        if payload is None:
            self._tdo = None
            self.__raw_payload_cache = None
            return
        blob = bytes(payload)
        self._tdo = TempDataObject.deserialize(blob, unpack_container=False)
        self.__raw_payload_cache = None

    def _feedIncomingPayload(self, payload: bytes | bytearray | memoryview) -> None:
        """
        # Добавить очередной chunk входящего payload ответа

        Внутренний helper transport-слоя.
        """
        self._payload_state.feed(payload)

    def _finishIncomingPayload(self, end_stream: bool) -> None:
        """
        # Завершить входящий payload ответа

        Помечает payload ответа как полный или неполный.

        Если payload завершился штатно и полностью, метод только помечает поток завершенным.
        `TempDataObject` создается лениво, если принимающая сторона явно запросит `await response.tdo`.
        """
        self._payload_state.finish(end_stream)
    
    @property
    def tdo(self):
        """
        # `TempDataObject` ответа

        Awaitable-свойство.

        Возвращает готовый `TempDataObject` после полной сборки payload ответа.
        Если payload ещё догружается, свойство будет ждать. Если payload завершился
        неполно, вернёт `None`.
        """
        return self._get_tdo()

    async def _get_tdo(self) -> TempDataObject | None:
        if self._payload_source is not None and not self._payload_source_consumed:
            raw = await self._materialize_payload_source()
            if raw is None:
                return None

        elif self._tdo is None:
            raw = await self._payload_state.get_raw_payload()
            if raw is None:
                return None
            self.setSerializedPayload(raw)

        return self._tdo

    @tdo.setter
    def tdo(self, value: TempDataObject | None):
        """
        # Установка готового `TempDataObject` ответа

        Полностью заменяет текущий payload ответа новым контейнером и пересобирает
        внутреннее потоковое состояние вокруг этого контейнера.
        """
        self._tdo = value
        self.__raw_payload_cache = None
        raw_payload = value.serialize() if value is not None else None
        self._payload_source = None
        self._payload_source_consumed = False
        self._payload_state = _AsyncPayloadState(
            payload_size=len(raw_payload) if raw_payload is not None else 0,
            initial_payload=raw_payload,
            complete=True,
            has_payload=raw_payload is not None
        )
        self.iter = _PayloadIterProxy(self._payload_state)
    
    @property
    def payload(self):
        """
        # Полезная нагрузка ответа

        Awaitable-свойство.

        Использование:

        ```python
        data = await response.payload
        ```

        Возвращает уже распакованный payload контейнера ответа:

        - Python-объект для STP
        - `bytes` для ITP
        - `None`, если payload отсутствует или был получен неполностью

        При первом обращении свойство дожидается полной загрузки payload, если это
        необходимо, затем кэширует результат.
        """
        return self._get_payload()

    async def _get_payload(self) -> SerializableType | bytes | None:
        if self.__raw_payload_cache is not None:
            return self.__raw_payload_cache

        if self._payload_source is not None and not self._payload_source_consumed:
            raw = await self._materialize_payload_source()
            if raw is None:
                return None

        elif self._tdo is None:
            raw = await self._payload_state.get_raw_payload()
            if raw is None:
                return None
            self.setSerializedPayload(raw)

        if self._tdo is None or self._tdo.container is None:
            return None

        p = self._tdo.container.payload
        self.__raw_payload_cache = p
        return p
    
    @payload.setter
    def payload(self, value: SerializableType | bytes | None):
        raise Exception("Use tdo to set payload as TempDataObject")
    
    @property
    def cookies(self) -> dict | None:
        return self._cookies
    
    @cookies.setter
    def cookies(self, value: dict | None):
        self._cookies = value

    @property
    def hasPayload(self) -> bool:
        return self._payload_state.hasPayload

    @property
    def payloadSize(self) -> Optional[int]:
        """
        # Размер wire-payload ответа в байтах

        Возвращает длину payload уровня `GNResponse` в байтах, без header самого ответа,
        или `None`, если длина неизвестна до end_stream.
        """
        return self._payload_state.payloadSize
    
    def __repr__(self):
        return f"<GNResponse [{self._command}]>"
    
    def __str__(self) -> str:
        return f"[GNResponse]: {self._command}"
    
    async def __reprfull__(self):
        return f"<GNResponse [{self._command}]: payload: {await self.payload}: cookies: {self._cookies}>"


from .fastcommands import AllGNFastCommands, COMMAND_TREE, COMMAND_PREFIX

class _CommandPath:
    def __init__(self, cmdobj: "CommandObject", path: tuple[str, ...]):
        self._cmdobj = cmdobj
        self._path = path

    def __getattr__(self, item: str):
        new_path = self._path + (item,)
        return self._cmdobj._build(new_path)

    def __bool__(self) -> bool:
        return self._cmdobj._check_path_raw(self._path)


class CommandObject(AllGNFastCommands):
    def __init__(self, value: Union[str, int, bool, bytes]):
        if not isinstance(value, (str, int, bool, bytes)):
            raise TypeError("Command must be str, int, bool or bytes")
        self.value = value

    def __getattribute__(self, name: str):
        # 0. Специальный случай: c.ok -> общий bool по значению
        if name == "ok":
            return bool(self)

        # 1. системные поля
        if name.startswith("_") or name in ("value", "__class__"):
            return object.__getattribute__(self, name)

        # 2. пробуем найти вложенный класс-команду
        cls = object.__getattribute__(self, "__class__")
        cls_attr = getattr(cls, name, None)

        # если это именно класс команды, то используем его _command_path
        if isinstance(cls_attr, type):
            path = getattr(cls_attr, "_command_path", None)
            if path is not None:
                return self._build(path)

        # 3. иначе — это групповая ветка (app, transport, dns, cors, ...)
        return _CommandPath(self, (name,))

    # =============== CORE ==================

    def _build(self, path: tuple[str, ...]):
        # конечная команда
        if path in COMMAND_TREE:
            return self.value == COMMAND_TREE[path]

        # группа команд
        if path in COMMAND_PREFIX:
            return _CommandPath(self, path)

        raise AttributeError(path)

    def _check_path_raw(self, path: tuple[str, ...]) -> bool:
        # конечная команда
        if path in COMMAND_TREE:
            return self.value == COMMAND_TREE[path]

        # группа
        if path in COMMAND_PREFIX:
            for sub in COMMAND_PREFIX[path]:
                if sub in COMMAND_TREE and self.value == COMMAND_TREE[sub]:
                    return True
        return False

    def _check_path(self, path: tuple[str, ...]) -> bool:
        return self._check_path_raw(path)

    # =======================================

    def __contains__(self, cls) -> bool:
        return self.value == cls.cls_command

    def __eq__(self, other) -> bool:
        if isinstance(other, CommandObject):
            return self.value == other.value
        return self.value == other

    def __ne__(self, other) -> bool:
        return not self.__eq__(other)

    def __bool__(self) -> bool:
        """
        Общая семантика "успеха" команды:
        True, 200, 'ok', '...:ok', '...:200' -> True
        bytes -> как стандартный bool(bytes)
        всё остальное -> False
        """
        v = self.value
        if isinstance(v, bool):
            return v
        elif isinstance(v, int):
            return v == 200
        elif isinstance(v, str):
            return v == "ok" or v.endswith((":ok", ":200"))
        else:
            # bytes и другие типы — по стандартной логике bool()
            return bool(v)


    def __str__(self) -> str:
        v = self.value
        if isinstance(v, str):
            return v
        elif isinstance(v, bool):
            return "ok" if v else "gn:error:false"
        elif isinstance(v, int):
            return "ok" if v == 200 else f"gn:error:{v}"
        else:
            return v.decode("utf-8")

    def __repr__(self):
        return f"CommandObject({self.value!r})"

    def _serializebleType(self):
        if isinstance(self.value, str):
            if self.value == "ok":
                return True
            return self.value
        return self.value



