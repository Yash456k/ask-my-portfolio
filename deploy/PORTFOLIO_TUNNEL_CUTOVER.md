# Portfolio API cutover — completed 14 September 2026 IST

The website remains on Vercel. Its API now travels through Cloudflare Tunnel to the existing restricted Caddy proxy on Hermes. The old direct public API is closed.

## Deployment

- Website: https://www.yash456k.com
- API: https://api.yash456k.com
- Vercel deployment: https://rag-playground-b4mkk51ah-yashs-projects-98b2c247.vercel.app
- Deployment ID: dpl_44ps36pSWxR2iAy5yoh7zThbrh9H — READY, production, with www/apex aliases verified.
- Project: rag-playground, yash's projects (prj_f3AfEUsAZUvdmWceCfu4AwdAukSO).
- GitHub: Yash456k/rag-playground, main, frontend/; commit c7d83ca49e0a01fcbc7d8f092e380a4abc3e47a2.
- Production, preview and development VITE_API_URL settings were updated successfully to https://api.yash456k.com. The development proxy default was committed to main.
- Typecheck, lint, 18 frontend tests, production build and GitHub CI passed: https://github.com/Yash456k/rag-playground/actions/runs/34772093376

## Tunnel and exposure

- Cloudflare account ownership was matched to the existing Hermes certificate and the signed-in account. api.yash456k.com was unused.
- Tunnel: portfolio-api-hermes, UUID 426b432b-41e6-4ad9-9636-00dd43b16f8a.
- Route: Cloudflare → cloudflared on Hermes → 127.0.0.1:18081 → existing Caddy container :8081 → API :8000.
- Root systemd service cloudflared-portfolio.service is active, enabled at boot, Restart=always, and uses a restricted dynamic user.
- Config lives at /etc/cloudflared-portfolio/config.yml; unit at /etc/systemd/system/cloudflared-portfolio.service. The tunnel-specific credential is provided through systemd LoadCredential. The login certificate remains in place and was never copied or displayed. Live tunnel configuration and credentials are not committed to Git.
- Only the API hostname is routed; unmatched tunnel requests return 404.
- Docker publications are now loopback-only: API 18080, proxy 18081, database configured at 55432. Public TCP 80/443 and UDP 443 publications were removed.
- UFW retains its deny-incoming default and SSH rule; the old 80/443 allowances were removed for IPv4 and IPv6.
- Outside-Hermes TCP probes to 178.104.56.243 ports 80, 443, 18080, 18081 and 55432 all failed as expected. No public HTTP/HTTPS listener remains.
- Main-site DNS, nameservers, email, SSH and Tailscale configuration were untouched. Private Tailscale HTTPS remains served separately. API and database container IDs did not change.

## Verification evidence

- HTTPS health/config/activity returned 200 through the tunnel, before and after closing direct access.
- Allowed-origin CORS/preflight passed; an untrusted origin received no access-control permission.
- Activity JSON and ETag revalidation passed: repeat GET with If-None-Match returned 304. Proxy compression initially modified the validator; the tunnel listener now preserves it using no-transform and leaves compression off at Caddy.
- Oversized JSON was rejected with 413; /docs, /openapi.json, /metrics and /v1/admin returned 404.
- The old API returned 200 throughout the parallel phase and was closed only after a successful production browser answer.
- Real Brave browser: graph/config/chat requested api.yash456k.com; no CORS/CSP or console warnings/errors were observed.
- Before closure: a complete NSK answer with seven sources finished in approximately 3.7 seconds.
- After closure: a complete retrieval explanation with seven sources finished in 7.416 seconds. Network response was HTTP 200, text/event-stream, with 54 token events, one done event, no error event and a completed network request.
- Final RAG request ID: d9e4aedf-f145-48d6-bdb7-3e307f1bb65c; requested/served DeepSeek V4 Flash, no fallback.
- Visitor IPs are trusted only from the host gateway on the dedicated tunnel listener. Caddy uses Cloudflare's visitor header there, overwrites X-Real-IP upstream, and strips both operator verification headers.
- Spoofed X-Real-IP/X-Forwarded-For values did not change the recovered visitor identity. A completed request's persisted quota hash matched the actual visitor, not the tunnel gateway.
- All existing non-root/read-only/capability, database separation, host/private-network isolation and provider-connectivity checks passed. Container attempts to use the tunnel route with a forged visitor header received 404; the host loopback port remained unreachable from the API container.
- No CAPTCHA/challenge settings were added. Cloudflare's existing edge checks reject the default Python urllib user-agent (1010); normal browser, curl and explicitly identified verification clients passed.

## Rollback

Do these in order if rollback is needed; do not switch the frontend back before restoring the old origin.

1. On Hermes, restore /var/backups/portfolio-tunnel-20260913/dual-compose.yml to /opt/rag-playground/docker-compose.yml and dual-Caddyfile to /opt/rag-playground/deploy/Caddyfile. These backups retain both old access and the tunnel.
2. Validate Caddy, then run sudo docker compose up -d --no-deps proxy from /opt/rag-playground. Restore the previous UFW 80/tcp and 443/tcp allows. Verify https://178-104-56-243.sslip.io/v1/health returns 200.
3. Set VITE_API_URL back to https://178-104-56-243.sslip.io in production, preview and development. Restore Vercel's previous production deployment dpl_cjLDpJUK6ggf8hs7qXWBec1eoELi (rag-playground-383f1auwv-yashs-projects-98b2c247.vercel.app).
4. Revert frontend commit c7d83ca49e0a01fcbc7d8f092e380a4abc3e47a2 if the development default should also return to the old address. Retest graph and streamed chat.
5. Leave the tunnel active until rollback browser checks pass. Do not modify main-site DNS or the existing unrelated tunnel.

The initial server configuration and UFW backup are also retained under /var/backups/portfolio-tunnel-20260913/. Run python3 /opt/rag-playground/scripts/verify_host_isolation.py to validate the final tunnel-only state; its closed-port assertions intentionally fail during a rollback that reopens direct access.
