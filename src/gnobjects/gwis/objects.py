from .values import tablex_gwis_object_types_int_to_str, table_gwis_object_types_int_ranges


class GWISObject:
    def __init__(self, gwisid: int):
        self.gwisid = gwisid
        self.__object_id = None

    
    def objectId(self, objectType: int):
        """
        # Получение id объекта
        ID объекта кодируется в gwisid

        Поддерживается для:

        - `8` `federation`
        - `9` `region`
        """

        if self.__object_id is not None:
            return self.__object_id

        _r = table_gwis_object_types_int_ranges.get(objectType)
        if _r is None:
            if objectType not in tablex_gwis_object_types_int_to_str:
                raise Exception(f'Unknown object type {objectType}')
            else:
                raise Exception(f'Object type {tablex_gwis_object_types_int_to_str[objectType]} has no supported object_id')
        
        object_id = self.gwisid - _r[0]
        if object_id < 0 or object_id >= _r[1] - _r[0]:
            raise Exception(f'Invalid object_id {self.gwisid} for object type {tablex_gwis_object_types_int_to_str[objectType]}')

        self.__object_id = object_id
        return object_id
    
    @staticmethod
    def fromObjectID(object_id: int, objectType: int):
        return GWISObject(object_id + table_gwis_object_types_int_ranges[objectType][0])

    def toBytes(self) -> bytes:
        """
        # `2B type` `22B 0` `8B gwisid`

        absid:
        - [2B type] - 00
        - [22B 0] - 0 * 22
        - [8B gwisid] - gwisid
        """
        return bytes(24) + self.gwisid.to_bytes(8, 'big')

    def fromBytes(self, data: bytes):
        self.gwisid = int.from_bytes(data[2:10], 'big')