"""NetTwin Ryu application: reacts to OpenFlow events and delegates the work.

Run with:  scripts/run_controller.sh

    * netmodel         decides *what* the network looks like and which ports matter
    * LinkHealth       decides *which path* is best right now
    * SwitchProgrammer decides *how* to say it in OpenFlow
This class only wires those three to Ryu's events.
"""
from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3

from nettwin import netmodel
from nettwin.controller.failover import LinkHealth
from nettwin.controller.programmer import SwitchProgrammer


class NetTwin(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._programmers = {}  # switch name -> SwitchProgrammer
        self._health = LinkHealth(
            {name: netmodel.path_ports(name) for name in netmodel.PATHS})

    # ------------------------------------------------ a switch connects
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def on_switch_connected(self, ev):
        datapath = ev.msg.datapath
        try:
            switch = netmodel.switch_name(datapath.id)
        except KeyError:
            self.logger.warning("ignoring unknown switch dpid=%s", datapath.id)
            return

        programmer = SwitchProgrammer(datapath)
        self._programmers[switch] = programmer
        self._health.forget_switch(datapath.id)  # drop state from an earlier run
        self.logger.info("switch %s connected", switch)

        programmer.reset()
        self._install_forwarding(switch, programmer)

    def _install_forwarding(self, switch, programmer):
        """Proactive rules: installed up front so no packet waits for Ryu."""
        if netmodel.is_edge_switch(switch):
            programmer.add_failover_group(self._uplink_ports(switch))
        for ip, port in netmodel.direct_routes(switch).items():
            programmer.route_to_port(ip, port)
        for ip in netmodel.failover_destinations(switch):
            programmer.route_to_group(ip)

    # ------------------------------------------------ a link goes up/down
    @set_ev_cls(ofp_event.EventOFPPortStatus, MAIN_DISPATCHER)
    def on_port_status(self, ev):
        msg = ev.msg
        dpid, port = msg.datapath.id, msg.desc.port_no
        is_down = bool(msg.desc.state & msg.datapath.ofproto.OFPPS_LINK_DOWN)

        self._health.set_link_down(dpid, port, is_down)
        self.logger.info("%s s%d port %d", "LINK DOWN " if is_down else "LINK UP   ",
                         dpid, port)
        self._refresh_failover_groups()

    def _refresh_failover_groups(self):
        """Keep both edge switches agreeing on the best path.

        A switch only notices its own dead port; the far edge switch would keep
        sending replies into the break. Re-ordering both groups fixes that.
        """
        for edge in netmodel.edge_switches():
            programmer = self._programmers.get(edge)
            if programmer is not None:
                programmer.update_failover_group(self._uplink_ports(edge))
        best = self._health.ranked_paths()[0]
        self.logger.info("preferred path: %s (via %s)", best,
                         ", ".join(netmodel.PATHS[best][1:-1]))

    def _uplink_ports(self, edge):
        return [netmodel.uplink_port(edge, path) for path in self._health.ranked_paths()]
