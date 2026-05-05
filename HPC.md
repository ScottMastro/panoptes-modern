# Running panoptes on a SLURM HPC

How to run the panoptes server on a cluster while watching the UI
from your laptop. The server has no auth in v1, so where you bind
matters.

## The three layers

Any setup has to answer three questions:

1. **Where does the server run** — login node, dedicated compute
   allocation, or workstation.
2. **How does snakemake reach it** — `127.0.0.1:5050` only works if
   snakemake runs on the *same* host as the server. Submitted-to-SLURM
   jobs run on compute nodes and need a hostname, not localhost.
3. **How does your laptop reach it** — almost always SSH local port
   forwarding (`-L`). The WebSocket goes through the same tunnel
   transparently.

The right answer depends on how long the workflow runs and how strict
your sysadmin is about login-node services.

---

## Setup A — quick & dirty (interactive debugging)

Server, snakemake, and the workflow itself all on the login node.
Smallest blast radius; fine for hours, not for days. Don't do this
for a 12-hour run.

```bash
# On the HPC, terminal 1 — start the server bound to localhost only
ssh user@login.hpc
cd ~/panoptes-modern/server
mkdir -p ~/.panoptes
PANOPTES_DB_URL="sqlite+aiosqlite:///$HOME/.panoptes/panoptes.db" \
  uvicorn panoptes_server.main:app --host 127.0.0.1 --port 5050

# On the HPC, terminal 2 — run snakemake
cd /path/to/snakemake/project
snakemake --logger panoptes \
          --logger-panoptes-url http://127.0.0.1:5050 \
          --cores 4

# On your laptop — open the tunnel and the browser
ssh -N -L 5050:127.0.0.1:5050 user@login.hpc &
open http://localhost:5050
```

The `-N` keeps the SSH session open as a pure tunnel (no shell). Kill
it with `kill %1` when done.

---

## Setup B — snakemake submits to compute nodes via SLURM

Server on the login node, snakemake's SLURM executor schedules rule
jobs across compute nodes. Compute nodes need to POST events back to
the server, which means `localhost` no longer works — use the login
node's hostname.

```bash
# Server, bound so compute nodes can reach it.
# IMPORTANT: 0.0.0.0 exposes it to every other user on the cluster.
# If your sysadmin cares (they should), bind to the login node's
# internal-network interface instead — see "Locking down the bind
# address" below.
uvicorn panoptes_server.main:app --host 0.0.0.0 --port 5050

# Snakemake — point the plugin at the login node by name.
# Replace login01.hpc.internal with whatever `hostname -f` returns
# on your login node.
snakemake --executor slurm \
          --logger panoptes \
          --logger-panoptes-url http://login01.hpc.internal:5050 \
          --jobs 50

# Laptop tunnel — same as Setup A.
ssh -N -L 5050:127.0.0.1:5050 user@login.hpc
```

**Caveats**:
- The login node's hostname must be DNS-resolvable from compute
  nodes. Verify by running `srun -n1 curl -s http://login01.hpc.internal:5050/api/v1/service-info`
  inside a quick allocation; you should see `{"status":"running",...}`.
- Some clusters firewall the login → compute path or only allow
  certain ports. If the curl hangs, ask sysadmin.
- The plugin retries with backoff on connection failure (3 attempts,
  0.5/1/2 seconds), then logs to stderr and continues. Snakemake
  won't crash if the server is briefly unreachable, but you'll lose
  the unflushed events for that batch.

---

## Setup C — server inside a SLURM allocation (long-running, sysadmin-friendly)

Grab a small persistent allocation, run the server inside it. The
allocation gets accounted for like any other job. Use this for
multi-day pipelines.

```bash
# On the HPC — grab a long allocation, note the hostname it gives you
salloc --time=48:00:00 --cpus-per-task=1 --mem=2G --job-name=panoptes
# After salloc starts, you're on the compute node, e.g. cn-024
hostname -f    # → cn-024.hpc.internal

# Inside the allocation — start the server
mkdir -p ~/.panoptes
PANOPTES_DB_URL="sqlite+aiosqlite:///$HOME/.panoptes/panoptes.db" \
  uvicorn panoptes_server.main:app --host 0.0.0.0 --port 5050

# In another shell on the login node — start snakemake
snakemake --executor slurm \
          --logger panoptes \
          --logger-panoptes-url http://cn-024.hpc.internal:5050 \
          --jobs 50

# Laptop — two-hop tunnel: laptop → login node → compute node
ssh -N -L 5050:cn-024.hpc.internal:5050 user@login.hpc
open http://localhost:5050
```

The `cn-024` part changes every time you `salloc`. Capture it with
`hostname -f` and use it in both the snakemake URL and the SSH `-L`
flag. If your cluster's compute node hostnames are *not* DNS-visible
from the login node, replace with the IP from `hostname -i`.

---

## Practical notes

### Database location

- Default is `./panoptes.db` in the server's cwd. That's fine for
  Setup A; for B and C, set `PANOPTES_DB_URL` to a stable path on a
  persistent filesystem (your home dir or a project dir).
- Don't put the DB on `/tmp` or scratch — those get wiped.
- SQLite over NFS is technically supported but flaky under
  concurrent writes. Single-process panoptes only writes from the
  ingest endpoint, so this is rarely an issue in practice.

### Plugin install across nodes

The snakemake conda env / module that the plugin lives in must be
the same one snakemake activates on each compute node. If your env
is in your home dir (typical), one `pip install -e ./plugin` covers
everything. If your env is per-job (rare but possible), the plugin
install needs to be in the conda env that gets activated per rule.

### WebSocket through SSH tunnels

Works transparently — the WebSocket upgrade is just an HTTP request
that turns into a long-lived TCP connection, and SSH forwards that
the same way it forwards anything else. The "live" indicator on the
workflow detail page should light up green within a second or two of
opening the page.

If the indicator stays gray ("polling"), the WS handshake failed.
Usually that's because something between you and the server (a
proxy, an aggressive firewall) doesn't speak WebSocket. The UI falls
back to polling at 2-second intervals; you'll still see updates,
just with up-to-2s latency.

### Stable URL across `salloc` cycles

If you find Setup C's "the cn-XXX hostname keeps changing" annoying,
have your `salloc` script write the hostname to a file and have a
helper alias that reads it:

```bash
# panoptes-start.sh — run inside salloc
hostname -f > ~/.panoptes/host
PANOPTES_DB_URL="sqlite+aiosqlite:///$HOME/.panoptes/panoptes.db" \
  uvicorn panoptes_server.main:app --host 0.0.0.0 --port 5050

# panoptes-tunnel — run on your laptop
HOST=$(ssh user@login.hpc 'cat ~/.panoptes/host')
ssh -N -L 5050:$HOST:5050 user@login.hpc
```

### Locking down the bind address (Setup B/C)

`--host 0.0.0.0` exposes the API to anyone with cluster network
access. There is no auth. Two ways to scope:

1. **Bind to the internal interface explicitly**:
   `ip -4 addr show | grep inet` on the host shows your interfaces.
   Pick the one on the cluster's internal network (often `10.x.x.x`
   or `192.168.x.x`) and pass `--host 10.x.x.x`.
2. **Use SSH ProxyJump from the laptop instead**: keep the server on
   `127.0.0.1` (Setup A pattern) and use the SLURM executor's
   ability to set the panoptes URL via env var on each rule's job
   environment. More fiddly; only worth it if your cluster is
   actively hostile.

The day someone exposes panoptes on a network they don't trust,
build proper auth first (Bearer token, printed at server startup)
and revisit.

### VS Code / Cursor Remote-SSH

Those clients auto-forward any port a process binds to. Open the
panoptes-modern project on the HPC via Remote-SSH, start uvicorn in
the integrated terminal, click "Open in Browser" when it offers.
No manual `ssh -L` needed. WebSocket forwarding works automatically.

---

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `curl` to the server hangs from a compute node | Login → compute firewall, wrong hostname, or server bound to `127.0.0.1` instead of `0.0.0.0`/internal IP |
| Workflow appears in UI but jobs are missing | Plugin couldn't reach server during the rule's run — check the snakemake job's stderr for `[panoptes] failed to ship N events` |
| "live" indicator stays gray | WebSocket handshake blocked. Polling fallback still works. |
| "live" flickers between live and polling | SSH tunnel keepalives. Add `ServerAliveInterval 30` to your `~/.ssh/config` |
| `Started -14351s ago` on workflow page | Server emitting naive timestamps. Should be fixed; rebuild the UI (`cd ui && npm run build`) and check the API directly: timestamps end with `+00:00`. |
| New runs not appearing | Workflows list polls every 2s; should show within that window. If not, check the server is still up (`pgrep uvicorn`). |
| `salloc` allocation killed by SLURM | Time limit hit, or memory exceeded the `--mem` you asked for. Bump and retry. |

---

## What's not covered

- **TLS / wss://** — out of scope for v1. If you need it, terminate
  TLS at a sidecar nginx or use Tailscale to handle the encryption.
- **Multi-user / per-user scoping** — server is global; everyone
  connected sees all workflows. Real auth deferred.
- **Persistent service via systemd** — possible but cluster-specific;
  ask sysadmin.
- **Cloudflared / Tailscale tunnels** — work fine in place of SSH
  `-L` but add an external dependency. SSH is the lowest-common-
  denominator answer.
