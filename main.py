from cloudbox.api import app
from cloudbox.nebula.nebula import Network
from rich import print

net = Network()
net.create_host("lh",
                is_lighthouse=True,
                public_ip='fd42:f8f4:bee9:96d7:1266:6aff:fe96:4a1c',
                )
net.create_host("Fred", is_lighthouse=False)
net.create_host("John", is_lighthouse=False)

print(net.hosts)
