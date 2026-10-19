import unittest

from nettwin import netmodel
from nettwin.controller.failover import LinkHealth


def make_health():
    return LinkHealth({name: netmodel.path_ports(name) for name in netmodel.PATHS})


class LinkHealthTest(unittest.TestCase):
    def test_all_healthy_prefers_primary_path(self):
        self.assertEqual(make_health().ranked_paths(), ["A", "B"])

    def test_any_down_port_on_path_a_demotes_it(self):
        for port in netmodel.path_ports("A"):
            health = make_health()
            health.set_link_down(*port, down=True)
            self.assertEqual(health.ranked_paths(), ["B", "A"], port)

    def test_link_up_restores_primary(self):
        health = make_health()
        health.set_link_down(1, 4, True)
        health.set_link_down(1, 4, False)
        self.assertEqual(health.ranked_paths(), ["A", "B"])

    def test_both_paths_down_keeps_declared_order(self):
        health = make_health()
        health.set_link_down(1, 4, True)
        health.set_link_down(1, 5, True)
        self.assertEqual(health.ranked_paths(), ["A", "B"])

    def test_path_b_failure_leaves_primary_first(self):
        health = make_health()
        health.set_link_down(3, 1, True)
        self.assertEqual(health.ranked_paths(), ["A", "B"])
        self.assertFalse(health.is_path_healthy("B"))

    def test_unrelated_port_does_not_affect_paths(self):
        health = make_health()
        health.set_link_down(1, 1, True)  # c1 access port
        self.assertEqual(health.ranked_paths(), ["A", "B"])

    def test_forget_switch_clears_only_that_switch(self):
        health = make_health()
        health.set_link_down(1, 4, True)
        health.set_link_down(2, 1, True)
        health.forget_switch(1)
        self.assertFalse(health.is_path_healthy("A"))  # (2, 1) still down
        health.forget_switch(2)
        self.assertTrue(health.is_path_healthy("A"))


if __name__ == "__main__":
    unittest.main()
