import jujuresources
import os
import subprocess
from jujubigdata import utils
from charmhelpers.core import hookenv
from charms.zkutils import update_zoo_cfg, getid
from subprocess import Popen


class Zookeeper(object):
    def __init__(self, dist_config=None):
        self.dist_config = dist_config or utils.DistConfig()
        self.resources = {
            'zookeeper': 'zookeeper-%s' % utils.cpu_arch(),
        }
        self.verify_resources = utils.verify_resources(*self.resources.values())

    def install(self):
        self.dist_config.add_users()
        self.dist_config.add_dirs()
        jujuresources.install(self.resources['zookeeper'],
                              destination=self.dist_config.path('zookeeper'),
                              skip_top_level=True)
        self.build_zkrest()
        self.setup_zookeeper_config()
        self.configure_zookeeper()

    def build_zkrest(self):
        # Zookeeper user needs to compile the rest contrib server.
        # So zookeeper needs to:
        # 1. Have a home dir for ant cache to exist
        # 2. Write to the /usr/lib/zookeeper
        utils.run_as('root', 'mkhomedir_helper', 'zookeeper')
        os.chdir(self.dist_config.path('zookeeper'))
        subprocess.check_call(["chown", "-R", "zookeeper", "."])
        utils.run_as('zookeeper', 'ant')

    def setup_zookeeper_config(self):
        '''
        copy the default configuration files to zookeeper_conf property
        defined in dist.yaml
        '''
        default_conf = self.dist_config.path('zookeeper') / 'conf'
        zookeeper_conf = self.dist_config.path('zookeeper_conf')
        zookeeper_conf.rmtree_p()
        default_conf.copytree(zookeeper_conf)
        # Now remove the conf included in the tarball and symlink our real conf
        default_conf.rmtree_p()
        zookeeper_conf.symlink(default_conf)

        zoo_cfg = zookeeper_conf / 'zoo.cfg'
        if not zoo_cfg.exists():
            (zookeeper_conf / 'zoo_sample.cfg').copy(zoo_cfg)
        utils.re_edit_in_place(zoo_cfg, {
            r'^dataDir.*': 'dataDir={}'.format(self.dist_config.path('zookeeper_data_dir')),
        })

        # Configure zookeeper environment for all users
        zookeeper_bin = self.dist_config.path('zookeeper') / 'bin'
        zookeeper_rest = self.dist_config.path('zookeeper') / 'src/contrib/rest'
        with utils.environment_edit_in_place('/etc/environment') as env:
            if zookeeper_bin not in env['PATH']:
                env['PATH'] = ':'.join([env['PATH'], zookeeper_bin])
            env['ZOOCFGDIR'] = self.dist_config.path('zookeeper_conf')
            env['ZOO_BIN_DIR'] = zookeeper_bin
            env['ZOO_LOG_DIR'] = self.dist_config.path('zookeeper_log_dir')
            env['ZOO_REST'] = zookeeper_rest

    def configure_zookeeper(self):
        '''
        The entries of the form server.X list the servers that make up the ZooKeeper
        service. When the server starts up, it knows which server it is by looking for
        the file myid in the data directory. That file contains the unit number
        in ASCII.
        '''
        myid = self.dist_config.path('zookeeper_data_dir') / 'myid'
        with open(myid, 'w') as df:
            df.writelines(getid(hookenv.local_unit()))

        # update_zoo_cfg maintains a server.X entry in this unit's zoo.cfg
        update_zoo_cfg()

    def increase_quorum(self, node_list):
        for unitId, unitIp in node_list:
            update_zoo_cfg(zkid=getid(unitId), ip=unitIp)

    def decrease_quorum(self, node_list):
        for unitId, unitIp in node_list:
            update_zoo_cfg(zkid=getid(unitId), remove=True)

    def open_ports(self):
        for port in self.dist_config.exposed_ports('zookeeper'):
            hookenv.open_port(port)

    def close_ports(self):
        for port in self.dist_config.exposed_ports('zookeeper'):
            hookenv.close_port(port)

    def start(self):
        zookeeper_home = self.dist_config.path('zookeeper')
        self.stop()
        utils.run_as('zookeeper', '{}/bin/zkServer.sh'.format(zookeeper_home), 'start')
        self.start_rest()

    def stop(self):
        zookeeper_home = self.dist_config.path('zookeeper')
        utils.run_as('zookeeper', '{}/bin/zkServer.sh'.format(zookeeper_home), 'stop')
        self.stop_rest()

    def start_rest(self):
        zookeeper_rest = self.dist_config.path('zookeeper') / 'src/contrib/rest'
        os.chdir(zookeeper_rest)
        try:
            utils.run_as('root', 'pkill', '-f', 'RestMain')
        except:
            pass
        zkrest_logs = self.dist_config.path('zookeeper_log_dir') / 'rest.out'
        self.run_bg('zookeeper', zkrest_logs, 'ant', 'run')

    def stop_rest(self):
        zookeeper_rest = self.dist_config.path('zookeeper') / 'src/contrib/rest'
        os.chdir(zookeeper_rest)
        try:
            utils.run_as('zookeeper', 'pkill', '-f', 'RestMain')
        except:
            pass

    def cleanup(self):
        self.dist_config.remove_dirs()

    def run_bg(self, user, output_log, command, *args):
        """
        Run a command as the given user in the background.

        :param str user: User to run flume agent
        :param str command: Command to run
        :param list args: Additional args to pass to the command
        """
        parts = [command] + list(args)
        quoted = ' '.join("'%s'" % p for p in parts)
        e = utils.read_etc_env()
        Popen(['su', user, '-c', '{} &> {} &'.format(quoted, output_log)],
              env=e)
