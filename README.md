# NOTICE
The Apache Zookeeper charm has been superseded by the Zookeeper charm
from Apache Bigtop:

https://github.com/apache/bigtop/tree/master/bigtop-packages/src/charm/zookeeper/layer-zookeeper

This `layer-apache-zookeeper` repository does not receive regular updates,
and is only here as a reference for legacy deployments.


## Overview
Apache ZooKeeper is a high-performance coordination service for distributed
applications. It exposes common services such as naming, configuration
management, synchronization, and group services in a simple interface so you
don't have to write them from scratch. You can use it off-the-shelf to
implement consensus, group management, leader election, and presence protocols.


## Usage
Deploy a Zookeeper unit. With only one unit, the service will be running in
`standalone` mode:

    juju deploy apache-zookeeper zookeeper


## Scaling
Running ZooKeeper in `standalone` mode is convenient for evaluation, some
development, and testing. But in production, you should run ZooKeeper in
`replicated` mode. A replicated group of servers in the same application is
called a quorum, and in `replicated` mode, all servers in the quorum have
copies of the same configuration file.

Scaling Zookeeper to create a quorum is trivial. The following will add two
additional Zookeeper units and will automatically configure them with knowledge
of the other quorum members based on their peer relation to one another:

    juju add-unit -n 2 zookeeper


## Test the deployment
Test if the Zookeeper service is running by using the `zkServer.sh` script:

    juju run --service=zookeeper '/usr/lib/zookeeper/bin/zkServer.sh status'

A successful deployment will report the service mode as either `standalone`
(if only one Zookeeper unit has been deployed) or `leader` / `follower` (if
a Zookeeper quorum has been formed).


## REST API
Zookeeper REST Api can be enabled/disabled either through an action or
via a config variable:

    juju action do zookeeper/0 start-rest
    juju action do zookeeper/0 stop-rest

or

    juju set zookeeper rest=true

## Integrate Zookeeper into another charm
1) Add following lines to your charm's metadata.yaml:

    requires:
      zookeeper:
         interface: zookeeper

2) Add a `zookeeper-relation-changed` hook to your charm. Example contents:

    from charmhelpers.core.hookenv import relation_get
    ZK_hostname = relation_get('private-address')
    ZK_port = relation_get('port')



## Contact Information
[bigdata@lists.ubuntu.com](mailto:bigdata@lists.ubuntu.com)


## Help
- [Apache Zookeeper home page](https://zookeeper.apache.org/)
- [Apache Zookeeper issue tracker](https://issues.apache.org/jira/browse/ZOOKEEPER)
- [Juju mailing list](https://lists.ubuntu.com/mailman/listinfo/juju)
- [Juju community](https://jujucharms.com/community)
