#!/bin/bash
# One-time setup for Kali Linux (also works on Ubuntu/Debian).
# Installs Mininet, Open vSwitch, Wireshark, Flask, curl and builds the private
# Python 3.9 environment (.ryu-env) that Ryu needs. Safe to run again.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> 1/4 Installing system packages"
sudo apt update
# Non-interactive: Wireshark's "let non-root users capture?" prompt defaults to
# No, which is what we want (we start Wireshark with sudo).
sudo DEBIAN_FRONTEND=noninteractive apt install -y \
    openvswitch-switch wireshark python3-flask curl ethtool pipx git

if ! sudo apt install -y mininet; then
    echo "==> mininet not in apt, installing from source"
    if [ ! -d "$HOME/mininet" ]; then
        git clone https://github.com/mininet/mininet "$HOME/mininet"
    fi
    (cd "$HOME/mininet" && sudo PYTHON=python3 util/install.sh -nv)
fi

echo "==> 2/4 Starting Open vSwitch"
sudo systemctl enable --now openvswitch-switch

echo "==> 3/4 Installing uv and Python 3.9 environment for Ryu"
# pip install ryu fails on the Python that current Kali ships (3.13), so Ryu
# gets its own Python 3.9 inside .ryu-env and nothing else on the system changes.
pipx install uv || true
export PATH="$HOME/.local/bin:$PATH"
if [ ! -d .ryu-env ]; then
    uv venv --python 3.9 .ryu-env
fi
source .ryu-env/bin/activate
uv pip install pip "setuptools==65.5.1" wheel pbr
pip install --no-build-isolation ryu "eventlet==0.30.2"

echo "==> 4/4 Checking the install"
ryu-manager --version
sudo ovs-vsctl show > /dev/null && echo "Open vSwitch: OK"
command -v mn > /dev/null && echo "Mininet: OK"
command -v wireshark > /dev/null && echo "Wireshark: OK"

echo
echo "Setup finished. Next: see README.md (Quick start)."
