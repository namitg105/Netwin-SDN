#!/bin/bash
# Terminal 1: start the Ryu controller. Always start this BEFORE the network.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -f .ryu-env/bin/activate ]; then
    echo "Ryu environment not found. Run scripts/setup_kali.sh first." >&2
    exit 1
fi
source .ryu-env/bin/activate

# PYTHONPATH lets Ryu import the nettwin package from the repo root.
PYTHONPATH="$PWD" exec ryu-manager nettwin.controller.app
