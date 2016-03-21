import time
import jujuresources
from charmhelpers.core.hookenv import (local_unit, unit_private_ip,
                                       open_port, close_port, log, config)
from charmhelpers.core.host import chownr, chdir
from charmhelpers.core import unitdata
from jujubigdata import utils
from subprocess import CalledProcessError, check_output


def getid(unit_id):
    """Utility function to return the unit number."""
    return unit_id.split("/")[1]


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
        self.setup_zookeeper_config()

    def init_zkrest(self):
        # Zookeeper user needs to compile the rest contrib server.
        # So zookeeper needs to:
        # 1. Have a home dir for ant cache to exist
        # 2. Write to the /usr/lib/zookeeper
        chownr(self.dist_config.path('zookeeper'), 'zookeeper', 'zookeeper', chowntopdir=True)
        with chdir(self.dist_config.path('zookeeper')):
            utils.run_as('zookeeper', 'ant')
        unitdata.kv().set('rest.initialised', True)

    def setup_zookeeper_config(self):
        """Setup Zookeeper configuration based on default config.

        Copy the default configuration files to zookeeper_conf property
        defined in dist.yaml
        """
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
            env['ZOO_REST_DIR'] = zookeeper_rest

    def initial_config(self):
        """Perform initial Zookeeper configuration.

        The entries of the form server.X list the servers that make up the ZooKeeper
        service. When the server starts up, it knows which server it is by looking for
        the file 'myid' in the data directory. That file contains the unit number
        in ASCII.

        After, 'myid' is written, this function will call update_zoo_cfg() with
        default values to populate zoo.cfg with this local unit's info.
        """
        myid = self.dist_config.path('zookeeper_data_dir') / 'myid'
        with open(myid, 'w') as df:
            df.writelines(getid(local_unit()))

        # update_zoo_cfg maintains a server.X entry in this unit's zoo.cfg
        self.update_zoo_cfg()

    def increase_quorum(self, node_list):
        for unitId, unitIp in node_list:
            self.update_zoo_cfg(zkid=getid(unitId), ip=unitIp)

    def decrease_quorum(self, node_list):
        for unitId, unitIp in node_list:
            self.update_zoo_cfg(zkid=getid(unitId), remove=True)

    def open_ports(self):
        for port in self.dist_config.exposed_ports('zookeeper'):
            open_port(port)

    def close_ports(self):
        for port in self.dist_config.exposed_ports('zookeeper'):
            close_port(port)

    def start(self):
        zookeeper_home = self.dist_config.path('zookeeper')
        utils.run_as('zookeeper', '{}/bin/zkServer.sh'.format(zookeeper_home), 'start')
        if config().get('rest'):
            self.start_rest()

    def stop(self):
        zookeeper_home = self.dist_config.path('zookeeper')
        utils.run_as('zookeeper', '{}/bin/zkServer.sh'.format(zookeeper_home), 'stop')
        self.stop_rest()

    def start_rest(self):
        if not unitdata.kv().get('rest.initialised'):
            log("Initialising REST API")
            self.init_zkrest()
        self.stop_rest()
        zookeeper_rest = self.dist_config.path('zookeeper') / 'src/contrib/rest'
        zkrest_logs = self.dist_config.path('zookeeper_log_dir') / 'rest.out'
        zkrest_buildxml = zookeeper_rest / 'build.xml'

        utils.run_bg_as('zookeeper', zkrest_logs, 'nohup', 'ant', 'run', '-f', zkrest_buildxml)
        # We set a generous timeout here, for _realy_ slow networks.
        pids = self.wait_process_start('RestMain', 240, 'zookeeper')

        if len(pids) == 0:
            raise Exception("Zookeeper REST API did not start.")
        if len(pids) > 1:
            raise Exception("Multiple Zookeeper REST API servers running.")
        log("REST API started (pid: {})".format(pids[0]))

    def stop_rest(self):
        pids = self.wait_process_start('RestMain', 0, 'zookeeper')
        if len(pids) != 0:
            utils.run_as('root', 'pkill', '-f', 'RestMain')

    def cleanup(self):
        self.dist_config.remove_dirs()

    def update_zoo_cfg(self, zkid=getid(local_unit()), ip=unit_private_ip(), remove=False):
        """Add or remove Zookeeper units from zoo.cfg.

        Configuration for a Zookeeper quorum requires listing all unique servers
        (server.X=<ip>:2888:3888) in the zoo.cfg. This function manages server.X
        entries.
        """
        zookeeper_cfg = "{}/zoo.cfg".format(self.dist_config.path('zookeeper_conf'))
        key = "server.{}".format(zkid)
        value = "={}:2888:3888".format(ip)
        found = False
        if remove:
            with open(zookeeper_cfg, 'r', encoding='utf-8') as f:
                contents = f.readlines()
                for l in range(0, len(contents)):
                    if contents[l].startswith(key):
                        contents.pop(l)
                        found = True
                        break
            if found:
                with open(zookeeper_cfg, 'w', encoding='utf-8') as f:
                    f.writelines(contents)
        else:
            with open(zookeeper_cfg, 'r', encoding='utf-8') as f:
                contents = f.readlines()
                for l in range(0, len(contents)):
                    if contents[l].startswith(key):
                        contents[l] = key + value + "\n"
                        found = True
            if not found:
                contents.append(key + value + "\n")
            with open(zookeeper_cfg, 'w', encoding='utf-8') as f:
                f.writelines(contents)

    def get_zk_count(self):
        """Return a count of all zookeeper servers in zoo.cfg."""
        zookeeper_cfg = "{}/zoo.cfg".format(self.dist_config.path('zookeeper_conf'))
        try:
            return check_output(['grep', '-c', '^server\.[0-9]', zookeeper_cfg])
        except CalledProcessError:
            print ("Could not grep %s" % zookeeper_cfg)

    def wait_process_start(self, name, wait_secs, user=None):
        """
        Wait for a process to appear and return its pid

        :param str name: Cmd pattern to search for
        :param int wait_sec: Seconds to wait for the process to spawn
        :param string user: Owner of the process
        :returns: list of process ids found. May return an empty list
        """
        timeout = time.time() + wait_secs
        pgrep_args = ['pgrep', '-f', name]
        if user:
            pgrep_args += ['-u', user]

        while True:
            try:
                pids = check_output(pgrep_args)
                return pids.splitlines()
            except CalledProcessError:
                log("REST service not running")

            if time.time() > timeout:
                return []

            time.sleep(5)
