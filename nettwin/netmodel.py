"""Single source of truth for the NetTwin-SDN network plan.

Hosts, switches, links, port numbers and the two core paths are declared once,
here. The Mininet builder and the Ryu controller both derive everything from
this module, so the topology and the forwarding rules cannot drift apart.

Standard library only and Python 3.9 compatible: it is imported by the system
Python (Mininet) and by the Python 3.9 virtualenv that runs Ryu.

              path A
        +====== s2 ======+
        |                |
 c1,c2,c3 == s1          s4 == srv
        |                |
        +====== s3 ======+
              path B
"""
from collections import deque, namedtuple

# A cable between two nodes. A port of None lets Mininet pick one
# (hosts have a single interface; switch ports are fixed on purpose).
Link = namedtuple("Link", ["node_a", "port_a", "node_b", "port_b"])

SUBNET_BITS = 24
SERVER = "srv"
SERVER_PORT = 5000

HOSTS = {  # name -> IPv4 address
    "c1": "10.0.0.1",
    "c2": "10.0.0.2",
    "c3": "10.0.0.3",
    SERVER: "10.0.0.100",
}

SWITCHES = {  # name -> OpenFlow datapath id
    "s1": 1,
    "s2": 2,
    "s3": 3,
    "s4": 4,
}

LINKS = (
    # clients on s1
    Link("c1", None, "s1", 1),
    Link("c2", None, "s1", 2),
    Link("c3", None, "s1", 3),
    # path A: s1 - s2 - s4
    Link("s1", 4, "s2", 1),
    Link("s2", 2, "s4", 1),
    # path B: s1 - s3 - s4
    Link("s1", 5, "s3", 1),
    Link("s3", 2, "s4", 2),
    # server on s4
    Link(SERVER, None, "s4", 3),
)

# Core paths between the two edge switches, most preferred first.
PATHS = {
    "A": ("s1", "s2", "s4"),
    "B": ("s1", "s3", "s4"),
}


# ---------------------------------------------------------------- lookups

def switch_name(dpid):
    """Name of the switch with this datapath id (KeyError if unknown)."""
    for name, known in SWITCHES.items():
        if known == dpid:
            return name
    raise KeyError(dpid)


def _find_link(node, neighbor):
    for link in LINKS:
        if {link.node_a, link.node_b} == {node, neighbor}:
            return link
    raise KeyError((node, neighbor))


def port_toward(node, neighbor):
    """Port number of `node` on its link to `neighbor`."""
    link = _find_link(node, neighbor)
    return link.port_a if link.node_a == node else link.port_b


def host_attachment(host):
    """(switch name, switch port) that `host` is plugged into."""
    for link in LINKS:
        if link.node_a == host:
            return link.node_b, link.port_b
        if link.node_b == host:
            return link.node_a, link.port_a
    raise KeyError(host)


# ------------------------------------------------------------------ paths

def edge_switches():
    """The switches that choose between paths: both ends of every path."""
    first_path = next(iter(PATHS.values()))
    return (first_path[0], first_path[-1])


def is_edge_switch(switch):
    return switch in edge_switches()


def path_ports(path_name):
    """Every (dpid, port) that belongs to a path, used to judge its health."""
    nodes = PATHS[path_name]
    ports = set()
    for left, right in zip(nodes, nodes[1:]):
        ports.add((SWITCHES[left], port_toward(left, right)))
        ports.add((SWITCHES[right], port_toward(right, left)))
    return frozenset(ports)


def uplink_port(edge_switch, path_name):
    """Port of an edge switch that leads onto the given path."""
    nodes = PATHS[path_name]
    neighbor = nodes[1] if nodes[0] == edge_switch else nodes[-2]
    return port_toward(edge_switch, neighbor)


# ---------------------------------------------------------------- routing

def _switch_neighbors(switch):
    """[(local port, neighbouring switch)] sorted by port."""
    found = []
    for link in LINKS:
        if link.node_a == switch and link.node_b in SWITCHES:
            found.append((link.port_a, link.node_b))
        elif link.node_b == switch and link.node_a in SWITCHES:
            found.append((link.port_b, link.node_a))
    return sorted(found)


def _first_hop_port(source, target):
    """Port of `source` on a shortest switch-to-switch path to `target`."""
    queue = deque([(source, None)])
    seen = {source}
    while queue:
        switch, first_port = queue.popleft()
        if switch == target:
            return first_port
        for port, neighbor in _switch_neighbors(switch):
            if neighbor not in seen:
                seen.add(neighbor)
                queue.append((neighbor, port if first_port is None else first_port))
    raise ValueError("no path from %s to %s" % (source, target))


def direct_routes(switch):
    """{destination ip: output port} for destinations with one obvious way.

    Edge switches only list their own hosts; everything else is reached over
    a path chosen by the failover group (see failover_destinations).
    """
    routes = {}
    for host, ip in HOSTS.items():
        home, port = host_attachment(host)
        if home == switch:
            routes[ip] = port
        elif not is_edge_switch(switch):
            routes[ip] = _first_hop_port(switch, home)
    return routes


def failover_destinations(switch):
    """Destination IPs that an edge switch sends into its failover group."""
    if not is_edge_switch(switch):
        return []
    return [ip for host, ip in HOSTS.items() if host_attachment(host)[0] != switch]
