# Deploy Loupe free on a Google Cloud "Always Free" e2-micro VM

Runs the **whole stack on one VM** — backend, Postgres, Redis, frontend — behind
**Caddy** (automatic HTTPS), on a free **DuckDNS** subdomain. **No domain to buy,
$0/month.** Uses `docker-compose.prod.yml` + `infra/caddy/Caddyfile` (the same files
as every other single-host target — only the VM-creation steps below are GCP-specific).

```
browser ─https─▶ YOUR.duckdns.org ─▶ Caddy ─┬─ /api/* ─▶ backend ─▶ Postgres + Redis
                 (GCP static IP)             └─ /*     ─▶ frontend (SPA)
```

The frontend (`/`) and API (`/api`) share one host, so they're **same-origin —
no CORS to configure**.

> **About the box:** the Always Free `e2-micro` has **1 GB RAM**. The stack *runs*
> fine in that, but the first image **build** can run out of memory. We fix that with
> a **2 GB swap file** (Part 2, step 2). For a low-traffic demo/portfolio site this is
> plenty.

---

## Part 1 — Things you do in a browser (one-time)

### 1. Create a Google Cloud account
<https://cloud.google.com/free> → "Get started for free". Needs a card for identity
verification; the **Always Free** `e2-micro` tier is **never charged** as long as you
stay within it. You also get a 90-day trial credit on top, but we won't need it.

### 2. Make a project
Top bar → project dropdown → **New Project** (e.g. `loupe`). Select it. Then enable
the **Compute Engine API** when prompted (Console → Compute Engine → Instances will
prompt you the first time; takes a minute).

### 3. Reserve a static external IP (so DuckDNS survives reboots)
An ephemeral IP changes if the VM ever stops/starts — which would break your DuckDNS
record and your TLS cert. Reserve a static one (free **while attached to a running
instance**):
- VPC network → **IP addresses** → **Reserve external static address**
- Name `loupe-ip`, **Region** = the region you'll use below (`us-west1`, the closest
  free region to Singapore — lowest latency of the three),
  **Standard** tier, **IPv4**. Reserve it and note the IP.

> Always-Free regions are **`us-west1`, `us-central1`, `us-east1` only** — pick one and
> use it for the IP *and* the VM.

### 4. Launch the VM
Compute Engine → **VM instances** → **Create instance**:
- **Name:** `loupe`
- **Region:** **`us-west1`** (must match the IP's region from step 3)
- **Machine type:** series **E2**, type **`e2-micro`** (this is the Always Free shape)
- **Boot disk:** change to **Ubuntu 22.04 LTS**, **30 GB Standard** persistent disk
  (30 GB std is the free allowance — don't exceed it)
- **Firewall:** tick **Allow HTTP traffic** and **Allow HTTPS traffic** (this opens
  80/443 at the network level — no host firewall step needed later)
- **Networking** → expand → **Network interfaces** → set **External IPv4 address** to
  the `loupe-ip` you reserved in step 3
- Create, then note that it shows your reserved IP.

### 5. Add your SSH key (to log in from your own terminal)
Generate a key pair if you don't already have one (the name is just a label):

```bash
ssh-keygen -t ed25519 -f ~/.ssh/loupe_gcp -C loupe-gcp
```

GCP keys are tagged with the login username. Copy your **public** key line
(`cat ~/.ssh/loupe_gcp.pub`), then:

- VM instances → click **loupe** → **Edit** → **Security and access** → **SSH Keys** →
  **Add item** → paste the line **prefixed with the username**, like:
  `ubuntu:ssh-ed25519 AAAA... loupe-gcp`
  (the `ubuntu:` prefix tells GCP this key logs in as user `ubuntu`) → **Save**.

> **Don't want to bother with keys?** GCP's in-browser **SSH** button (next to the VM)
> just works with no key setup. Use that and skip straight to Part 2 step 1's commands.

### 6. Get a free DuckDNS subdomain
<https://www.duckdns.org> → sign in (GitHub/Google) → create a subdomain (e.g.
`loupe-paarth`) → set its **IP** to your **reserved static IP**. Your URL is now
`https://loupe-paarth.duckdns.org`.

---

## Part 2 — On the VM (SSH in)

```bash
ssh -i ~/.ssh/loupe_gcp ubuntu@YOUR_STATIC_IP
```
(or just click the **SSH** button in the GCP console).

### 1. Install Docker (includes the compose plugin)
```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER && newgrp docker   # run docker without sudo
```

### 2. Add 2 GB swap (so the 1 GB box can build images without OOM)
```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab   # persist across reboots
free -h                                                       # confirm swap shows 2.0Gi
```

### 3. Get the code
```bash
git clone https://github.com/paarth6011/loupe.git
cd loupe
```

> No host-firewall step here — unlike Oracle, GCP's Ubuntu image doesn't ship
> restrictive iptables; the "Allow HTTP/HTTPS" boxes from Part 1 step 4 already opened
> 80/443.

### 4. Configure secrets
```bash
cp .env.prod.example .env
nano .env
```
Set:
- `PUBLIC_URL=https://loupe-paarth.duckdns.org` and `PUBLIC_DOMAIN=loupe-paarth.duckdns.org`
- strong `POSTGRES_PASSWORD`, `JWT_SECRET`, `ADMIN_PASSWORD`
  (e.g. generate with `openssl rand -hex 32`)
- optionally `ANTHROPIC_API_KEY` for Claude-written incident summaries

### 5. Launch
```bash
docker compose -f docker-compose.prod.yml up -d --build
```
First build on `e2-micro` is slow (a few minutes — the swap is what keeps it from
OOM-ing). Caddy then fetches the Let's Encrypt cert automatically (needs ports 80/443
reachable — handled by the firewall boxes in Part 1).

Watch it come up:
```bash
docker compose -f docker-compose.prod.yml logs -f caddy backend
```

### 6. Open it
Visit **`https://YOUR-SUBDOMAIN.duckdns.org`** and log in with `admin` / your
`ADMIN_PASSWORD`. Create an API key in the dashboard and point an instrumented app
at it (`LOUPE_API_KEY`) to start sending real data.

---

## Day-2

**Update to latest:**
```bash
cd ~/loupe && git pull && docker compose -f docker-compose.prod.yml up -d --build
```

**Logs / status:**
```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f backend
```

**Stop / tear down (data is in named volumes; `-v` also wipes the DB):**
```bash
docker compose -f docker-compose.prod.yml down       # stop, keep data
docker compose -f docker-compose.prod.yml down -v     # stop + delete all data
```

## Gotchas

- **1 GB RAM is tight.** If a build still OOM-errors, build the images on your laptop
  and push them, or bump swap to 4 G. At idle the running stack fits comfortably.
- **Keep the IP attached.** A reserved static IP is free *only while attached to a
  running instance* — if you delete the VM but keep the IP, GCP bills a few cents/day.
  Release the IP when you tear the VM down.
- **Changed `PUBLIC_URL`?** The frontend bakes it at build time — rebuild with
  `up -d --build` so the new URL takes effect.
- **Cert didn't issue?** Almost always 80/443 aren't reachable — re-check the
  "Allow HTTP/HTTPS" firewall rules and that DuckDNS points at your **static** IP.
- **Stay in an Always-Free region** (`us-west1`/`us-central1`/`us-east1`) and on the
  `e2-micro` shape with a 30 GB standard disk — that's what keeps it $0.
- **Egress:** 1 GB/month of North-America egress is free; a demo dashboard is nowhere
  near that.
