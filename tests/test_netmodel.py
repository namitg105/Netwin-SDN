import unittest

from nettwin import netmodel as m


class TopologyConsistencyTest(unittest.TestCase):
    def test_every_link_endpoint_is_a_known_node(self):
        known = set(m.HOSTS) | set(m.SWITCHES)
        for link in m.LINKS:
            self.assertIn(link.node_a, known)
            self.assertIn(link.node_b, known)

    def test_switch_ports_are_unique_per_switch(self):
        seen = set()
        for link in m.LINKS:
            for node, port in ((link.node_a, link.port_a), (link.node_b, link.port_b)):
                if node in m.SWITCHES:
                    self.assertIsNotNone(port)
                    self.assertNotIn((node, port), seen)
                    seen.add((node, port))

    def test_every_host_is_attached_to_exactly_one_switch(self):
        for host in m.HOSTS:
            switch, port = m.host_attachment(host)
            self.assertIn(switch, m.SWITCHES)
            self.assertIsInstance(port, int)

    def test_switch_name_roundtrip(self):
        for name, dpid in m.SWITCHES.items():
            self.assertEqual(m.switch_name(dpid), name)
        with self.assertRaises(KeyError):
            m.switch_name(99)


class DocumentedPortTableTest(unittest.TestCase):
    """The port table in the setup guide must hold, Wireshark names depend on it."""

    def test_client_ports(self):
        self.assertEqual(m.host_attachment("c1"), ("s1", 1))
        self.assertEqual(m.host_attachment("c2"), ("s1", 2))
        self.assertEqual(m.host_attachment("c3"), ("s1", 3))
        self.assertEqual(m.host_attachment("srv"), ("s4", 3))

    def test_core_ports(self):
        self.assertEqual((m.port_toward("s1", "s2"), m.port_toward("s2", "s1")), (4, 1))
        self.assertEqual((m.port_toward("s2", "s4"), m.port_toward("s4", "s2")), (2, 1))
        self.assertEqual((m.port_toward("s1", "s3"), m.port_toward("s3", "s1")), (5, 1))
        self.assertEqual((m.port_toward("s3", "s4"), m.port_toward("s4", "s3")), (2, 2))


class PathTest(unittest.TestCase):
    def test_edge_switches(self):
        self.assertEqual(m.edge_switches(), ("s1", "s4"))
        self.assertTrue(m.is_edge_switch("s1"))
        self.assertFalse(m.is_edge_switch("s2"))

    def test_path_ports(self):
        self.assertEqual(m.path_ports("A"), {(1, 4), (2, 1), (2, 2), (4, 1)})
        self.assertEqual(m.path_ports("B"), {(1, 5), (3, 1), (3, 2), (4, 2)})

    def test_uplink_ports(self):
        self.assertEqual(m.uplink_port("s1", "A"), 4)
        self.assertEqual(m.uplink_port("s1", "B"), 5)
        self.assertEqual(m.uplink_port("s4", "A"), 1)
        self.assertEqual(m.uplink_port("s4", "B"), 2)


class RoutingTest(unittest.TestCase):
    def test_direct_routes(self):
        self.assertEqual(m.direct_routes("s1"),
                         {"10.0.0.1": 1, "10.0.0.2": 2, "10.0.0.3": 3})
        self.assertEqual(m.direct_routes("s4"), {"10.0.0.100": 3})
        for core in ("s2", "s3"):
            self.assertEqual(m.direct_routes(core), {
                "10.0.0.1": 1, "10.0.0.2": 1, "10.0.0.3": 1, "10.0.0.100": 2})

    def test_failover_destinations(self):
        self.assertEqual(m.failover_destinations("s1"), ["10.0.0.100"])
        self.assertEqual(m.failover_destinations("s4"),
                         ["10.0.0.1", "10.0.0.2", "10.0.0.3"])
        self.assertEqual(m.failover_destinations("s2"), [])

    def test_every_switch_can_forward_to_every_host(self):
        for switch in m.SWITCHES:
            covered = set(m.direct_routes(switch)) | set(m.failover_destinations(switch))
            self.assertEqual(covered, set(m.HOSTS.values()), switch)


if __name__ == "__main__":
    unittest.main()
