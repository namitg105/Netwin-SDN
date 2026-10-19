# Setup (manual steps)

`bash scripts/setup_kali.sh` does all of this. Use this page to understand it, or to fix one step by hand. Works on Kali; Ubuntu works the same with the same packages.

## 1. System packages

```bash
sudo apt update
sudo apt install -y mininet openvswitch-switch wireshark python3-flask curl ethtool pipx git
```

| Package | Job in this project |
|---|---|
| mininet | Creates the virtual hosts, switches and links on one machine |
| openvswitch-switch | The OpenFlow switch software behind s1 to s4 |
| wireshark | Packet inspection on switch ports |
| python3-flask | The web server on `srv` |
| curl | Sends requests from the clients |
| ethtool | Only needed for the checksum fix in the troubleshooting table |
| pipx | Used to get `uv`, which builds the Python 3.9 environment |

Wireshark asks whether non-root users may capture. Answer **No**; we start it with `sudo`.

If apt cannot find `mininet`, install it from source:

```bash
git clone https://github.com/mininet/mininet
cd mininet
sudo PYTHON=python3 util/install.sh -nv
```

## 2. Start Open vSwitch

```bash
sudo systemctl enable --now openvswitch-switch
sudo ovs-vsctl show
sudo mn --test pingall      # expect 0% dropped
```

Mininet's switches are OVS bridges, so the service must be running. If a Mininet run is interrupted and things act strangely: `bash scripts/cleanup.sh`.

## 3. Ryu in its own Python 3.9

`pip install ryu` **fails on the Python that current Kali ships (3.13)**, because Ryu is an old project. The fix is to give Ryu a private Python 3.9 in `.ryu-env/` inside the repo, which touches nothing else on the system.

```bash
pipx install uv
pipx ensurepath           # then open a new terminal so `uv` is found
uv venv --python 3.9 .ryu-env
source .ryu-env/bin/activate
uv pip install pip "setuptools==65.5.1" wheel pbr
pip install --no-build-isolation ryu "eventlet==0.30.2"
ryu-manager --version     # must print: ryu-manager 4.34
deactivate
```

Why these versions: Ryu's installer needs the old `setuptools` plus `pbr`, and only `eventlet 0.30.2` works with it.

Keep two Pythons apart in your head:

| Part | Python |
|---|---|
| Controller (`nettwin/controller`) | Ryu's 3.9 environment (`scripts/run_controller.sh` activates it) |
| Network and server (`nettwin/network`, `nettwin/server`) | System Python (`scripts/run_network.sh` forces `/usr/bin/python3`) |

`nettwin/netmodel.py` is imported by both, so it stays standard-library only and 3.9 compatible.

## 4. Check

```bash
bash scripts/run_controller.sh     # terminal 1
bash scripts/run_network.sh        # terminal 2
mininet> pingall                   # expect 0% dropped
```

## No Open vSwitch kernel module?

If `run_network.sh` fails because the kernel has no `openvswitch` module (some minimal VMs and containers), use the userspace datapath:

```bash
bash scripts/run_network.sh --datapath user
```

Kali and standard Ubuntu VMs normally do not need this. The userspace datapath corrupts TCP checksums on virtual links, so `curl` hangs until you turn offloading off inside each host (see Troubleshooting in `docs/DEMO.md`).
