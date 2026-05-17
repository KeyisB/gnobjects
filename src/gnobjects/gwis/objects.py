from .values import tablex_gwis_object_types_int_to_str, table_gwis_object_types_int_ranges


class GWISObject:
    def __init__(self, gwisid: int, type: int):
        self.gwisid = gwisid
        self.type = type
        self.__object_id = None

    @property
    def objectId(self):
        """
        # Получение id объекта
        ID объекта кодируется в gwisid

        Поддерживается для:

        - `8` `federation`
        - `9` `region`
        """

        if self.__object_id is not None:
            return self.__object_id

        _r = table_gwis_object_types_int_ranges.get(self.type)
        if _r is None:
            if self.type not in tablex_gwis_object_types_int_to_str:
                raise Exception(f'Unknown object type {self.type}')
            else:
                raise Exception(f'Object type {tablex_gwis_object_types_int_to_str[self.type]} has no supported object_id')
        
        object_id = self.gwisid - _r[0]
        if object_id < 0 or object_id >= _r[1] - _r[0]:
            raise Exception(f'Invalid object_id {self.gwisid} for object type {tablex_gwis_object_types_int_to_str[self.type]}')

        self.__object_id = object_id
        return object_id
    
    @staticmethod
    def fromObjectID(object_id: int, type: int):
        return GWISObject(object_id + table_gwis_object_types_int_ranges[type][0], type)