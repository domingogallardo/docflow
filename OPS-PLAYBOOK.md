# Ops Playbook (Host maintenance)

Quick commands to verify the stack, deploy safely, clean legacy endpoints, and keep the host updated for the public site.

## Health checks

```bash
# Nginx (host)
sudo nginx -t && systemctl is-active nginx

# Docker and container
systemctl is-active docker
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'

# Endpoints (public HTTPS)
curl -ksI https://domingogallardo.com/read/ | head -n1   # expect 200
curl -ksI https://domingogallardo.com/posts/ | head -n1  # expect 404

# TLS
certbot certificates
```

## Deploy and clean

```bash
# Deploy (bundles public/ and nginx.conf, rebuilds container)
REMOTE_USER=root REMOTE_HOST=<SERVER_IP> bash web/deploy.sh
# Note: deploy.sh cleans remote /opt/web-domingo/public before extracting to avoid stale files.
```

Mark completed reads (optional before deploy):
```bash
# Edit the curated list: items here will appear BELOW a <hr/> in /read/
$EDITOR web/public/read/read_posts.md

# Preview locally without deploying
python utils/build_read_index.py
open web/public/read/read.html  # or xdg-open on Linux
```

## Ensure container survives reboots

```bash
# Set restart policy and make sure Docker starts on boot
docker update --restart=unless-stopped web-domingo
sudo systemctl enable docker
```

## Reboot and verify

```bash
# Reboot without hanging the SSH session
nohup sh -c 'sleep 1; reboot' >/dev/null 2>&1 &

# Wait a bit, then verify services and endpoints
# (run these after reconnecting)
systemctl is-active docker && systemctl is-active nginx
curl -ksI https://domingogallardo.com/read/ | head -n1   # 200
curl -ksI https://domingogallardo.com/posts/ | head -n1  # 404
```

## Remove legacy /posts (if ever reappears)

```bash
# Find and remove any stray 'posts' directories (inspect output before removal)
sudo find /var/www /usr/share/nginx/html /opt/web-domingo -maxdepth 3 -type d -iname posts -print -exec sudo rm -rf {} +

# Check for nginx references and reload
sudo grep -RinE '/posts(\b|/)' /etc/nginx || true
sudo nginx -t && sudo systemctl reload nginx
```

## Update host packages (Ubuntu)

```bash
export DEBIAN_FRONTEND=noninteractive
sudo apt-get -qq update
sudo apt-get -y -o Dpkg::Options::=--force-confold upgrade
sudo apt-get -y autoremove
sudo apt-get -y autoclean

# Reboot if required
[ -f /var/run/reboot-required ] && echo 'Reboot required'
```
