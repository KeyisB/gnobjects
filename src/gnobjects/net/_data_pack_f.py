from typing import Tuple, Callable, Dict, Literal, Union







def encode_varlen_2358(length: int) -> bytes:
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
    
def decode_varlen_2358(b: bytes) -> tuple[int, int]:
    if len(b) < 2:
        raise ValueError("Insufficient data")

    first = b[0]
    prefix = first >> 6

    if prefix == 0b00:
        size = 2
        bits = 14
    elif prefix == 0b01:
        size = 3
        bits = 22
    elif prefix == 0b10:
        size = 5
        bits = 38
    else:  # 0b11
        size = 8
        bits = 62

    if len(b) < size:
        raise ValueError("Insufficient data")

    v = int.from_bytes(b[:size], "big")
    length = v & ((1 << bits) - 1)

    return length, size

def encode_varlen_1248(length: int) -> bytes:
    if length < (1 << 6):
        # 00 — 1 байт
        v = (0b00 << 6) | length
        return v.to_bytes(1, "big")

    elif length < (1 << 14):
        # 01 — 2 байта
        v = (0b01 << 14) | length
        return v.to_bytes(2, "big")

    elif length < (1 << 30):
        # 10 — 4 байта
        v = (0b10 << 30) | length
        return v.to_bytes(4, "big")

    elif length < (1 << 62):
        # 11 — 8 байт
        v = (0b11 << 62) | length
        return v.to_bytes(8, "big")
    else:
        raise ValueError("Length too large")

def decode_varlen_1248(b: bytes) -> tuple[int, int]:
    first = b[0]
    prefix = first >> 6

    if prefix == 0:
        size = 1
        bits = 6
    elif prefix == 1:
        size = 2
        bits = 14
    elif prefix == 2:
        size = 4
        bits = 30
    else:
        size = 8
        bits = 62

    v = int.from_bytes(b[:size], "big")
    length = v & ((1 << bits) - 1)
    return length, size


VARLEN_ENCODE: Dict[str, Callable[[int], bytes]] = {
    "1248": encode_varlen_1248,
    "2358": encode_varlen_2358,
}

VARLEN_DECODE: Dict[str, Callable[[bytes], Tuple[int, int]]] = {
    "1248": decode_varlen_1248,
    "2358": decode_varlen_2358,
}

_Mode = Union[Literal["1248", "2358"], str]

def encode_data_with_len(data: bytes, mode: _Mode) -> bytes:
    enc = VARLEN_ENCODE.get(mode)
    if enc is None:
        raise ValueError("Unsupported mode")

    length_prefix = enc(len(data))
    return length_prefix + data

def decode_data_with_len(data: bytes, mode: _Mode) -> tuple[bytes, int]:
    dec = VARLEN_DECODE.get(mode)
    if dec is None:
        raise ValueError("Unsupported mode")

    length, prefix_size = dec(data)

    end = prefix_size + length
    if len(data) < end:
        raise ValueError("Insufficient data")

    return data[prefix_size:end], end


def pack_byte_1_1_4_2(a: int, b: int, c: int, d: int) -> int:
    if not (0 <= a < 2):
        raise ValueError("a must be 0..1")
    if not (0 <= b < 2):
        raise ValueError("b must be 0..1")
    if not (0 <= c < 16):
        raise ValueError("c must be 0..15")
    if not (0 <= d < 4):
        raise ValueError("d must be 0..3")

    return (
        (a << 7) |
        (b << 6) |
        (c << 2) |
        d
    )

def unpack_byte_1_1_4_2(x: int) -> tuple[int, int, int, int]:
    if not (0 <= x < 256):
        raise ValueError("x must be 0..255")

    a = (x >> 7) & 0b1
    b = (x >> 6) & 0b1
    c = (x >> 2) & 0b1111
    d = x & 0b11

    return a, b, c, d

def pack_byte_1_7(a: int, b: int) -> int:
    if not (0 <= a < 2):
        raise ValueError("a must be 0..1")
    if not (0 <= b < 128):
        raise ValueError("b must be 0..127")

    return (a << 7) | b

def unpack_byte_1_7(x: int) -> tuple[int, int]:
    if not (0 <= x < 256):
        raise ValueError("x must be 0..255")

    a = (x >> 7) & 0b1
    b = x & 0b1111111

    return a, b