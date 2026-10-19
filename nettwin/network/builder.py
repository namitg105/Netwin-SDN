"""Turns the plan in nettwin.netmodel into a Mininet network."""
from functools import partial

from mininet.net import Mininet
from mininet.node import OVSSwitch, RemoteController

from nettwin import netmodel

CONTROLLER_IP = "127.0.0.1"
CONTROLLER_PORT = 6653  # Ryu's default OpenFlow port
OPENFLOW_VERSION = "OpenFlow13"  # Fast Failover groups need OpenFlow 1.3


def build(datapath="kernel"):
    """Return an unstarted Mininet network.

    datapath: "kernel" (normal) or "user" for machines whose kernel has no
    Open vSwitch module.
    """
    net = Mininet(
        controller=None,
        switch=partial(OVSSwitch, datapath=datapath, protocols=OPENFLOW_VERSION),
        autoSetMacs=True,
        # The topology has a loop (two paths). Pre-filled ARP tables avoid
        # broadcasts circling forever.
        autoStaticArp=True,
    )
    net.addController("c0", controller=RemoteController,
                      ip=CONTROLLER_IP, port=CONTROLLER_PORT)

    nodes = {}
    for name, dpid in netmodel.SWITCHES.items():
        nodes[name] = net.addSwitch(name, dpid="%x" % dpid)
    for name, ip in netmodel.HOSTS.items():
        nodes[name] = net.addHost(name, ip="%s/%d" % (ip, netmodel.SUBNET_BITS))
    for link in netmodel.LINKS:
        net.addLink(nodes[link.node_a], nodes[link.node_b],
                    port1=link.port_a, port2=link.port_b)
    return net
