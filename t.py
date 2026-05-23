


import gnobjects
from gnobjects.net.objects import Url



# x = Url('gn://@hub/api/x')


# print(x.hostname)



from KeyisBTools.bytes.transformation import userFriendly
import os

x = Url(f'gn://@KeyisB/files/dir1/file1.py')

print(x.hostname)

print(x.path)


a = x.path[1:].split('/', 1)[1]

print(a)


# from gnobjects.gwis import GWISObject


# o = GWISObject(100001, 8)
# print(o.gwisid)
# print(o.objectId)

# o2 = GWISObject(165538, 9)
# print(o2.gwisid)
# print(o2.objectId)