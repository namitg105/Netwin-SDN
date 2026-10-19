# NetTwin-SDN: Simulation Network Setup Guide for Kali Linux

This guide builds the exact network used in our project: one server, three clients, four OpenFlow switches, a primary path and a backup path, a Ryu controller that watches the network, and Wireshark to inspect packets. You will also learn how to cut a link, deny a client, and measure recovery.

Everything runs inside **one Kali machine (a VM is fine)**. No second VM is needed, because Mininet creates all the hosts and switches virtually.

---

## 0. What you are about to build

### The network

```
                 path A (primary)
          +====== s2 ======+
          |                |
 c1,c2,c3 == s1            s4 == srv
          |                |
          +====== s3 ======+
                 path B (backup)
```

| Device | Role | IP address |
|---|---|---|
| c1 | Client 1 | 10.0.0.1 |
| c2 | Client 2 | 10.0.0.2 |
| c3 | Client 3 | 10.0.0.3 |
| srv | Server (Flask) | 10.0.0.100 |
| s1 | Switch next to the clients | none |
| s2 | Core switch, path A | none |
| s3 | Core switch, path B | none |
| s4 | Switch next to the server | none |

### Which port connects to what

You need this table later, because Wireshark interfaces are named after these ports (for example `s1-eth4` means port 4 of switch s1).

| Link | Switch port | Other end |
|---|---|---|
| c1 to s1 | s1 port 1 | c1 |
| c2 to s1 | s1 port 2 | c2 |
| c3 to s1 | s1 port 3 | c3 |
| s1 to s2 (path A) | s1 port 4 | s2 port 1 |
| s2 to s4 (path A) | s2 port 2 | s4 port 1 |
| s1 to s3 (path B) | s1 port 5 | s3 port 1 |
| s3 to s4 (path B) | s3 port 2 | s4 port 2 |
| srv to s4 | s4 port 3 | srv |

### What each tool does here

| Tool | Its job in this project |
|---|---|
| Mininet | Creates the virtual hosts, switches and links on one machine |
| Open vSwitch (OVS) | The actual OpenFlow switch software that Mininet uses for s1 to s4 |
| Ryu | The controller. It installs the forwarding rules and watches for link failures |
| Flask | The small web server running on `srv`. It gives the clients something real to talk to |
| curl | Sends requests from the clients to the server |
| Wireshark | Captures packets on switch ports so you can see traffic and prove failover |
| ovs-ofctl | Command line tool to look at, add and remove rules on a switch by hand |

### The idea in one minute

Switches s1 and s4 each have two ways to reach the other side (path A and path B). We tell them: "use path A, but if the port to path A goes down, use path B instead." In OpenFlow this is called a **Fast Failover Group**. The switch makes the change by itself, so it is almost instant.

There is one catch. If the link between s1 and s2 breaks, s1 notices, but s4 does not, because s4 still has a working link to s2. s4 would keep sending replies into a dead end. So the Ryu controller listens for "link down" events and tells **both** s1 and s4 to prefer path B. That keeps both directions in agreement.

---

## 1. Prepare Kali

### Step 1.1: Update and install the packages

```bash
sudo apt update
sudo apt install -y mininet openvswitch-switch wireshark python3-flask curl ethtool pipx
```

What each one is for: `mininet` and `openvswitch-switch` are the simulator and the switch software. `wireshark` is the packet inspector. `python3-flask` is the server library. `curl` sends test requests. `pipx` is only used in Step 2 to get a Python tool.

During the Wireshark install it asks whether non-root users may capture packets. Pick **No** for now. We will simply start Wireshark with `sudo`, which is easier.

If apt says it cannot find `mininet`, install it from source instead:

```bash
git clone https://github.com/mininet/mininet
cd mininet
sudo PYTHON=python3 util/install.sh -nv
```

### Step 1.2: Start Open vSwitch

```bash
sudo systemctl enable --now openvswitch-switch
```

Mininet's switches are really OVS bridges, so the OVS service must be running first. `enable --now` starts it immediately and also on every boot.

### Step 1.3: Check that it works

```bash
sudo ovs-vsctl show
sudo mn --test pingall
```

The first command should print an OVS version without errors. The second one builds a tiny test network, pings between all hosts and exits. You want to see `0% dropped`. If both work, Mininet and OVS are ready.

If a Mininet run is ever interrupted and things act strangely, clean up with:

```bash
sudo mn -c
```

---

## 2. Install Ryu (read this part, it matters)

On a normal install, `pip install ryu` **fails on the Python version that current Kali ships (3.13)**. Ryu is an older project and breaks on new Python. The reliable fix is to give Ryu its own older Python (3.9) inside a private folder, so it does not touch the rest of your system. We use a tool called `uv` for that.

```bash
pipx install uv
pipx ensurepath
```

Close the terminal and open a new one so the `uv` command is found. Then:

```bash
mkdir -p ~/nettwin
cd ~/nettwin
uv venv --python 3.9 ryu-env
source ryu-env/bin/activate
uv pip install pip "setuptools==65.5.1" wheel pbr
pip install --no-build-isolation ryu "eventlet==0.30.2"
ryu-manager --version
```

Why each line exists:

- `uv venv --python 3.9 ryu-env` creates an isolated Python 3.9 environment named `ryu-env`.
- `source ryu-env/bin/activate` switches your terminal into that environment.
- The old `setuptools`, plus `pbr`, are needed because Ryu's installer uses features that newer versions removed.
- `eventlet==0.30.2` is the version of Ryu's networking library that works with it. Newer versions break Ryu.

The last command must print `ryu-manager 4.34`. If it does, Ryu is ready. Type `deactivate` to leave the environment when you are done with it.

---

## 3. Create the project files

Everything lives in `~/nettwin`. You will create four files.

### File 1: `topo.py` (the network)

This script builds the virtual network from the diagram above.

```python
#!/usr/bin/env python3
from functools import partial

from mininet.cli import CLI
from mininet.log import setLogLevel
from mininet.net import Mininet
from mininet.node import OVSKernelSwitch, RemoteController


def build():
    net = Mininet(
        controller=None,
        switch=partial(OVSKernelSwitch, protocols="OpenFlow13"),
        autoSetMacs=True,
        autoStaticArp=True,
    )
    net.addController("c0", controller=RemoteController, ip="127.0.0.1", port=6653)

    s1 = net.addSwitch("s1", dpid="1")
    s2 = net.addSwitch("s2", dpid="2")
    s3 = net.addSwitch("s3", dpid="3")
    s4 = net.addSwitch("s4", dpid="4")

    c1 = net.addHost("c1", ip="10.0.0.1/24")
    c2 = net.addHost("c2", ip="10.0.0.2/24")
    c3 = net.addHost("c3", ip="10.0.0.3/24")
    srv = net.addHost("srv", ip="10.0.0.100/24")

    # clients on s1 (ports 1, 2, 3)
    net.addLink(c1, s1, port2=1)
    net.addLink(c2, s1, port2=2)
    net.addLink(c3, s1, port2=3)
    # path A: s1 to s2 to s4
    net.addLink(s1, s2, port1=4, port2=1)
    net.addLink(s2, s4, port1=2, port2=1)
    # path B: s1 to s3 to s4
    net.addLink(s1, s3, port1=5, port2=1)
    net.addLink(s3, s4, port1=2, port2=2)
    # server on s4 (port 3)
    net.addLink(srv, s4, port2=3)
    return net


if __name__ == "__main__":
    setLogLevel("info")
    net = build()
    net.start()
    CLI(net)
    net.stop()
```

What the important lines mean:

- `protocols="OpenFlow13"` makes the switches speak OpenFlow 1.3. Fast Failover Groups need it.
- `RemoteController ... port=6653` tells the switches that the controller is a separate program (Ryu) listening on this machine, port 6653 (Ryu's default).
- `dpid="1"` to `"4"` gives each switch a fixed ID, so Ryu can tell s1 from s4.
- `autoStaticArp=True` fills in every host's address table in advance. This matters because our network has loops (two paths). Normal ARP uses broadcasts, and broadcasts in a loop can spin forever. Pre-filling ARP removes the problem.
- `port1=` and `port2=` fix the port numbers, so the table in Section 0 is always true.
- All hosts share one subnet (`10.0.0.0/24`), so the switches only need to forward, not route.

### File 2: `controller.py` (the Ryu controller)

```python
from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3

SERVER = "10.0.0.100"
C1, C2, C3 = "10.0.0.1", "10.0.0.2", "10.0.0.3"

# Switches that choose between the two core paths (A = via s2, B = via s3).
# value = (port towards path A, port towards path B)
UPLINKS = {1: (4, 5), 4: (1, 2)}

# Destinations each switch can reach directly: {dpid: {ip: output port}}
DIRECT = {
    1: {C1: 1, C2: 2, C3: 3},
    2: {C1: 1, C2: 1, C3: 1, SERVER: 2},
    3: {C1: 1, C2: 1, C3: 1, SERVER: 2},
    4: {SERVER: 3},
}

# Destinations that s1 and s4 send into the failover group
VIA_GROUP = {1: [SERVER], 4: [C1, C2, C3]}

# Every (switch, port) that belongs to each path, used to judge path health
PATH_A = {(1, 4), (2, 1), (2, 2), (4, 1)}
PATH_B = {(1, 5), (3, 1), (3, 2), (4, 2)}

GROUP_ID = 1


class NetTwin(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dps = {}      # dpid -> datapath
        self.down = set()  # (dpid, port) pairs whose link is down

    # ---------- when a switch connects ----------
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def on_connect(self, ev):
        dp = ev.msg.datapath
        self.dps[dp.id] = dp
        # forget any link state left over from a previous Mininet run
        self.down = {k for k in self.down if k[0] != dp.id}
        self.logger.info("switch s%d connected", dp.id)
        self.wipe(dp)
        if dp.id in UPLINKS:
            self.send_group(dp, dp.ofproto.OFPGC_ADD)
        self.install_flows(dp)

    def wipe(self, dp):
        ofp, parser = dp.ofproto, dp.ofproto_parser
        dp.send_msg(parser.OFPFlowMod(
            dp, table_id=ofp.OFPTT_ALL, command=ofp.OFPFC_DELETE,
            out_port=ofp.OFPP_ANY, out_group=ofp.OFPG_ANY,
            match=parser.OFPMatch()))
        dp.send_msg(parser.OFPGroupMod(
            dp, ofp.OFPGC_DELETE, ofp.OFPGT_ALL, ofp.OFPG_ALL))

    # ---------- failover group (s1 and s4 only) ----------
    def port_order(self, dpid):
        a, b = UPLINKS[dpid]
        a_bad = bool(self.down & PATH_A)
        b_bad = bool(self.down & PATH_B)
        return [b, a] if (a_bad and not b_bad) else [a, b]

    def send_group(self, dp, command):
        ofp, parser = dp.ofproto, dp.ofproto_parser
        buckets = [
            parser.OFPBucket(watch_port=p, watch_group=ofp.OFPG_ANY,
                             actions=[parser.OFPActionOutput(p)])
            for p in self.port_order(dp.id)
        ]
        dp.send_msg(parser.OFPGroupMod(
            dp, command, ofp.OFPGT_FF, GROUP_ID, buckets))

    # ---------- forwarding rules ----------
    def install_flows(self, dp):
        parser = dp.ofproto_parser
        for ip, port in DIRECT[dp.id].items():
            self.add_flow(dp, ip, [parser.OFPActionOutput(port)])
        for ip in VIA_GROUP.get(dp.id, []):
            self.add_flow(dp, ip, [parser.OFPActionGroup(GROUP_ID)])

    def add_flow(self, dp, dst_ip, actions, priority=10):
        ofp, parser = dp.ofproto, dp.ofproto_parser
        match = parser.OFPMatch(eth_type=0x0800, ipv4_dst=dst_ip)
        inst = [parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)]
        dp.send_msg(parser.OFPFlowMod(
            dp, priority=priority, match=match, instructions=inst))

    # ---------- link up/down events ----------
    @set_ev_cls(ofp_event.EventOFPPortStatus, MAIN_DISPATCHER)
    def on_port_status(self, ev):
        msg = ev.msg
        dp = msg.datapath
        key = (dp.id, msg.desc.port_no)
        if msg.desc.state & dp.ofproto.OFPPS_LINK_DOWN:
            self.down.add(key)
            self.logger.info("LINK DOWN  s%d port %d", *key)
        else:
            self.down.discard(key)
            self.logger.info("LINK UP    s%d port %d", *key)
        # keep both ends of the core in agreement about the best path
        for dpid in UPLINKS:
            if dpid in self.dps:
                self.send_group(self.dps[dpid], self.dps[dpid].ofproto.OFPGC_MODIFY)
        self.logger.info("preferred path: %s",
                         "B (via s3)" if self.port_order(1)[0] == UPLINKS[1][1] else "A (via s2)")
```

How to read it, section by section:

- **The tables at the top** are the whole "plan". `DIRECT` says "on this switch, traffic for this IP leaves through this port." `VIA_GROUP` says "on s1 and s4, traffic for these IPs goes into the failover group instead of a fixed port."
- **`on_connect`** runs when a switch connects to the controller. It clears old rules, creates the failover group (s1 and s4 only), then installs the forwarding rules. Rules are installed in advance (proactively), so no packet ever waits for the controller.
- **`send_group`** builds the Fast Failover Group. Each bucket has a `watch_port`. The switch sends traffic out of the first bucket whose watched port is up. This is the instant, local failover.
- **`on_port_status`** runs when any switch reports a port going up or down. It records the state and re-sends the group to s1 and s4 with the healthy path first. This is the "telemetry" part: the controller keeps a live picture of link health.
- **`PATH_A` and `PATH_B`** list every port on each path, so one broken link anywhere on a path marks the whole path as unhealthy.

### File 3: `server.py` (the web server)

```python
import socket

from flask import Flask, jsonify

app = Flask(__name__)


@app.route("/")
def index():
    return jsonify(message="NetTwin server is alive", host=socket.gethostname())


@app.route("/health")
def health():
    return jsonify(status="ok")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, threaded=True)
```

This is a tiny web server with two pages. `/health` is what the clients will keep asking. `host="0.0.0.0"` makes it listen on all of the host's addresses, so `10.0.0.100:5000` works.

### File 4: `client.sh` (the client loop)

```bash
#!/bin/bash
# usage: ./client.sh c1
# Sends one request to the server every half second and prints what happened.
NAME="${1:-client}"
while true; do
    CODE=$(curl -s -m 1 -o /dev/null -w "%{http_code}" http://10.0.0.100:5000/health)
    if [ "$CODE" = "200" ]; then STATE="OK"; else STATE="FAILED"; fi
    echo "$(date +%H:%M:%S.%3N) $NAME request $STATE (HTTP $CODE)"
    sleep 0.5
done
```

Every half second it asks the server for `/health` and prints a timestamped OK or FAILED line. `-m 1` means "give up after 1 second", so a dead network shows up as FAILED quickly instead of hanging.

Make it runnable:

```bash
chmod +x ~/nettwin/client.sh
```

---

## 4. Start everything (order matters)

You need **three terminals**. Always start the controller first. The switches are set to forward nothing until a controller gives them rules, so if you start Mininet first it will look dead.

### Terminal 1: the controller

```bash
cd ~/nettwin
source ryu-env/bin/activate
ryu-manager controller.py
```

Leave it running. Watch this window during demos, because it prints every link event.

### Terminal 2: the network

```bash
cd ~/nettwin
sudo python3 topo.py
```

You must run this from `~/nettwin`, because the hosts inherit that folder, and later commands use `server.py` and `client.sh` from there. Mininet needs `sudo` because it creates network devices.

In Terminal 1 you should now see four lines, one per switch:

```
switch s1 connected
switch s2 connected
switch s3 connected
switch s4 connected
```

If you do not see them, see Troubleshooting at the end.

Terminal 2 now shows the prompt `mininet>`. This is the Mininet command line. Everything in the next sections is typed there unless it says otherwise.

---

## 5. Check the network is correct

### Step 5.1: Ping everything

```
mininet> pingall
```

Expected: `0% dropped`. This proves every host can reach every other host through the switches.

### Step 5.2: Look at the rules Ryu installed

Open a **third terminal** (Terminal 3) for these:

```bash
sudo ovs-ofctl -O OpenFlow13 dump-groups s1
sudo ovs-ofctl -O OpenFlow13 dump-flows s1
```

The first should show one group of type `ff` (fast failover) with two buckets:

```
group_id=1,type=ff,bucket=watch_port:4,actions=output:4,bucket=watch_port:5,actions=output:5
```

Read it as: "send out of port 4 (path A) while port 4 is up, otherwise port 5 (path B)."

The second shows one rule per destination. The rule for `10.0.0.100` should end in `actions=group:1`, meaning "hand this to the failover group."

Why `-O OpenFlow13`? Because the switches speak OpenFlow 1.3, and the tool must use the same version.

---

## 6. Start the server and the clients

### Step 6.1: Start the server on `srv`

```
mininet> srv python3 server.py > /tmp/server.log 2>&1 &
```

This runs `server.py` inside the `srv` host, in the background, with its messages saved to a log file. Give it two or three seconds to start.

### Step 6.2: Test it once by hand

```
mininet> c1 curl -s http://10.0.0.100:5000/health
```

Expected: `{"status":"ok"}`. If you get nothing, wait a few more seconds and try again.

### Step 6.3: Start the three clients

```
mininet> c1 ./client.sh c1 > /tmp/c1.log 2>&1 &
mininet> c2 ./client.sh c2 > /tmp/c2.log 2>&1 &
mininet> c3 ./client.sh c3 > /tmp/c3.log 2>&1 &
```

Each client now sends a request every half second. To watch them live, open Terminal 3 and run:

```bash
tail -f /tmp/c1.log /tmp/c2.log /tmp/c3.log
```

You should see a steady stream of `request OK (HTTP 200)` lines from all three clients. This is your "normal" state.

---

## 7. Inspect packets with Wireshark

Open Terminal 4 (or reuse one):

```bash
sudo wireshark &
```

Wireshark shows a list of interfaces. Because the switches live in your normal network space, **every switch port appears as an interface**. Pick one based on what you want to see:

| Interface | What you will see there |
|---|---|
| `s1-eth1` | Only client c1's traffic |
| `s1-eth4` | Everything going out on path A from s1 |
| `s1-eth5` | Everything going out on path B from s1 (quiet until a failover) |
| `s4-eth3` | All traffic arriving at and leaving the server |

Double click an interface to start capturing. Useful display filters (type in the bar at the top):

| Filter | Shows |
|---|---|
| `http` | The actual client requests and server replies |
| `tcp.port == 5000` | All traffic to and from the Flask server |
| `ip.src == 10.0.0.2` | Only packets sent by c2 |
| `icmp` | Pings only |

A good first look: capture on `s1-eth4` and `s1-eth5` together (select both with Ctrl, then Start). While everything is healthy you will see traffic only on `s1-eth4`. That is path A in use.

---

## 8. Cut and allow connections

There are two different things you can cut: a **whole link** (a cable breaking) and **one client's access** (a policy decision). Both are shown below.

### 8.1: Deny one client (block c2 from the server)

Open Terminal 3 and add a rule on s1 that drops everything from c2 to the server:

```bash
sudo ovs-ofctl -O OpenFlow13 add-flow s1 "priority=100,ip,nw_src=10.0.0.2,nw_dst=10.0.0.100,actions=drop"
```

Read it as: "if a packet comes from 10.0.0.2 going to 10.0.0.100, drop it. Priority 100 beats Ryu's priority 10 rules, so this wins."

Now watch the client logs. c2 starts printing `FAILED` while c1 and c3 keep printing `OK`. In Wireshark on `s1-eth2` you will still see c2's packets arriving at the switch, but on `s4-eth3` they never appear. That proves the switch dropped them.

To block only web traffic and still allow ping, use a narrower rule:

```bash
sudo ovs-ofctl -O OpenFlow13 add-flow s1 "priority=100,tcp,nw_src=10.0.0.2,nw_dst=10.0.0.100,tp_dst=5000,actions=drop"
```

### 8.2: Allow c2 again

Delete exactly the rule you added:

```bash
sudo ovs-ofctl -O OpenFlow13 --strict del-flows s1 "priority=100,ip,nw_src=10.0.0.2,nw_dst=10.0.0.100"
```

`--strict` makes it remove only the rule with that exact priority and match, so Ryu's normal rules stay untouched. c2 goes back to `OK`.

To see all rules at any time:

```bash
sudo ovs-ofctl -O OpenFlow13 dump-flows s1
```

Note: if you restart Ryu, it clears all rules on connect, including your manual ones.

---

## 9. The main demo: cut a link and watch it heal

### Step 9.1: Start a fast ping so you can measure the gap

```
mininet> c1 ping -i 0.01 -c 1000 10.0.0.100 > /tmp/failover.txt &
```

This sends 100 pings per second for about 10 seconds. Each missing reply later equals 10 milliseconds of outage.

### Step 9.2: Cut the primary path

About a second after starting the ping:

```
mininet> link s1 s2 down
```

What happens, step by step:

1. The link between s1 and s2 goes down.
2. s1's failover group sees port 4 is down and instantly uses port 5 (path B).
3. The controller prints `LINK DOWN` lines and `preferred path: B (via s3)`.
4. The controller tells s4 to prefer path B too, so replies come back the same way.

In Terminal 1 you will see something like:

```
LINK DOWN  s1 port 4
preferred path: B (via s3)
LINK DOWN  s2 port 1
preferred path: B (via s3)
```

In Wireshark, traffic that was on `s1-eth4` moves to `s1-eth5`. The client logs should keep saying `OK`, possibly with one or two `FAILED` lines at the moment of the cut.

### Step 9.3: Read the result

After the ping finishes (about 10 seconds):

```
mininet> sh tail -4 /tmp/failover.txt
```

Look at the line `1000 packets transmitted, N received`. Lost packets times 10 ms is your approximate recovery time. If 3 were lost, that is about 30 ms. Your exact number will depend on your machine, so run it a few times and note the typical value.

### Step 9.4: Bring the link back

```
mininet> link s1 s2 up
```

The controller prints `LINK UP` and `preferred path: A (via s2)`. Traffic returns to path A by itself, because the group always uses the first healthy bucket.

### Step 9.5: Repeat with the far side link

```
mininet> link s2 s4 down
```

This breaks the other half of path A. Here s4 notices the failure directly, but s1 does not, so the controller's job is to tell s1 as well. The clients should still stay connected. Restore with `link s2 s4 up`.

This second test is the one that shows why the controller is needed on top of the switch's own failover.

---

## 10. Before and after (for your graph)

Your report promises a before and after comparison. "After" is everything above. For "before", you need the network to behave like one with **no** self healing. Add a rule that forces s1 to use path A only and ignore the group:

```bash
sudo ovs-ofctl -O OpenFlow13 add-flow s1 "priority=50,ip,nw_dst=10.0.0.100,actions=output:4"
```

Now repeat Steps 9.1 to 9.3 with `link s1 s2 down`. This time the ping will fail until you bring the link back up, so lost packets will be huge. Remove the forcing rule afterward:

```bash
sudo ovs-ofctl -O OpenFlow13 --strict del-flows s1 "priority=50,ip,nw_dst=10.0.0.100"
```

Write down the lost packet counts from both runs, convert them to milliseconds (lost packets times 10), and plot them as two bars with Matplotlib (`sudo apt install python3-matplotlib`). Do each run three times and use the average.

---

## 11. Demo: the link is fine but the server crashed

This is the second kind of failure from our report: the network is healthy but the server is not.

```
mininet> srv pkill -f server.py
mininet> c1 ping -c 3 10.0.0.100
mininet> c1 curl -s -m 2 http://10.0.0.100:5000/health
```

The ping still works (the network is fine), but the curl gets no answer and the client logs turn to `FAILED`. A plain link monitor would miss this. That gap is what the server health check in our design is meant to catch. Restart the server with the command from Step 6.1.

---

## 12. Shutting down and cleaning up

Type `exit` in the `mininet>` prompt, then press Ctrl+C in Terminal 1 to stop Ryu. Always finish with:

```bash
sudo mn -c
```

This removes any leftover virtual links and switches, so the next run starts clean.

---

## 13. Troubleshooting

| Problem | Likely cause and fix |
|---|---|
| Terminal 1 never prints `switch s1 connected` | Ryu was not running, or Mininet was started first. Stop both, run `sudo mn -c`, then start Ryu, then Mininet. |
| `pingall` shows 100% dropped | Ryu is not connected, or you used a different port. The topology expects Ryu on `127.0.0.1:6653`. |
| `pingall` works but `curl` returns nothing | The server needs a few seconds to start. Check `cat /tmp/server.log`. |
| Ping works but curl always hangs | Rarely, a virtual network card corrupts TCP checksums. Run `sudo ethtool -K s1-eth1 tx off rx off` for the affected interfaces, or retry on a different VM network mode. |
| `ryu-manager: command not found` | You forgot `source ryu-env/bin/activate` in that terminal. |
| `ImportError: ALREADY_HANDLED` or `is_timeout` errors from Ryu | Wrong eventlet or Python version. Recreate the environment exactly as in Section 2. |
| `RTNETLINK answers: File exists` when starting Mininet | A previous run was not cleaned. Run `sudo mn -c`. |
| After `link s1 s2 down` everything stops | Check Terminal 1 for `LINK DOWN` lines. If missing, the controller is not receiving port events, so restart Ryu and Mininet in order. |
| Wireshark lists no `s1-eth` interfaces | Mininet is not running, or you started Wireshark before it. Start Mininet first, then reopen Wireshark. |

---

## 14. Cheat sheet

| What | Command |
|---|---|
| Start Ryu | `cd ~/nettwin && source ryu-env/bin/activate && ryu-manager controller.py` |
| Start network | `cd ~/nettwin && sudo python3 topo.py` |
| Test connectivity | `mininet> pingall` |
| Start server | `mininet> srv python3 server.py > /tmp/server.log 2>&1 &` |
| Start a client | `mininet> c1 ./client.sh c1 > /tmp/c1.log 2>&1 &` |
| Cut primary path | `mininet> link s1 s2 down` |
| Restore it | `mininet> link s1 s2 up` |
| Deny c2 | `sudo ovs-ofctl -O OpenFlow13 add-flow s1 "priority=100,ip,nw_src=10.0.0.2,nw_dst=10.0.0.100,actions=drop"` |
| Allow c2 | `sudo ovs-ofctl -O OpenFlow13 --strict del-flows s1 "priority=100,ip,nw_src=10.0.0.2,nw_dst=10.0.0.100"` |
| Show rules | `sudo ovs-ofctl -O OpenFlow13 dump-flows s1` |
| Show failover group | `sudo ovs-ofctl -O OpenFlow13 dump-groups s1` |
| Show group usage | `sudo ovs-ofctl -O OpenFlow13 dump-group-stats s1` |
| Clean up | `sudo mn -c` |

---

## 15. How this matches the project report

| Report topic | Where you see it in this setup |
|---|---|
| Virtual campus network with a backup path | The diamond topology in `topo.py` |
| Ryu controller watching the network | `controller.py`, especially `on_port_status` |
| OpenFlow as the southbound API | Every rule and group Ryu installs on the switches |
| Fast Failover Groups | `send_group`, shown with `dump-groups` |
| Fault detection (link down) | `LINK DOWN` lines in the controller log |
| Server health (server crash, link fine) | Section 11 |
| Demonstration with Wireshark | Section 7 and Step 9.2 |
| Before and after recovery graph | Section 10 |
