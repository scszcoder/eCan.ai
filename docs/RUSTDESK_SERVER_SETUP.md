# Self-hosted RustDesk server — setup checklist

Goal: remote screen access to alpha customers' PCs (and our own test machines)
without AweSun / 向日葵. RustDesk mirrors the real console session like AweSun
(it does NOT lock the screen the way Windows RDP does, so eCan / 千牛 keep
working while someone watches). We run its ID + relay server ourselves on a
small mainland cloud VM, so connections stay fast inside China and no third
party sits in the middle.

Do this from the server environment, not from a customer PC. Keep the server's
key files out of any repository.

---

## 1. The cloud VM

- [ ] Mainland region close to the users (e.g. Tencent Cloud 上海 / 广州; Lighthouse or CVM).
- [ ] 1–2 vCPU, 2 GB RAM, 20 GB disk, Ubuntu 22.04 LTS. RustDesk's server is tiny; **bandwidth** is what matters (relayed sessions pass through it).
- [ ] Bandwidth: 10 Mbps or more, or pay-by-traffic. A relayed 1080p session uses roughly 1–4 Mbps; most sessions connect directly and use none.
- [ ] A fixed public IP (or an EIP). A domain name is optional — the clients can use the IP.
- [ ] Time sync on (`timedatectl` shows NTP active).

## 2. Ports (cloud security group AND the VM's firewall)

| Port | Protocol | What |
|---|---|---|
| 21115 | TCP | hbbs — NAT type test |
| 21116 | TCP **and** UDP | hbbs — ID registration, heartbeat, hole punching |
| 21117 | TCP | hbbr — relay |

- [ ] Open exactly these in the security group (source 0.0.0.0/0 — clients are everywhere).
- [ ] On the VM: `ufw allow 21115/tcp; ufw allow 21116/tcp; ufw allow 21116/udp; ufw allow 21117/tcp; ufw allow OpenSSH; ufw enable`
- [ ] Do NOT open 21118/21119 (web client) unless you decide you want browser access.
- [ ] SSH: key login only, password login off.

## 3. Install (Docker, pinned version)

- [ ] Install Docker + the compose plugin.
- [ ] `mkdir -p /opt/rustdesk && cd /opt/rustdesk`, create `docker-compose.yml`:

```yaml
services:
  hbbs:
    image: rustdesk/rustdesk-server:1.1.14   # pin a version; check the current release first
    container_name: hbbs
    command: hbbs -r <PUBLIC_IP>:21117 -k _
    volumes: ["./data:/root"]
    network_mode: host
    depends_on: [hbbr]
    restart: unless-stopped
  hbbr:
    image: rustdesk/rustdesk-server:1.1.14
    container_name: hbbr
    command: hbbr -k _
    volumes: ["./data:/root"]
    network_mode: host
    restart: unless-stopped
```

- [ ] `docker compose up -d`
- [ ] `-k _` makes the server **require the key**: clients without our public key cannot register or relay. Keep it.
- [ ] If Docker Hub is slow from the mainland, use a registry mirror, or run the release binaries (`hbbs`, `hbbr`) under systemd instead — same flags.

## 4. The key

- [ ] On first start the server writes `data/id_ed25519` (private) and `data/id_ed25519.pub` (public).
- [ ] `cat /opt/rustdesk/data/id_ed25519.pub` — this one line is the **Key** every client needs.
- [ ] Back up BOTH files somewhere safe (not a repo). Losing them means re-configuring every client.
- [ ] Never share the private key; the public key is fine to hand out.

## 5. Check it works

- [ ] `docker ps` shows hbbs and hbbr running; `docker logs hbbs` has no errors.
- [ ] `ss -lntup | grep 2111` shows 21115/21116(tcp+udp)/21117 listening.
- [ ] From another network: `nc -vz <PUBLIC_IP> 21116` and `nc -vz <PUBLIC_IP> 21117` succeed.

## 6. Clients (customer PCs, our test machines, our own laptops)

- [ ] Use the same RustDesk client version everywhere (pin it; take it from the official GitHub releases).
- [ ] Settings → Network → ID/Relay server:
  - ID server: `<PUBLIC_IP>:21116`
  - Relay server: `<PUBLIC_IP>:21117`
  - Key: the public key from step 4
- [ ] Shortcut for customers: rename the installer to
  `rustdesk-host=<PUBLIC_IP>,key=<PUBLIC_KEY>.exe` — it configures itself on install (no typing).
- [ ] On machines we access unattended (customer test PC, lab VM):
  - Install it (not just run it), so it starts as a service with Windows.
  - Security → set a **strong permanent password** (different per machine); keep "one-time password" too.
  - Keep the connection notification on, so the person at the PC sees when someone connects.
  - Record ID + password in our password manager, never in chat or a repo.
- [ ] Test a session from outside: connects in a few seconds, stays smooth; check the client shows "direct" (P2P) when both sides allow it, "relay" otherwise.

## 7. Customers — before installing on their PC

- [ ] Written OK from the customer: what we access, when (agreed hours), for what (test stores, eCan logs).
- [ ] They can see every session (notification on) and can remove access any time (uninstall or change the password).
- [ ] We only touch eCan, the test stores and the files we agreed on.
- [ ] Keep AweSun until RustDesk has worked on their PC for a few days, then cancel it.

## 8. Running it

- [ ] Logs: `docker logs hbbs` / `hbbr` (connections by ID and IP) — keep for incident checks.
- [ ] Updates: review the release notes, bump the pinned version, `docker compose pull && docker compose up -d`, then test one client.
- [ ] Watch monthly traffic on the cloud bill (relayed sessions).
- [ ] Server rebuilt or moved → restore `data/` (the keys) and keep the same IP, or re-configure every client.

## 9. Optional — the same VM as our private-network relay

The private network (Tailscale / ZeroTier) usually connects machines directly, but inside China it can fall back to slow overseas relays. The same VM can host a mainland relay:
- ZeroTier: run a **moon** on the VM (UDP 9993 open) — simple, no domain needed.
- Tailscale: run **derper** (needs TCP 443 + UDP 3478 and a TLS certificate; a domain on a mainland server may need ICP filing — check before choosing this route).
- Either way, test from the lab and from a customer site: latency should be close to a plain ping between them.
