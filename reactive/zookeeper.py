from charms.reactive import when, when_file_changed, when_not
from charms.reactive import set_state
from charmhelpers.core import hookenv
from charms.layer.zookeeper import Zookeeper
from jujubigdata.utils import DistConfig


@when_not('zookeeper.installed')
def install_zookeeper(*args):
    zk = Zookeeper()
    if zk.verify_resources():
        hookenv.status_set('maintenance', 'Installing Zookeeper')
        zk.install()
        zk.initial_config()
        set_state('zookeeper.installed')
        hookenv.status_set('maintenance', 'Zookeeper Installed')


@when('zookeeper.installed')
@when_not('zookeeper.started')
def start_zookeeper():
    zk = Zookeeper()
    zk.start()
    zk.open_ports()
    set_state('zookeeper.started')
    hookenv.status_set('active', 'Ready')


@when('zookeeper.started')
@when_file_changed(DistConfig().path('zookeeper_conf') / 'zoo.cfg')
def restart_zookeeper():
    hookenv.status_set('maintenance', 'Server config changed: restarting Zookeeper')
    zk = Zookeeper()
    zk.stop()
    zk.start()
    hookenv.status_set('active', 'Ready')


@when('zookeeper.started', 'config.changed.rest')
def rest_config():
    hookenv.status_set('maintenance', 'Updating REST service')
    zk = Zookeeper()
    config = hookenv.config()
    if config['rest']:
        zk.start_rest()
    else:
        zk.stop_rest()
    hookenv.status_set('active', 'Ready')


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
    config = DistConfig()
    port = config.port('zookeeper')
    rest_port = config.port('zookeeper-rest')
    client.send_port(port, rest_port)
