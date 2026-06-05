tablex_gwis_object_types_int_to_str: dict[int, str] = {
    0: 'gbn',
    2: 'user',
    3: 'company',
    4: 'project',
    5: 'product',
    6: 'service',
    7: 'doo', # Distributed Ownership Object
    8: 'federation',
    9: 'region',
    255: 'freenet' # access from web2
}

gwis_object_types_int_object_id_start: int = 100_000
gwis_object_types_int_object_id_end: int = 281_474_976_710_656

table_gwis_object_types_int_max_object_id: dict[int, int] = {
    9: 2 ** 32
}

table_gwis_object_types_int_ranges: dict[int, tuple[int, int]] = {
    8: (2000, 3000)
}

for o, m in table_gwis_object_types_int_max_object_id.items():
    table_gwis_object_types_int_ranges[o] = (
        gwis_object_types_int_object_id_start, 
        gwis_object_types_int_object_id_start + m
    )
    gwis_object_types_int_object_id_start += m

tablex_gwis_object_types_str_to_int = {value: key for key, value in tablex_gwis_object_types_int_to_str.items()}
