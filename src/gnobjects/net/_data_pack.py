

from typing import *

import zstandard as zstd


from .values import (common_gnrequest_transports,
                     common_gnrequest_methods,
                     common_gnrequest_routes,
                     base_gnrequest_transport,
                     base_gnrequest_method,
                     base_gnrequest_route,
                     common_gnrequest_dataTypes,
                     base_gnrequest_inType,
                     common_gnrequest_inTypes,
                     common_gnrequest_compressTypes
                     )


_len_encode_2_bit = (1, 2, 4, 8)
_len_encode_2_bit_short = {
    0: 0,  # 00 = поля нет
    1: 1,  # 01 → 1 байт длины
    2: 3,  # 10 → 3 байта длины (хватает до 0xFFFFF)
    3: 4,  # 11 → 4 байта длины (хватает до 0xFFFFFFF)
}



_rev_dataTypes: Dict[int, str] = {v: k for k, v in common_gnrequest_dataTypes.items()}
_rev_inTypes:   Dict[int, str] = {v: k for k, v in common_gnrequest_inTypes.items()}
_rev_methods:   Dict[int, str] = {v: k for k, v in common_gnrequest_methods.items()}


# ===== gnrequest =====
def pack_gnrequest(
                 version: int,
                 transport: str,
                 route: str,
                 method: str,
                 url: bytes,
                 payload: Optional[bytes],
                 cookies: Optional[bytes]
                 ) -> bytes:
    
    if version == 0:
        return pack_gnrequest_v0(
            version,
            transport,
            route,
            method,
            url,
            payload,
            cookies
        )
    else:
        raise ValueError('Unsupported version')

def unpack_gnrequest(data: bytes) -> dict:
    if len(data) == 0:
        raise ValueError("Empty data")

    version = (data[0] >> 6) & 0b11

    if version == 0:
        return unpack_gnrequest_v0(data)
    else:
        raise ValueError('Unsupported version')


def pack_gnrequest_v0(
                 version: int,
                 transport: str,
                 route: str,
                 method: str,
                 url: bytes,
                 payload: Optional[bytes],
                 cookies: Optional[bytes]
                 ) -> bytes:
    
    if version < 0 or version > 3:
        raise ValueError('Version must be between 0 and 3')

    blob = bytearray()

    types_b = 0

    types_b |= (version & 0x03) << 6

    # transport
    if transport == base_gnrequest_transport:
        types_b |= (1 << 5)
    elif transport in common_gnrequest_transports:
        types_b |= (1 << 4)

    method = method.lower()
    # method
    if method == base_gnrequest_method:
        types_b |= (1 << 3)
    elif method in common_gnrequest_methods:
        types_b |= (1 << 2)

    # route
    if route == base_gnrequest_route:
        types_b |= (1 << 1)
    elif route in common_gnrequest_routes:
        types_b |= (1 << 0)

    blob.append(types_b)

    # теперь нестандартные значения

    # необычные но стандартные значения
    b1 = 0
    b2 = 0

    data_len = bytearray()
    data = bytearray()

    # transport
    if ((types_b >> 5) & 1) == 0:
        # если не обычный
        if (types_b >> 4) & 1:
            # если стандартный, то 4 бита.
            transport_int = common_gnrequest_transports[transport] + 1 # +1 чтобы 0 не использовался
            b1 |= (transport_int & 0x0F) << 4
        else:
            # иначе строка
            # длина строки 1 байт
            transport_b = transport.encode('utf-8')
            l = len(transport_b)
            if l > 255:
                raise ValueError('Transport string too long')
            data_len.append(l)
            data.extend(transport_b)
    
    # method
    if ((types_b >> 3) & 1) == 0:
        # если не обычный
        if (types_b >> 2) & 1:
            # если стандартный, то 4 бита.
            method_int = common_gnrequest_methods[method] + 1 # +1 чтобы 0 не использовался
            b1 |= (method_int & 0x0F)
        else:
            # иначе строка
            # длина строки 1 байт
            method_b = method.encode('utf-8')
            l = len(method_b)
            if l > 255:
                raise ValueError('Method string too long')
            data_len.append(l)
            data.extend(method_b)


    # route
    if ((types_b >> 1) & 1) == 0:
        # если не обычный
        if (types_b >> 0) & 1:
            # если стандартный, то 8 бит.
            route_int = common_gnrequest_routes[route] + 1 # +1 чтобы 0 не использовался
            b2 |= (route_int & 0xFF)
        else:
            # иначе строка
            # длина строки 1 байт
            route_b = route.encode('utf-8')
            l = len(route_b)
            if l > 255:
                raise ValueError('Route string too long')
            data_len.append(l)
            data.extend(route_b)


    if b1 != 0:
        blob.append(b1)
    if b2 != 0:
        blob.append(b2)
    
    if len(data_len) > 0:
        blob.extend(data_len)
    
    if len(data) > 0:
        blob.extend(data)



    # типы тела
    b3 = 0

    # payload is
    if payload is not None:
        b3 |= (1 << 7)
    
    # cookies is
    if cookies is not None:
        b3 |= (1 << 6)
    
    # length types

    # url
    if len(url) <= 255: # 1 byte
        b3 |= (0 << 5)
        b3 |= (0 << 4)
    elif len(url) <= 65535: # 2 bytes
        b3 |= (0 << 5)
        b3 |= (1 << 4)
    elif len(url) <= 4294967295: # 4 bytes
        b3 |= (1 << 5)
        b3 |= (0 << 4)
    else: # 8 bytes
        b3 |= (1 << 5)
        b3 |= (1 << 4)

    if cookies is not None:
        if len(cookies) <= 255: # 1 byte
            b3 |= (0 << 3)
            b3 |= (0 << 2)
        elif len(cookies) <= 65535: # 2 bytes
            b3 |= (0 << 3)
            b3 |= (1 << 2)
        elif len(cookies) <= 4294967295: # 4 bytes
            b3 |= (1 << 3)
            b3 |= (0 << 2)
        else: # 8 bytes
            b3 |= (1 << 3)
            b3 |= (1 << 2)
    
   

    blob.append(b3)

    body = bytearray()

    # url
    url_b = url
    l = len(url_b)
    body += l.to_bytes(_len_encode_2_bit[(b3 >> 4) & 0b11], 'big', signed=False)
    body += url_b


    # cookies
    if cookies is not None:
        cookies_b = cookies
        l = len(cookies_b)
        body += l.to_bytes(_len_encode_2_bit[(b3 >> 2) & 0b11], 'big', signed=False)
        body += cookies_b
    

    # payload
    if payload is not None:
        payload_b = payload
        body += payload_b


    blob += body
    return bytes(blob)

def unpack_gnrequest_v0(data: bytes) -> dict:
    """
    Декод строго соответствует pack_request():
    [types_b][b1?][b2?][(len T)?][(len M)?][(len R)?][(T str)?][(M str)?][(R str)?][b3][url_len][url][cookies_len?][cookies?][payload?]
    """
    total_len = len(data)
    pos = 0

    def ensure(n: int):
        if pos + n > total_len:
            raise ValueError(f"Truncated input: need {n} bytes at pos {pos}, total {total_len}")

    def lookup_by_value(d: dict, code: int, what: str) -> str:
        for k, v in d.items():
            if v == code:
                return k
        raise ValueError(f"Unknown {what} code {code}")

    # === 1) TYPES_B ===
    ensure(1)
    types_b = data[pos]; pos += 1

    version      = (types_b >> 6) & 0b11
    t_quik_real  = ((types_b >> 5) & 1) == 1
    t_common     = ((types_b >> 4) & 1) == 1
    m_get        = ((types_b >> 3) & 1) == 1
    m_common     = ((types_b >> 2) & 1) == 1
    r_gn_net     = ((types_b >> 1) & 1) == 1
    r_common     = ((types_b >> 0) & 1) == 1

    # === 2) b1 / b2 presence, read if present ===
    b1_present = (not t_quik_real and t_common) or m_common
    b2_present = (not r_gn_net and r_common)

    b1 = 0
    if b1_present:
        ensure(1)
        b1 = data[pos]; pos += 1

    b2 = 0
    if b2_present:
        ensure(1)
        b2 = data[pos]; pos += 1

    # === 3) Какие поля — строковые? (PACK кладёт сначала ВСЕ длины, потом ВСЕ строки) ===
    t_is_str = (not t_quik_real) and (not t_common)
    m_is_str = (not m_get) and (not m_common)
    r_is_str = (not r_gn_net) and (not r_common)

    # === 4) Считать все длины строк, если есть ===
    t_len = 0
    if t_is_str:
        ensure(1)
        t_len = data[pos]; pos += 1

    m_len = 0
    if m_is_str:
        ensure(1)
        m_len = data[pos]; pos += 1

    r_len = 0
    if r_is_str:
        ensure(1)
        r_len = data[pos]; pos += 1

    # === 5) Считать все строки по порядку: Transport, Method, Route ===
    # Transport
    if t_quik_real:
        transport = base_gnrequest_transport
    elif t_common:
        # код в старших 4 битах b1, закодирован как (idx+1)
        t_code = ((b1 >> 4) & 0x0F) - 1
        if t_code < 0:
            raise ValueError("Invalid transport code (zero)")
        transport = lookup_by_value(common_gnrequest_transports, t_code, "transport")
    else:
        ensure(t_len)
        transport = data[pos:pos + t_len].decode('utf-8')
        pos += t_len

    # Method
    if m_get:
        method = base_gnrequest_method
    elif m_common:
        m_code = (b1 & 0x0F) - 1
        if m_code < 0:
            raise ValueError("Invalid method code (zero)")
        method = lookup_by_value(common_gnrequest_methods, m_code, "method")
    else:
        ensure(m_len)
        method = data[pos:pos + m_len].decode('utf-8')
        pos += m_len

    # Route
    if r_gn_net:
        route = base_gnrequest_route
    elif r_common:
        r_code = b2 - 1
        if r_code < 0:
            raise ValueError("Invalid route code (zero)")
        route = lookup_by_value(common_gnrequest_routes, r_code, "route")
    else:
        ensure(r_len)
        route = data[pos:pos + r_len].decode('utf-8')
        pos += r_len

    # === 6) B3 ===
    ensure(1)
    b3 = data[pos]; pos += 1

    payload_present  = ((b3 >> 7) & 1) == 1
    cookies_present  = ((b3 >> 6) & 1) == 1
    url_len_flag     = (b3 >> 4) & 0b11
    cookies_len_flag = (b3 >> 2) & 0b11

    try:
        url_len_size = _len_encode_2_bit[url_len_flag]
    except IndexError:
        raise ValueError(f"Invalid url_len_flag {url_len_flag}")

    cookies_len_size = _len_encode_2_bit[cookies_len_flag] if cookies_present else 0

    # === 7) URL ===
    ensure(url_len_size)
    url_len = int.from_bytes(data[pos:pos + url_len_size], 'big', signed=False)
    pos += url_len_size

    ensure(url_len)
    url = data[pos:pos + url_len]
    pos += url_len

    # === 8) Cookies (если есть) ===
    cookies = None
    if cookies_present:
        ensure(cookies_len_size)
        c_len = int.from_bytes(data[pos:pos + cookies_len_size], 'big', signed=False)
        pos += cookies_len_size

        ensure(c_len)
        cookies = data[pos:pos + c_len]
        pos += c_len

    # === 9) Payload (оставшиеся данные) ===
    payload = None
    if payload_present:
        payload = data[pos:total_len]
        pos = total_len

    # === 10) Результат ===
    return {
        'version': version,
        'transport': transport,
        'method': method,
        'route': route,
        'url': url,
        'cookies': cookies,
        'payload': payload,
    }

# ===== gnrequest =====



# ===== TempDataObject =====
def pack_temp_data_object(
                    version: int,
                    dataType: str,
                    inType: Optional[str],
                    method: str,
                    path: str,
                    payload: Optional[bytes],
                    cache: Optional[bytes],
                    cors: Optional[bytes]
                 ) -> bytes:

    if version == 0:
        return pack_temp_data_object_v0(
            version,
            dataType,
            inType,
            method,
            path,
            payload,
            cache,
            cors
        )
    else:
        raise ValueError('Unsupported version')

def unpack_temp_data_object(data: bytes) -> dict:
    if len(data) == 0:
        raise ValueError("Empty data")

    version = (data[0] >> 6) & 0b11

    if version == 0:
        return unpack_temp_data_object_v0(data)
    else:
        raise ValueError('Unsupported version')



def pack_temp_data_object_v0(
                 version: int,
                 dataType: str,
                 inType: Optional[str],
                 method: str,
                 path: str,
                 payload: Optional[bytes],
                 cache: Optional[bytes],
                 cors: Optional[bytes]
                 ) -> bytes:
    
    if version < 0 or version > 3:
        raise ValueError('Version must be between 0 and 3')
    
    blob = bytearray()

    b0 = 0  # allways
    # 7 - version # allways
    # 6 - version # allways
    # 5 - dataType # allways
    # 4 - dataType # allways
    # 3 - dataType # allways
    # 2 - dataType # allways
    # 1 - inType is base
    # 0 - inType standard

    # 1 and 0 == 11 - inType is None



    b0 |= (version & 0x03) << 6

    # dataType
    _dt_int = common_gnrequest_dataTypes[dataType] # тут можем использовать 0. этот байт всегда есть
    b0 |= (_dt_int & 0x0F) << 2

    if inType is None:
        b0 |= (1 << 1)
        b0 |= (1 << 0)
    elif inType == base_gnrequest_inType:
        b0 |= (1 << 1)
    elif inType in common_gnrequest_inTypes:
        b0 |= (1 << 0)

    blob.append(b0)

    b1 = 0
    # 7 - method is base
    # 6 - method standard
    # 5 - path is base
    # 4 - has payload
    # 3 - compressType standard value (reserved)
    # 2 - compressType standard value (reserved)
    # 1 - compressType standard value (reserved)
    # 0 - compressType standard value (reserved)

    

    if method == base_gnrequest_method:
        b1 |= (1 << 7)
    elif method in common_gnrequest_methods:
        b1 |= (1 << 6)
    else:
        raise ValueError(f"Unknown method: {method}")

    if path == '/':
        b1 |= (1 << 5)
    
    if payload is not None:
        b1 |= (1 << 4)


    blob.append(b1)


    # теперь стандартные значения
    if (
        (inType is not None and ((b0 & 0b11) in (1,2)))  # inType присутствует и имеет стандарт/базу
        or ((b1 >> 6) & 1)  # method стандартный
            ): # если есть стандартные значения, добавляем байт [90%]
        
        if (inType is not None and ((b0 >> 0) & 1) == 1) and (((b1 >> 6) & 1) == 0): # если есть inType, но нет method, то весь байт идет на inType [80%]
            # b2 - inType standard value
            b2 = common_gnrequest_inTypes[inType]
            blob.append(b2)

        elif (((b1 >> 6) & 1) == 1) and (((b0 >> 0) & 1) == 0): # если есть method, но нет inType, то весь байт идет на method [5%]
            # b2 - method standard value
            b2 = common_gnrequest_methods[method]
            blob.append(b2)

        else: # если есть и метод и inType, то добавляем 2 байта. 2 на inType, второй на method [15%]
            if inType is not None and inType != base_gnrequest_inType:
                # b2 - inType standard value
                b2 = common_gnrequest_inTypes[inType]
                blob.append(b2)

            # b2 - method standard value
            b3 = common_gnrequest_methods[method]
            blob.append(b3)



    # lenghs of lenghs
    b4 = 0
    # 7 - # inType length type
    # 6 - # inType length type
    # 5 - # path length type
    # 4 - # path length type
    # 3 - # cache length size
    # 2 - # cache length size
    # 1 - # cors length size
    # 0 - # cors length size



    path_b = path.encode('utf-8')
    
    if inType is None:
        inType_b = None
    elif inType == base_gnrequest_inType:
        inType_b = None              # base → без строки
    elif inType in common_gnrequest_inTypes:
        inType_b = None              # standard → без строки
    else:
        inType_b = inType.encode('utf-8')  # custom

    def _set_length_type(b: int, length: int, shift: int) -> int:
        if length <= 0xFF:
            return b | (1 << shift)
        elif length <= 0xFFFFF:
            return b | (1 << (shift + 1))
        elif length <= 0xFFFFFFF:
            return b | (1 << shift) | (1 << (shift + 1))
        else:
            raise ValueError("Too long length")

    # inType
    if inType_b is not None:
        b4 = _set_length_type(b4, len(inType_b), 6)
    # path
    b4 = _set_length_type(b4, len(path_b), 4)
    # cache
    if cache is not None:
        b4 = _set_length_type(b4, len(cache), 2)
    # cors
    if cors is not None:
        b4 = _set_length_type(b4, len(cors), 0)
    blob.append(b4)




    body = bytearray()
    if inType_b is not None:
        l1 = len(inType_b)
        body.extend(l1.to_bytes(_len_encode_2_bit_short[(b4 >> 6) & 0b11], 'big', signed=False))
        body.extend(inType_b)

    if path != '/':
        l1 = len(path_b)
        body.extend(l1.to_bytes(_len_encode_2_bit_short[(b4 >> 4) & 0b11], 'big', signed=False))
        body.extend(path_b)

    if cache is not None:
        cache_b = cache
        l2 = len(cache_b)
        body.extend(l2.to_bytes(_len_encode_2_bit_short[(b4 >> 2) & 0b11], 'big', signed=False))
        body.extend(cache_b)
    
    if cors is not None:
        cors_b = cors
        l3 = len(cors_b)
        body.extend(l3.to_bytes(_len_encode_2_bit_short[(b4 >> 0) & 0b11], 'big', signed=False))
        body.extend(cors_b)
    
    if payload is not None:
        body.extend(payload)

    blob.extend(body)
    return bytes(blob)


def _read_len_and_bytes(buf: bytes, pos: int, len_type_2bit: int) -> tuple[bytes, int]:
    n = _len_encode_2_bit_short[len_type_2bit]
    if pos + n > len(buf):
        raise ValueError("Truncated length field")
    ln = int.from_bytes(buf[pos:pos + n], "big", signed=False)
    pos += n
    if pos + ln > len(buf):
        raise ValueError("Truncated data field")
    seg = buf[pos:pos + ln]
    pos += ln
    return seg, pos

def unpack_temp_data_object_v0(data: bytes) -> dict:
    """
    Строго зеркальная распаковка к pack_temp_data_object_v0().
    Однозначна и детерминирована.
    """
    if len(data) < 3:
        raise ValueError("Too short")

    pos = 0

    # b0
    b0 = data[pos]; pos += 1
    version = (b0 >> 6) & 0b11
    dataType_code = (b0 >> 2) & 0x0F
    inType_bits = b0 & 0b11  # 10=base, 01=std, 11=None

    # inType_mode и значение
        
    if inType_bits == 0b11:
        inType_mode = "none"
    elif inType_bits == 0b10:
        inType_mode = "base"
    elif inType_bits == 0b01:
        inType_mode = "standard"
    elif inType_bits == 0b00:
        inType_mode = "custom"
    else:
        raise ValueError("Invalid inType bits")

    inType: Optional[str] = None  # инициализация для Pylance
    # (значение установим позже, после b2/b3 и/или чтения строки)

    # dataType
    try:
        dataType = _rev_dataTypes[dataType_code]
    except KeyError:
        raise ValueError(f"Unknown dataType code: {dataType_code}")

    # b1
    b1 = data[pos]; pos += 1
    method_is_base = (b1 >> 7) & 1
    method_is_std  = (b1 >> 6) & 1
    path_is_base   = (b1 >> 5) & 1
    has_payload    = (b1 >> 4) & 1
    # b1 bits 3..0 зарезервированы под compressType (не используются здесь)

    # b2/b3 (std-значения inType/method) — строго по логике pack()
    inType_std_val: Optional[int] = None
    method_std_val: Optional[int] = None

    if ((inType_bits in (0b01, 0b10)) or method_is_std):
        if (inType_bits == 0b01) and (not method_is_std):
            # только inType std
            inType_std_val = data[pos]; pos += 1
        elif method_is_std and (inType_bits != 0b01):
            # только method std
            method_std_val = data[pos]; pos += 1
        else:
            # оба; либо method std при inType=None — см. pack(): сначала inType (если есть), затем method
            if inType_bits == 0b01:
                inType_std_val = data[pos]; pos += 1
            method_std_val = data[pos]; pos += 1

    # b4 (дескрипторы длин)
    b4 = data[pos]; pos += 1
    inType_len_type = (b4 >> 6) & 0b11
    path_len_type   = (b4 >> 4) & 0b11
    cache_len_type  = (b4 >> 2) & 0b11
    cors_len_type   = (b4 >> 0) & 0b11

    # === тело ===

    # inType
    if inType_mode == "none":
        inType = None
    elif inType_mode == "base":
        inType = base_gnrequest_inType
    elif inType_mode == "standard":
        if inType_std_val is None:
            raise ValueError("Missing inType std value")
        try:
            inType = _rev_inTypes[inType_std_val]
        except KeyError:
            raise ValueError(f"Unknown inType std code: {inType_std_val}")
    elif inType_mode == "custom":
        seg, pos = _read_len_and_bytes(data, pos, inType_len_type)
        inType = seg.decode("utf-8")
    else:
        raise ValueError("Impossible inType_mode")  # защитный

    # path
    if path_is_base:
        path = "/"
    else:
        seg, pos = _read_len_and_bytes(data, pos, path_len_type)
        path = seg.decode("utf-8")

    # ВНИМАНИЕ по cache/cors:
    # Детект присутствия делаем ТОЛЬКО по b4 (len_type != 0 → поле присутствует).
    # Это детерминированно и не съедает payload.
    cache: Optional[bytes] = None
    cors:  Optional[bytes] = None

    if cache_len_type != 0:
        seg, pos = _read_len_and_bytes(data, pos, cache_len_type)
        cache = seg

    if cors_len_type != 0:
        seg, pos = _read_len_and_bytes(data, pos, cors_len_type)
        cors = seg

    # payload
    payload: Optional[bytes] = None
    if has_payload:
        payload = data[pos:] if pos < len(data) else b""
        pos = len(data)

    # method
    if method_is_base:
        method = base_gnrequest_method
    elif method_is_std:
        if method_std_val is None:
            raise ValueError("Missing method std value")
        try:
            method = _rev_methods[method_std_val]
        except KeyError:
            raise ValueError(f"Unknown method std code: {method_std_val}")
    else:
        raise ValueError("Invalid method flags")

    # финал
    return {
        "version": version,
        "dataType": dataType,
        "inType": inType,
        "method": method,
        "path": path,
        "payload": payload,
        "cache": cache,
        "cors": cors,
    }


def _read_len(buf: bytes, pos: int, len_type: int) -> tuple[int, int]:
    n = _len_encode_2_bit_short[len_type]
    if n == 0:
        return 0, pos
    if pos + n > len(buf):
        raise ValueError("Truncated length field")
    ln = int.from_bytes(buf[pos:pos + n], 'big')
    pos += n
    return ln, pos
def pick_zstd_level(size: int) -> int:
    if size < 4 * 1024:
        return 0
    if size < 16 * 1024:
        return 6
    if size < 256 * 1024:
        return 9
    if size < 2 * 1024 * 1024:
        return 15
    return 19

def compress_TempDataObject(raw: bytes) -> bytes:
    data = bytearray(raw)
    if len(data) < 5:
        return raw

    pos = 0
    b0 = data[pos]; pos += 1
    b1 = data[pos]; pos += 1

    method_is_std  = (b1 >> 6) & 1
    path_is_base   = (b1 >> 5) & 1
    has_payload    = (b1 >> 4) & 1

    inType_bits = b0 & 0b11
    skip_std = 0
    if ((inType_bits in (0b01, 0b10)) or method_is_std):
        if (inType_bits == 0b01) and (not method_is_std):
            skip_std = 1
        elif method_is_std and (inType_bits != 0b01):
            skip_std = 1
        else:
            skip_std = 2
    pos += skip_std

    if pos >= len(data):
        return raw

    b4 = data[pos]; pos += 1
    inType_len_type = (b4 >> 6) & 0b11
    path_len_type   = (b4 >> 4) & 0b11
    cache_len_type  = (b4 >> 2) & 0b11
    cors_len_type   = (b4 >> 0) & 0b11

    # inType
    if inType_bits == 0b00:
        l, pos = _read_len(data, pos, inType_len_type)
        pos += l
    # path
    if not path_is_base:
        l, pos = _read_len(data, pos, path_len_type)
        pos += l
    # cache
    if cache_len_type != 0:
        l, pos = _read_len(data, pos, cache_len_type)
        pos += l
    # cors
    if cors_len_type != 0:
        l, pos = _read_len(data, pos, cors_len_type)
        pos += l

    if not has_payload or pos >= len(data):
        return raw

    payload = bytes(data[pos:])
    if not payload:
        return raw

    level = pick_zstd_level(len(payload))
    if level == 0:
        return raw

    compressor = zstd.ZstdCompressor(level=level)
    compressed = compressor.compress(payload)

    # флаг компрессии
    b1 = (b1 & 0xF0) | common_gnrequest_compressTypes['zstd']
    data[1] = b1

    data = data[:pos] + compressed
    return bytes(data)


def decompress_TempDataObject(raw: bytes) -> bytes:
    if len(raw) < 5:
        return raw

    data = bytearray(raw)
    b1 = data[1]
    comp_type = b1 & 0x0F
    if comp_type == 0:
        # нет компрессии
        return raw
    if comp_type != common_gnrequest_compressTypes['zstd']:
        raise ValueError(f"Unknown compression type: {comp_type}")

    # вычисляем начало payload (аналогично compress)
    pos = 0
    b0 = data[pos]; pos += 1
    _ = data[pos]; pos += 1  # b1
    method_is_std  = (b1 >> 6) & 1
    path_is_base   = (b1 >> 5) & 1
    has_payload    = (b1 >> 4) & 1
    inType_bits = b0 & 0b11

    skip_std = 0
    if ((inType_bits in (0b01, 0b10)) or method_is_std):
        if (inType_bits == 0b01) and (not method_is_std):
            skip_std = 1
        elif method_is_std and (inType_bits != 0b01):
            skip_std = 1
        else:
            skip_std = 2
    pos += skip_std

    b4 = data[pos]; pos += 1
    inType_len_type = (b4 >> 6) & 0b11
    path_len_type   = (b4 >> 4) & 0b11
    cache_len_type  = (b4 >> 2) & 0b11
    cors_len_type   = (b4 >> 0) & 0b11

    if inType_bits == 0b00:
        l, pos = _read_len(data, pos, inType_len_type)
        pos += l
    if not path_is_base:
        l, pos = _read_len(data, pos, path_len_type)
        pos += l
    if cache_len_type != 0:
        l, pos = _read_len(data, pos, cache_len_type)
        pos += l
    if cors_len_type != 0:
        l, pos = _read_len(data, pos, cors_len_type)
        pos += l

    if not has_payload or pos >= len(data):
        return raw

    compressed = bytes(data[pos:])
    if not compressed:
        return raw

    # декомпрессия
    decompressor = zstd.ZstdDecompressor()
    try:
        payload = decompressor.decompress(compressed)
    except zstd.ZstdError:
        raise ValueError("Invalid zstd payload")

    # убираем флаг
    b1 &= 0xF0
    data[1] = b1

    # заменяем payload
    data = data[:pos] + payload
    return bytes(data)

# ===== TempDataObject =====


# ===== TempDataGroup =====

def pack_temp_data_group(
                    version: int,
                    path: str,
                    payload: List[bytes]
                 ) -> bytes:

    if version == 0:
        return pack_temp_data_group_v0(
            version,
            path,
            payload
        )
    else:
        raise ValueError('Unsupported version')

def unpack_temp_data_group(data: bytes) -> dict:
    if len(data) == 0:
        raise ValueError("Empty data")

    version = (data[0] >> 6) & 0b11

    if version == 0:
        return unpack_temp_data_object_v0(data)
    else:
        raise ValueError('Unsupported version')



def __encode_varlen_length(length: int) -> bytes:
    """Кодирует длину: 2–8 байт с префиксом из 2 бит."""
    if length < (1 << 14):
        # 00 — 2 байта
        v = (0b00 << 14) | length
        return v.to_bytes(2, "big")
    elif length < (1 << 22):
        # 01 — 3 байта
        v = (0b01 << 22) | length
        return v.to_bytes(3, "big")
    elif length < (1 << 38):
        # 10 — 5 байт
        v = (0b10 << 38) | length
        return v.to_bytes(5, "big")
    elif length < (1 << 62):
        # 11 — 8 байт
        v = (0b11 << 62) | length
        return v.to_bytes(8, "big")
    else:
        raise ValueError("Length too large")


def __decode_varlen_length(buf: bytes, pos: int) -> Tuple[int, int]:
    """Декодирует varlen (возвращает length, new_pos). С защитой от усечения."""
    if pos >= len(buf):
        raise ValueError("Truncated buffer (no first byte)")
    first = buf[pos]
    prefix = (first >> 6) & 0b11
    if prefix == 0b00:
        nbytes = 2
        if pos + nbytes > len(buf):
            raise ValueError("Truncated varlen (need 2 bytes)")
        raw = int.from_bytes(buf[pos:pos + nbytes], "big")
        length = raw & ((1 << 14) - 1)
    elif prefix == 0b01:
        nbytes = 3
        if pos + nbytes > len(buf):
            raise ValueError("Truncated varlen (need 3 bytes)")
        raw = int.from_bytes(buf[pos:pos + nbytes], "big")
        length = raw & ((1 << 22) - 1)
    elif prefix == 0b10:
        nbytes = 5
        if pos + nbytes > len(buf):
            raise ValueError("Truncated varlen (need 5 bytes)")
        raw = int.from_bytes(buf[pos:pos + nbytes], "big")
        length = raw & ((1 << 38) - 1)
    else:
        nbytes = 8
        if pos + nbytes > len(buf):
            raise ValueError("Truncated varlen (need 8 bytes)")
        raw = int.from_bytes(buf[pos:pos + nbytes], "big")
        length = raw & ((1 << 62) - 1)
    return length, pos + nbytes


def pack_temp_data_group_v0(version: int, path: str, payload: List[bytes]) -> bytes:
    if not (0 <= version <= 3):
        raise ValueError("Version must be between 0 and 3")

    blob = bytearray()

    # b0: версия (2 старших бита)
    b0 = (version & 0b11) << 6
    blob.append(b0)

    # path
    path_b = path.encode("utf-8")
    if len(path_b) > 0xFFFF:
        raise ValueError("Path too long")
    blob.extend(len(path_b).to_bytes(2, "big"))
    blob.extend(path_b)

    # count
    n = len(payload)
    if n > 0xFFFF:
        raise ValueError("Too many payload items (>65535)")
    blob.extend(n.to_bytes(2, "big"))

    # items
    for p in payload:
        blob.extend(__encode_varlen_length(len(p)))
        blob.extend(p)

    return bytes(blob)


def unpack_temp_data_group_v0(data: bytes) -> dict:
    pos = 0
    if len(data) < 5:
        raise ValueError("Too short")

    b0 = data[pos]; pos += 1
    version = (b0 >> 6) & 0b11

    # path
    if pos + 2 > len(data):
        raise ValueError("Truncated before path length")
    path_len = int.from_bytes(data[pos:pos + 2], "big"); pos += 2
    if pos + path_len > len(data):
        raise ValueError("Truncated path")
    path = data[pos:pos + path_len].decode("utf-8"); pos += path_len

    # count
    if pos + 2 > len(data):
        raise ValueError("Truncated before items count")
    n_items = int.from_bytes(data[pos:pos + 2], "big"); pos += 2
    payloads = []

    for _ in range(n_items):
        length, pos = __decode_varlen_length(data, pos)
        if pos + length > len(data):
            raise ValueError("Truncated item data")
        payloads.append(data[pos:pos + length])
        pos += length

    # Жёсткая проверка на хвост
    if pos != len(data):
        raise ValueError("Trailing bytes after payloads")

    return {
        "version": version,
        "path": path,
        "payload": payloads
    }

# ===== TempDataGroup =====
# ===== GNResponse =====


def pack_gnresponse(
                    version: int,
                    command: Union[str, int, bool, bytes, bytearray, memoryview],
                    payload: Optional[bytes],
                    cookies: Optional[bytes]
                 ) -> bytes:

    if version == 0:
        return pack_gnresponse_v0(
            version,
            command,
            payload,
            cookies
        )
    else:
        raise ValueError('Unsupported version')

def unpack_gnresponse(data: bytes) -> dict:
    if len(data) == 0:
        raise ValueError("Empty data")

    version = (data[0] >> 6) & 0b11

    if version == 0:
        return unpack_gnresponse_v0(data)
    else:
        raise ValueError('Unsupported version')





def __encode_varint62(value: int) -> bytes:
    if value < 0:
        raise ValueError("Negative values are not supported by varint62")
    if value < (1 << 14):
        v = (0b00 << 14) | value
        return v.to_bytes(2, "big")
    elif value < (1 << 22):
        v = (0b01 << 22) | value
        return v.to_bytes(3, "big")
    elif value < (1 << 38):
        v = (0b10 << 38) | value
        return v.to_bytes(5, "big")
    elif value < (1 << 62):
        v = (0b11 << 62) | value
        return v.to_bytes(8, "big")
    else:
        raise ValueError("Value too large for varint62 (<2^62)")

def __decode_varint62(buf: bytes, offset: int = 0) -> Tuple[int, int]:
    if offset >= len(buf):
        raise ValueError("Buffer underflow (no varint head)")
    tag = buf[offset] >> 6
    size = (2, 3, 5, 8)[tag]
    end = offset + size
    if end > len(buf):
        raise ValueError("Buffer underflow (varint truncated)")
    raw = int.from_bytes(buf[offset:end], "big")
    payload_bits = size * 8 - 2
    value = raw & ((1 << payload_bits) - 1)
    return value, end

def pack_gnresponse_v0(
    version: int,
    command: Union[str, int, bool, bytes, bytearray, memoryview],
    payload: Optional[bytes],
    cookies: Optional[bytes],
) -> bytes:
    if not (0 <= version <= 3):
        raise ValueError("Version must be between 0 and 3")

    def _check_len(x: Optional[bytes], name: str) -> None:
        if x is None:
            return
        if len(x) >= (1 << 62):
            raise ValueError(f"{name} too large (>= 2^62)")

    _check_len(payload, "payload")
    _check_len(cookies, "cookies")

    out = bytearray()

    b0 = (version & 0x03) << 6

    has_cookies = cookies is not None
    has_payload = payload is not None
    if has_cookies:
        b0 |= (1 << 3)
    if has_payload:
        b0 |= (1 << 2)

    if isinstance(command, bool):
        b0 |= (0b00 << 4)
        if command:
            b0 |= (1 << 1)
        out.append(b0)

    elif isinstance(command, int) and not isinstance(command, bool):
        if command < 0:
            raise ValueError("Negative int not supported in v0")
        if command >= (1 << 62):
            raise ValueError("int value too large (>= 2^62)")
        b0 |= (0b01 << 4)

        if not has_cookies and not has_payload and command <= 14:
            b0 |= (command & 0x0F)
            out.append(b0)
        else:
            b0 |= 0x0F if not has_cookies and not has_payload else 0
            out.append(b0)
            out.extend(__encode_varint62(command))

    elif isinstance(command, str):
        b0 |= (0b10 << 4)
        data = command.encode("utf-8")
        n = len(data)
        if n >= (1 << 62):
            raise ValueError("command(str) too large (>= 2^62)")
        if not has_cookies and not has_payload and n <= 14:
            b0 |= (n & 0x0F)
            out.append(b0)
            out.extend(data)
        else:
            if not has_cookies and not has_payload:
                b0 |= 0x0F
            out.append(b0)
            out.extend(__encode_varint62(n))
            out.extend(data)

    elif isinstance(command, (bytes, bytearray, memoryview)):
        b0 |= (0b11 << 4)
        data = bytes(command)
        n = len(data)
        if n >= (1 << 62):
            raise ValueError("command(bytes) too large (>= 2^62)")
        if not has_cookies and not has_payload and n <= 14:
            b0 |= (n & 0x0F)
            out.append(b0)
            out.extend(data)
        else:
            if not has_cookies and not has_payload:
                b0 |= 0x0F
            out.append(b0)
            out.extend(__encode_varint62(n))
            out.extend(data)
    else:
        raise TypeError("Unsupported command type")

    if has_cookies:
        out.extend(__encode_varint62(len(cookies)))  # type: ignore[arg-type]
        out.extend(cookies)  # type: ignore[arg-type]

    if has_payload:
        out.extend(__encode_varint62(len(payload)))  # type: ignore[arg-type]
        out.extend(payload)  # type: ignore[arg-type]

    return bytes(out)




"""

payload_type: int 1B
0 - bytes
1 - serialize
2 - TempDataObject
3 - TempDataGroup
4 - FileObject

"""

def unpack_gnresponse_v0(buf: bytes) -> dict:
    if not buf:
        raise ValueError("Empty buffer")

    b0 = buf[0]
    pos = 1

    version = (b0 >> 6) & 0b11
    ctype   = (b0 >> 4) & 0b11
    # Биты флагов перекрываются nibble в микро-кадрах/расш.-без-cp — учитываем это ниже.
    has_cookies_bit = bool((b0 >> 3) & 1)
    has_payload_bit = bool((b0 >> 2) & 1)
    nibble = b0 & 0x0F

    res = {"version": version, "command_type": ctype, "cookies": None, "payload": None}

    if ctype == 0b00:  # bool
        res["command"] = bool((b0 >> 1) & 1)
        microframe = False
        extended_no_cp = False

    elif ctype == 0b01:  # int
        # inline int -> ровно 1 байт в буфере
        microframe = (nibble != 0x0F) and (len(buf) == 1)
        extended_no_cp = (nibble == 0x0F)
        if microframe:
            res["command"] = nibble  # 0..14 inline
        else:
            val, pos = __decode_varint62(buf, pos)
            res["command"] = val

    elif ctype == 0b10:  # str
        # inline str -> общий размер ровно 1 + nibble
        microframe = (nibble != 0x0F) and (len(buf) == 1 + nibble)
        extended_no_cp = (nibble == 0x0F)
        if microframe:
            ln = nibble
            end = pos + ln
            if end > len(buf):
                raise ValueError("Str truncated (inline)")
            res["command"] = buf[pos:end].decode("utf-8")
            pos = end
        else:
            ln, pos = __decode_varint62(buf, pos)
            end = pos + ln
            if end > len(buf):
                raise ValueError("Str truncated")
            res["command"] = buf[pos:end].decode("utf-8")
            pos = end

    elif ctype == 0b11:  # bytes
        microframe = (nibble != 0x0F) and (len(buf) == 1 + nibble)
        extended_no_cp = (nibble == 0x0F)
        if microframe:
            ln = nibble
            end = pos + ln
            if end > len(buf):
                raise ValueError("Bytes truncated (inline)")
            res["command"] = bytes(buf[pos:end])
            pos = end
        else:
            ln, pos = __decode_varint62(buf, pos)
            end = pos + ln
            if end > len(buf):
                raise ValueError("Bytes truncated")
            res["command"] = bytes(buf[pos:end])
            pos = end
    else:
        raise ValueError("Unknown command type")

    # Cookies/payload:
    # — пропускаем целиком для микро-кадров и "расширенного без cp" (там nibble перекрывает флаги),
    # — иначе читаем по флагам.
    if not (ctype in (1, 2, 3) and (microframe or extended_no_cp)):
        if has_cookies_bit:
            ln, pos = __decode_varint62(buf, pos)
            end = pos + ln
            if end > len(buf):
                raise ValueError("Cookies truncated")
            res["cookies"] = bytes(buf[pos:end])
            pos = end

        if has_payload_bit:
            ln, pos = __decode_varint62(buf, pos)
            end = pos + ln
            if end > len(buf):
                raise ValueError("Payload truncated")
            res["payload"] = bytes(buf[pos:end])
            pos = end

    if pos != len(buf):
        raise ValueError("Trailing bytes")
    return res
# ===== GNResponse =====