"""Builds and sends OpenFlow 1.3 messages to a single switch.

This is the only place that knows OpenFlow message details. It decides nothing:
callers say *what* the switch should do, this class says it in OpenFlow.
"""

FAILOVER_GROUP_ID = 1
ROUTE_PRIORITY = 10
ETH_TYPE_IPV4 = 0x0800


class SwitchProgrammer:
    def __init__(self, datapath):
        self._dp = datapath
        self._ofp = datapath.ofproto
        self._parser = datapath.ofproto_parser

    def reset(self):
        """Delete every flow rule and group left on the switch."""
        ofp, parser = self._ofp, self._parser
        self._dp.send_msg(parser.OFPFlowMod(
            self._dp, table_id=ofp.OFPTT_ALL, command=ofp.OFPFC_DELETE,
            out_port=ofp.OFPP_ANY, out_group=ofp.OFPG_ANY,
            match=parser.OFPMatch()))
        self._dp.send_msg(parser.OFPGroupMod(
            self._dp, ofp.OFPGC_DELETE, ofp.OFPGT_ALL, ofp.OFPG_ALL))

    def route_to_port(self, dst_ip, out_port):
        """Send IPv4 traffic for `dst_ip` out of one fixed port."""
        self._add_route(dst_ip, [self._parser.OFPActionOutput(out_port)])

    def route_to_group(self, dst_ip):
        """Send IPv4 traffic for `dst_ip` into the failover group."""
        self._add_route(dst_ip, [self._parser.OFPActionGroup(FAILOVER_GROUP_ID)])

    def add_failover_group(self, ports):
        """Create the fast-failover group: first bucket whose port is up wins."""
        self._send_group(self._ofp.OFPGC_ADD, ports)

    def update_failover_group(self, ports):
        """Re-order the buckets of the existing failover group."""
        self._send_group(self._ofp.OFPGC_MODIFY, ports)

    def _send_group(self, command, ports):
        ofp, parser = self._ofp, self._parser
        buckets = [
            parser.OFPBucket(watch_port=port, watch_group=ofp.OFPG_ANY,
                             actions=[parser.OFPActionOutput(port)])
            for port in ports
        ]
        self._dp.send_msg(parser.OFPGroupMod(
            self._dp, command, ofp.OFPGT_FF, FAILOVER_GROUP_ID, buckets))

    def _add_route(self, dst_ip, actions):
        ofp, parser = self._ofp, self._parser
        match = parser.OFPMatch(eth_type=ETH_TYPE_IPV4, ipv4_dst=dst_ip)
        instructions = [parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)]
        self._dp.send_msg(parser.OFPFlowMod(
            self._dp, priority=ROUTE_PRIORITY, match=match, instructions=instructions))
