import jujuresources
from charms.reactive import when, when_not
from charms.reactive import set_state
from charmhelpers.core import hookenv
from jujubigdata.utils import DistConfig
from charms.zookeeper import Zookeeper


def dist_config():
    if not getattr(dist_config, 'value', None):
        zookeeper_reqs = ['vendor', 'packages',  'groups', 'users', 'dirs', 'ports']
        dist_config.value = DistConfig(filename='dist.yaml', required_keys=zookeeper_reqs)
    return dist_config.value


@when_not('zookeeper.installed')
def install_zookeeper(*args):
    zk = Zookeeper(dist_config())
    if zk.verify_resources():
        hookenv.status_set('maintenance', 'Installing Zookeeper')
        zk.install()
        set_state('zookeeper.installed')
        hookenv.status_set('active', 'Ready')
        zk.start()


@when('zookeeper.installed', 'instance.related')
def quorum_incresed(instances):
    nodes = instances.get_nodes()
    zk = Zookeeper(dist_config())
    zk.increase_quorum(nodes)


@when('zookeeper.installed', 'instance.departing')
def quorum_decreased(instances):
    nodes = instances.get_nodes()
    instances.dismiss()
    zk = Zookeeper(dist_config())
    zk.decrease_quorum(nodes)
    

@when('zookeeper.installed', 'zkclient.connected')
def zk_client_connected(client):
    config = dist_config()
    port = config.port('zookeeper')
    client.send_port(port)
