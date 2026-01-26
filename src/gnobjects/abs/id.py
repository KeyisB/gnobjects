"""
abs_id: 32B -> bytes:
[
    object_type: 2B -> int;
    fcms_id: 2B -> int;
    rcms_id: 2B -> int;
    inc_id: 26B -> bytes;
]
"""

class AbsId:
    @staticmethod
    def from_bytes_to_dict(data: bytes) -> dict:
        """
        ```python
        from bytes (32B)
        
        return data: {
            'object_type': int (2B),
            'fcms_id': int (2B),
            'rcms_id': int (2B),
            'inc_id': bytes (26B),
        }
        ```
        """
        if len(data) != 32:
            raise ValueError("Data must be exactly 32 bytes long")
        
        object_type = int.from_bytes(data[0:2], byteorder='big')
        fcms_id = int.from_bytes(data[2:4], byteorder='big')
        rcms_id = int.from_bytes(data[4:6], byteorder='big')
        inc_id = data[6:32]
        
        return {
            'object_type': object_type,
            'fcms_id': fcms_id,
            'rcms_id': rcms_id,
            'inc_id': inc_id
        }

    @staticmethod
    def from_dict_to_bytes(data: dict) -> bytes:
        """
        ```python
        from data: {
            'object_type': int (2B),
            'fcms_id': int (2B),
            'rcms_id': int (2B),
            'inc_id': bytes (26B),
        }
        
        return bytes (32B)
        ```
        """
        object_type = data['object_type'].to_bytes(2, byteorder='big')
        fcms_id = data['fcms_id'].to_bytes(2, byteorder='big')
        rcms_id = data['rcms_id'].to_bytes(2, byteorder='big')
        inc_id = data['inc_id']
        
        if len(inc_id) != 26:
            raise ValueError("inc_id must be exactly 26 bytes long")
        
        return object_type + fcms_id + rcms_id + inc_id
    @staticmethod
    def from_abs_to_gwis(data: bytes) -> int:
        """
        `32B => 8B`
        
        00 00 00 00 00 00 | 00 ... 00 (18B) | gwisid (8B)
        """
        if len(data) != 32:
            raise ValueError("Data must be exactly 32 bytes long")
        
        _ = int.from_bytes(data[0:6], byteorder='big')
        if _ != 0:
            raise ValueError("The first 6 bytes must be zero")
        gwis_bytes = data[24:32]
        gwisid = int.from_bytes(gwis_bytes, byteorder='big')
        return gwisid


    @staticmethod
    def from_gwis_to_abs(gwisid: int) -> bytes:
        """
        `8B => 32B`
        """
        gwis_bytes = gwisid.to_bytes(8, byteorder='big')
        return b'\x00' * 6 + b'\x00' * 18 + gwis_bytes
    
    @staticmethod
    def is_abs_id_gwisid(data: bytes) -> bool:
        """
        Check if the given abs_id corresponds to a gwisid format.
        """
        if len(data) != 32:
            raise ValueError("Data must be exactly 32 bytes long")
        
        return all(b == 0 for b in data[0:24])