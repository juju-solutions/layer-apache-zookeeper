from charms.reactive import when, when_not
from charms.reactive import set_state

from charmhelpers.core import hookenv

from charms.zookeeper import Zookeeper

from jujubigdata.utils import DistConfig


@when_not('zookeeper.installed')
def install_zookeeper(*args):
    zk = Zookeeper()
    if zk.verify_resources():
        hookenv.status_set('maintenance', 'Installing Zookeeper')
        zk.install()
        hookenv.status_set('active', 'Ready')
        zk.open_ports()
        zk.start()
        set_state('zookeeper.installed')


@when('zookeeper.installed', 'zkpeer.joined')
def quorum_add(zkpeer):
    nodes = zkpeer.get_nodes()
    zk = Zookeeper()
    zk.increase_quorum(nodes)
    zkpeer.dismiss_joined()


@when('zookeeper.installed', 'zkpeer.departed')
def quorum_remove(zkpeer):
    nodes = zkpeer.get_nodes()
    zk = Zookeeper()
    zk.decrease_quorum(nodes)
    zkpeer.dismiss_departed()


@when('zookeeper.installed', 'zkclient.joined')
def serve_client(client):
    port = DistConfig().port('zookeeper')
    client.send_port(port)
