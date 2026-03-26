import re
import os
import ast
from typing import Optional, Dict, Any, List, Union, Literal, Tuple, cast, overload
import anyio
from pathlib import Path

from KeyisBTools.models.serialization import serialize, deserialize, SerializableType

from .gnTransportProtocolParser import GNTransportProtocol, parse_gn_protocol
from .values import tablex_file_extension_to_inType
from ._data_pack import (
    pack_gnrequest,
    unpack_gnrequest,
    pack_gnresponse,
    unpack_gnresponse,
    _Aracada_container_packer
    )


from .domains import GNDomain
from ..gwis.values import tablex_gwis_object_types_int_to_str



class Url:
    
    __slots__ = (
        "transport", "route", "scheme",
        "hostname", "port", "path", "params", "fragment", "isIp"
    )

    _re_hostport = re.compile(r"^(?P<host>\[[^\]]+\]|[a-zA-Z0-9.~<>-]+)(?::(?P<port>\d+))?$", re.X)

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




class CORSObject:
    def __init__(self,
                 allow_origins: Optional[List[str]] = None,
                 allow_methods: Optional[List[str]] = None,
                 allow_client_types: List[Literal['net', 'client', 'server']] = ['net'],
                 allow_transport_protocols: Optional[List[str]] = None,
                 allow_route_protocols: Optional[List[str]] = None,
                 allow_request_protocols: Optional[List[str]] = None
                 ) -> None:
        """
        # Механизм контроля доступа


        :allow_origins: Список доменов, с которых разрешен запрос.
        :allow_methods: Разрешенные методы для запроса.
        :allow_client_types: Какие типы клиентов могут использовать.

        - `net` - Пользователи и другие службы сети `GN`

        - `client` - (TBD) Пользователи напрямую. Без использования прокси серверов сети `GN`

        - `server` - Другие `origin` сервера сети `GN`

        :allow_transport_protocols: (TBD)
        :allow_route_protocols: (TBD)
        :allow_request_protocols: (TBD)
        """
        self.allow_origins = allow_origins
        self.allow_methods = allow_methods
        self.allow_client_types = allow_client_types
        self.allow_transport_protocols = allow_transport_protocols
        self.allow_route_protocols = allow_route_protocols
        self.allow_request_protocols = allow_request_protocols

            


    
    def serialize(self) -> Optional[bytes]:
        a = {}
        if self.allow_origins is not None:
            a[0] = self.allow_origins
        if self.allow_methods is not None:
            a[1] = self.allow_methods
        if self.allow_client_types is not None and self.allow_client_types != ['net']:
            a[2] = self.allow_client_types
        if self.allow_transport_protocols is not None:
            a[3] = self.allow_transport_protocols
        if self.allow_route_protocols is not None:
            a[4] = self.allow_route_protocols
        if self.allow_request_protocols is not None:
            a[5] = self.allow_request_protocols
        if not a:
            return None
        else:
            return serialize(a)
        

    @staticmethod
    def deserialize(data: Dict[int, Any]) -> 'CORSObject':
        return CORSObject(
            allow_origins=data.get(0, None),
            allow_methods=data.get(1, None),
            allow_client_types=data.get(2, ['net']),

            allow_transport_protocols=data.get(3, None),
            allow_route_protocols=data.get(4, None),
            allow_request_protocols=data.get(5, None)
        )

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
                container: STPContainer | ITPContainer | bytes | None = None
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

    def setContainer(self, container: STPContainer | ITPContainer | bytes):
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
    def container(self) -> STPContainer | ITPContainer | None:
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
    
    def _unpack_container(self) -> STPContainer | ITPContainer:
        if self._container is None:
            raise ValueError('TempDataObject container is None')
        
        if isinstance(self._container, (bytes, bytearray, memoryview)):
            self._container = bytes(self._container)
            t = int.from_bytes(self._container[0:2], "big")
            if t == 1:  # ITP
                self._container = ITPContainer.deserialize(self._container)
            elif t == 2:  # STP
                self._container = STPContainer.deserialize(self._container)
            else:
                raise ValueError('Invalid TempDataObject data')
        
        return self._container
    
    @staticmethod
    def STP(payload: SerializableType, version: int = 0, compression_info: tuple[int, int, int, int] | None = None) -> 'TempDataObject':
        return TempDataObject(STPContainer(payload, version, compression_info))
    
    @staticmethod
    def ITP(interpreterType: int | str, payload: bytes, interpretatorVersion: int = 0, compression_info: tuple[int, int, int, int] | None = None) -> 'TempDataObject':
        return TempDataObject(ITPContainer(interpreterType, payload, interpretatorVersion, compression_info))
    
    def __repr__(self) -> str:
        return f"<TempDataObject [{self._container.payload if self._container else None}]>"

class TempDataGroup:
    __slots__ = ['objects']
    def __init__(self, objects: list[TempDataObject] | None = None) -> None:
        """
        # Временная группа данных
        """
        self.objects = objects or []



class GNRequest:
    """
    # Запрос для сети `GN`
    """
    def __init__(
        self,
        method: str,
        url: Url,
        payload: TempDataObject | SerializableType | None = None,
        cookies: dict | None = None,
        transport: str | None = None,
        route: str | None = None,
        origin: str | None = None
    ):
        self._method: str = method
        self._url = url
        self._cookies: dict = cookies
        self._transport: str = transport
        self._route: str = route
        self._origin = origin

        if isinstance(payload, TempDataObject):
            self._tdo = payload
        else:
            tdo = TempDataObject.STP(payload)
            self._tdo = tdo

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
                4: 'client'
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
        def type(self) -> Literal['net', 'client', 'server']:
            """
            # Тип клиента

            - `net` - Пользователи и другие службы сети `GN`

            - `client` - Пользователи напрямую. Без использования прокси серверов сети `GN`

            - `server` - Другие `origin` сервера сети `GN`
                
            :return: Literal['net', 'client', 'server']
            """
            return self.model_client_types[self._data.get('client-type', 1)] # type: ignore
        
        @property
        def type_int(self) -> Literal[1, 4, 2]:
            """
            # Тип клиента (int)

            - `1` - net - Пользователи и другие службы сети `GN`

            - `4` - client - Пользователи напрямую. Без использования прокси серверов сети `GN`

            - `2` - server - Другие `origin` сервера сети `GN`
            
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
        if self._transport is None: self.setTransport()
        if self._route is None: self.setRoute()

        cookies = {}

        if self._tdo is not None:
            payload = self._tdo.serialize()
        else:
            payload = None

        
        if self._cookies is not None:
            cookies.update(self._cookies)

        if cookies != {}:
            raw_cookies = serialize(cookies)
        else:
            raw_cookies = None

        return pack_gnrequest(
            version,
            self._transport,
            self._route,
            self._method,
            self.url.toString().encode(),
            payload,
            raw_cookies
        )

    @staticmethod
    def deserialize(data: bytes) -> 'GNRequest':
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

    def _assembly_server(self):
        d: str = self.client._data['domain']

        ct = None
        if d.endswith('.shield.gn'):
            ct = 1
        elif d.endswith('~gwis'):
            ct = 4
        elif GNDomain.isCore(d):
            ct = 0
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
    def payload(self) -> SerializableType | bytes | None:
        """
        # Полезная нагрузка запроса

        `Dict`, `List`, `bytes`, `int`, `str` и другие типы с поддержкой байтов.

        Все поддерживаемые типа описанны в `KeyisBTools.models.serialization.SerializableType`

        Если полезная нагрузка в контейнере `TempDataObject` не распакована, контейнер будет распакован.
        """
        if self.__raw_payload_cache is not None:
            return self.__raw_payload_cache

        if self._tdo is None or self._tdo.container is None:
            return None

        p = self._tdo.container.payload
        self.__raw_payload_cache = p
        return p

    @property
    def tdo(self) -> TempDataObject | None:
        """
        # Временный объект данных запроса `TempDataObject`
        """
        if self._tdo is None:
            return None
        
        return self._tdo

    @tdo.setter
    def tdo(self, value: TempDataObject | None):
        self._tdo = value
        self.__raw_payload_cache = None

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
    """
    def __init__(self,
                 command: str | int | bool | bytes,
                 payload: SerializableType | 'TempDataObject' | None = None,
                 cookies: dict | None = None
                 ):
        """
        :param command: Команда ответа. `str`, `int`, `bool`, `bytes`.
        :param payload: Полезная нагрузка ответа. Может быть `SerializableType` или `TempDataObject`. Все поддерживаемые типа описанны в `KeyisBTools.models.serialization.SerializableType`. `SerializableType` будет преобразован в `TempDataObject` при сборке.
        :param cookies: `dict`. Метаданные ответа.
        """
        self._command = command
        self._cookies = cookies
        self.command = CommandObject(command)
        """
        # Команда запроса `CommandObject`
        """

        self._tdo: TempDataObject | None = None

        if isinstance(payload, TempDataObject):
            self._tdo = payload
        else:
            tdo = TempDataObject.STP(payload)
            self._tdo = tdo

        self.__raw_payload_cache: SerializableType | None = None

    def assembly(self): ... # legacy
        

    def serialize(self) -> bytes:
        if self._cookies is not None:
            cookies = serialize(self._cookies)
        else:
            cookies = None
        
        return pack_gnresponse(
            version=0,
            command=self._command,
            payload=cast(TempDataObject, self._tdo).serialize(),
            cookies=cookies
        )
    
    @staticmethod
    def deserialize(data: bytes) -> 'GNResponse':
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
    
    @property
    def tdo(self) -> TempDataObject | None:
        if self._tdo is None:
            return None
        
        return self._tdo

    @tdo.setter
    def tdo(self, value: TempDataObject | None):
        self._tdo = value
        self.__raw_payload_cache = None
    
    @property
    def payload(self) -> SerializableType | bytes | None:
        """
        # Полезная нагрузка ответа
        Если полезная нагрузка в контейнере `TempDataObject` не распакована, контейнер будет распакован.
        """
        if self.__raw_payload_cache is not None:
            return self.__raw_payload_cache

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
    
    def __repr__(self):
        return f"<GNResponse [{self._command}]>"
    
    def __str__(self) -> str:
        return f"[GNResponse]: {self._command} {self._tdo}"


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



