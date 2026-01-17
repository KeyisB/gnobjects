

from .values import gn_core_domains, gn_sys_domains, gn_domains

gn_core_domains_p = tuple(['.' + x for x in gn_core_domains])
gn_sys_domains_p = tuple(['.' + x for x in gn_sys_domains])

class GNDomain:
    @staticmethod
    def isSys(domain: str) -> bool:
        return domain.endswith(gn_sys_domains_p)
    @staticmethod
    def isCore(domain: str) -> bool:
        return domain.endswith(gn_core_domains)

