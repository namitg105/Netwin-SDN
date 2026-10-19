"""Link-health bookkeeping and path ranking.

Pure logic with no OpenFlow or Ryu imports, so it can be unit tested anywhere.
"""


class LinkHealth:
    """Remembers which (dpid, port) links are down and ranks the core paths.

    A path is unhealthy as soon as any one of its ports is down. Healthy paths
    are ranked ahead of unhealthy ones; ties keep the declared order, so the
    primary path wins whenever it is usable.
    """

    def __init__(self, path_ports):
        """`path_ports` maps a path name to the (dpid, port) pairs on it."""
        self._path_ports = dict(path_ports)
        self._down = set()

    def set_link_down(self, dpid, port, down):
        if down:
            self._down.add((dpid, port))
        else:
            self._down.discard((dpid, port))

    def forget_switch(self, dpid):
        """Drop stale state for a switch that has just (re)connected."""
        self._down = {link for link in self._down if link[0] != dpid}

    def is_path_healthy(self, path_name):
        return not (self._down & self._path_ports[path_name])

    def ranked_paths(self):
        """Path names, best first (healthy before unhealthy, declared order)."""
        return sorted(self._path_ports, key=lambda name: not self.is_path_healthy(name))
