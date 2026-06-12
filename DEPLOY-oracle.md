# Deploy Loupe free on an Oracle Cloud "Always Free" VM

Runs the **whole stack on one VM** — backend, Postgres, Redis, frontend — behind
**Caddy** (automatic HTTPS), on a free **DuckDNS** subdomain. **No domain to buy,
$0/month.** Uses `docker-compose.prod.yml` + `infra/caddy/Caddyfile`.

```
browser ─https─▶ YOUR.duckdns.org ─▶ Caddy ─┬─ /api/* ─▶ backend ─▶ Postgres + Redis
                 (Oracle VM IP)             └─ /*     ─▶ frontend (SPA)
```

The frontend (`/`) and API (`/api`) share one host, so they're **same-origin —
no CORS to configure**.

---

## Part 1 — Things you do in a browser (one-time)

### 1. Create an Oracle Cloud Always Free account
<https://www.oracle.com/cloud/free/> — needs a card for identity verification but
**Always Free resources are never charged**. (Pick a home region close to you.)

### 2. Launch the VM
Compute → Instances → **Create instance**:
- **Image:** Ubuntu 22.04
- **Shape:** `VM.Standard.A1.Flex` (Ampere **ARM**, Always Free). Give it
  **2 OCPU / 12 GB** — comfortably within the always-free allowance and plenty
  for this stack.
- **Add your SSH public key** (you'll need it to log in).
- Create, then note the **public IP**.

> ⚠️ **"Out of host capacity"** on the ARM shape is common in busy regions. Retry,
> try a different Availability Domain, or as a fallback use a `VM.Standard.E2.1.Micro`
> (AMD, 1 GB — works but tight; add swap). The ARM shape is worth the retries.

### 3. Open ports 80 and 443
Two layers must allow them:
- **VCN security list:** Networking → your VCN → its subnet → Security List → add
  **Ingress** rules for TCP **80** and **443** from `0.0.0.0/0`.
- (The Ubuntu image's host firewall is handled in Part 2, step 3.)

### 4. Get a free DuckDNS subdomain
<https://www.duckdns.org> → sign in (GitHub/Google) → create a subdomain (e.g.
`loupe-paarth`) → set its **IP** to your VM's public IP. Your URL is now
`https://loupe-paarth.duckdns.org`.

---

## Part 2 — On the VM (SSH in)

```bash
ssh ubuntu@YOUR_VM_PUBLIC_IP
```

### 1. Install Docker (includes the compose plugin)
```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER && newgrp docker   # run docker without sudo
```

### 2. Get the code
```bash
git clone https://github.com/paarth6011/loupe.git
cd loupe
```

### 3. Open the host firewall (Oracle Ubuntu ships restrictive iptables)
```bash
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save
```

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
First build on ARM takes a few minutes. Caddy then fetches the Let's Encrypt cert
automatically (needs ports 80/443 reachable — that's why we opened both layers).

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

- **Changed `PUBLIC_URL`?** The frontend bakes it at build time — rebuild with
  `up -d --build` so the new URL takes effect.
- **Cert didn't issue?** Almost always ports 80/443 aren't reachable — re-check
  *both* the VCN security list and the host iptables, and that DuckDNS points at
  the right IP.
- **ARM images:** everything here (Postgres, Redis, Node, Python, Caddy) has
  arm64 images and builds natively on the VM — nothing special to do.
- **Cost:** $0 as long as you stay on Always Free shapes. The VM has no idle
  spin-down, so the dashboard and live updates are always on.
