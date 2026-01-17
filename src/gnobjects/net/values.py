gn_core_domains = (
    'core',
    'gw',
    'gwis',
    'abs',
    'sys',
    'net'
    )

gn_sys_domains = (
    'gn',
    'vm',
    'net'
    )

gn_domains = (
    'com',
    'net',
    'gov'
)

base_gnrequest_transport = 'gn:quik:net'
base_gnrequest_method = 'get'
base_gnrequest_route = 'gn:net'

common_gnrequest_transports = { # max 15
    'gn:quik:dev': 0,
    'gn:raw:dev': 1,
}


common_gnrequest_methods = { # max 256
    'get': 0,
    'post': 1,
    'put': 2,
    'delete': 3,
    'patch': 4,
    'gn:sys': 7,
}

common_gnrequest_routes = { # max 255
}

common_gnrequest_dataTypes = { # max 16
    'lib': 0,
    'static': 1,
    'api': 2,
    'img': 3,
    'fat': 4,
    'stream': 5
}

common_gnrequest_compressTypes = { # max 16
    'none': 0,
    'zstd': 1
}

base_gnrequest_inType = None

common_gnrequest_inTypes = { # max 256
    'html': 0,
    'css': 1,
    'js': 2,
    'svg': 3,
    'png': 4,
    'py': 5
}


tablex_legacy_mime_type_to_inType = {
    'text/html': 'html',
    'text/css': 'css',
    'application/javascript': 'js',
    'image/svg+xml': 'svg',
    'image/png': 'png'
}

tablex_legacy_inType_to_mime_type = {
    'html': 'text/html',
    'css': 'text/css',
    'js': 'application/javascript',
    'svg': 'image/svg+xml',
    'png': 'image/png'
}

tablex_file_extension_to_inType = {
    'html': 'html',
    'css': 'css',
    'js': 'js',
    'svg': 'svg',
    'png': 'png',
    'py': 'py'
}

tablex_dataTypes_to_transportObject = {
    'lib': 'tdo',
    'static': 'tdo',
    'api': 'api',
    'img': 'tdo',
    'fat': 'tdo',
    'stream': 'stream'
}


# legacy
from ..gwis.values import tablex_gwis_object_types_int_to_str as _tablex_gwis_object_types_int_to_str
tablex_gwiso_type_int_to_str = _tablex_gwis_object_types_int_to_str