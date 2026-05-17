


# import gnobjects
# from gnobjects.net.objects import Url



# x = Url("gn://@hub/api/x")


# print(x.hostname)


from gnobjects.gwis import GWISObject


o = GWISObject(100001, 8)
print(o.gwisid)
print(o.objectId)

# o2 = GWISObject(165538, 9)
# print(o2.gwisid)
# print(o2.objectId)