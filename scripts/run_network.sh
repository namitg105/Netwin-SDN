#!/bin/bash
# Terminal 2: start the virtual network and open the mininet> prompt.
# Extra arguments are passed on, e.g.  scripts/run_network.sh --datapath user
set -euo pipefail
cd "$(dirname "$0")/.."

# Always the system Python (Mininet lives there), never the Ryu virtualenv.
# sudo keeps the working directory, so `-m nettwin.network` finds the package,
# and Mininet hosts inherit the repo root (they run nettwin.server and scripts/).
exec sudo /usr/bin/python3 -m nettwin.network "$@"
