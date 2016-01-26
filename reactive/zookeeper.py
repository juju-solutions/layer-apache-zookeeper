import jujuresources
from charms.reactive import when, when_not
from charms.reactive import set_state, remove_state
from charmhelpers.core import hookenv
from subprocess import check_call
from glob import glob

def dist_config():
    from jujubigdata.utils import DistConfig  # no available until after bootstrap

    if not getattr(dist_config, 'value', None):
        zookeeper_reqs = ['vendor', 'packages',  'groups', 'users', 'dirs', 'ports']
        dist_config.value = DistConfig(filename='dist.yaml', required_keys=zookeeper_reqs)
    return dist_config.value


@when_not('bootstrapped')
def bootstrap():
    hookenv.status_set('maintenance', 'Installing base resources')
    check_call(['apt-get', 'install', '-yq', 'python-pip', 'bzr'])
    archives = glob('resources/python/*')
    check_call(['pip', 'install'] + archives)

    """
    Install required resources defined in resources.yaml
    """
    mirror_url = jujuresources.config_get('resources_mirror')
    if not jujuresources.fetch(mirror_url=mirror_url):
        missing = jujuresources.invalid()
        hookenv.status_set('blocked', 'Unable to fetch required resource%s: %s' % (
            's' if len(missing) > 1 else '',
            ', '.join(missing),
        ))
        return False

    set_state('bootstrapped')
    return True

@when('bootstrapped')
@when_not('zookeeper.installed')
def install_zookeeper(*args):
    from charms.zookeeper import Zookeeper  # in lib/charms; not available until after bootstrap

    zk = Zookeeper(dist_config())
    if zk.verify_resources():
        hookenv.status_set('maintenance', 'Installing Zookeeper')
        zk.install()
        set_state('zookeeper.installed')
        hookenv.status_set('active', 'Ready')
        zk.start()
