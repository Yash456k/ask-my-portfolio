# Same-host public API hardening

The public RAG/portfolio API is not an agent and must never gain a tool loop, public ingestion endpoint, arbitrary URL fetcher, or credentials from Hermes. Only the reviewed public corpus belongs in retrieval; chunk text is deliberately returned to visitors.

## Deployment boundary

- API UID10001, PostgreSQL UID999, proxy UID10002; all Linux capabilities dropped and no-new-privileges set.
- All container root filesystems read-only. API models, activity snapshot and model-artifact mounts read-only; bounded tmpfs scratch directories only. PostgreSQL data and Caddy certificate/config named volumes remain writable for their functions.
- DB uses separate internal network `rag-playground-db-private` (`172.30.251.0/29`, bridge `br-rag-db`). Only API joins both networks. Proxy cannot directly access DB.
- Public bridge subnet `172.18.0.0/16`; API `.3`, proxy `.4`. These IPs are pinned because trusted-proxy and host-isolation rules depend on them.
- Root-owned `/etc/rag-isolation.nft`, installed from `deploy/host-isolation.nft`, denies new container connections into the host and blocks routed private/tailnet/link-local destinations. Explicit API→DB and proxy→API links remain; API/proxy may use public HTTPS/DNS. This is public HTTPS egress allowance, **not domain-level egress allowlisting**.
- `rag-isolation.service` runs before Docker; Docker has a Requires/After dependency. Its root-owned apply helper atomically replaces only its own nftables table. UFW, Tailscale and SSH rules are otherwise unchanged. Never flush the entire nftables ruleset.
- Networks have IPv6 disabled. Reassess firewall coverage before enabling IPv6 or changing subnets.

## Credentials and database

- `.env` holds operator/bootstrap database credentials and deployment values. Never mount or send it to the public API.
- `.env.runtime` (0600, ignored by Git and Docker build context) contains only required runtime settings and the `rag_runtime` database login. It does not contain Codex, Hermes, Gmail, Telegram, SSH, or database-admin credentials.
- `rag_runtime` is not a superuser and has no role/database creation, replication, or bypass-RLS privileges. SELECT on documents/chunks; SELECT/INSERT/UPDATE/DELETE on quota/log tables. Connection/statement/lock limits bound DB work. See `sql/runtime-role-grants.sql`.
- `DATABASE_BOOTSTRAP_SCHEMA=false` for the public API. Run schema migrations/ingestion separately as operator using `.env`, then start the restricted runtime. Do not grant DDL privileges merely to make startup migration work.
- Existing named PostgreSQL volume must be UID999-writable; certificate/config volumes UID10002-writable. Prepare ownership during deployment, not from the public runtime.
- Graph updates remain a one-way host-side credential reader → sanitized JSON handoff. Public visitors cannot trigger the updater; schema validation strips unrecognized fields.

## HTTP controls

- Public proxy allows only `/v1/health`, `/v1/config`, `/v1/activity`, `/v1/chat`. Everything else returns404. Extra methods still pass through application method validation.
- Caddy overwrites X-Real-IP and strips X-Verify-Evaluation/X-Verify-Fallback on public traffic. Operator verification stays on local/private paths.
- App trusts only proxy `172.18.0.4/32`; browser origins are explicit, but CORS is not authorization.
- Body size capped at32KiB at edge and app; read-header/body/write/idle timeouts bounded.
- Process-local pre-DB burst and streaming concurrency admission supplements durable daily/monthly quotas. Current deployment must retain a single worker unless limits are re-designed for multiple workers.
- Detailed health checks are coalesced/cached briefly. Public provider errors use fixed reason codes, not provider-controlled diagnostic text.

## Verification and operation

Run `python3 scripts/verify_host_isolation.py` from the host. It checks running container properties, live SQL denial, filesystem denial, private service TCP denial, provider reachability, and public endpoints without printing secrets.

After image updates: run the test suite, verify public SSE completion/citations and activity ETag304, and repeat isolation checks. Audit dependencies with the complete installed-package inventory, not just direct requirements. Inference remains pinned to the qualified model stack; model-converter/training advisories are not proof of a public exploit, but need reassessment if model inputs or tools are ever exposed.

Deployment-specific rollback snapshot: `/var/backups/rag-hardening-20260913/` (root-only), including prior compose/Caddy/.env and database dump; prior image tag `rag-playground-api:pre-hardening-20260913`. Rolling back networking/rootfs changes requires matching compose, private environment, certificate volume ownership and firewall rules. Never drop a database volume or restore a stale DB dump as a first response to a failed API rollout.

No finite hardening checklist makes a shared kernel immune to escape bugs or volumetric DDoS. Provider-level protection and prompt OS/dependency updates remain necessary; these controls primarily reduce reachability and blast radius.
