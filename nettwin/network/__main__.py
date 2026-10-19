"""Start the network and open the Mininet CLI:  sudo python3 -m nettwin.network"""
import argparse

from mininet.cli import CLI
from mininet.log import setLogLevel

from nettwin.network.builder import build


def main():
    parser = argparse.ArgumentParser(description="Start the NetTwin-SDN virtual network.")
    parser.add_argument("--datapath", choices=("kernel", "user"), default="kernel",
                        help="Open vSwitch datapath; use 'user' if the kernel lacks "
                             "the openvswitch module (default: kernel)")
    args = parser.parse_args()

    setLogLevel("info")
    net = build(datapath=args.datapath)
    net.start()
    try:
        CLI(net)
    finally:
        net.stop()


if __name__ == "__main__":
    main()
