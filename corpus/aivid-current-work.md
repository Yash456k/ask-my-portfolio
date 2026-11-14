<!-- rag-chunk: aivid-mobile-alerts | AIVID Techvision current work: the mobile alert server, the React Native alerts app, and mobile access security -->
# Yash's current work at AIVID Techvision

AIVID Techvision's platform raises alerts from camera detections. Since March 2026, first as an intern and as a Software Engineer since June 2026, Yash built the company's mobile alert server alone, from an empty repository, on Fastify, Prisma and PostgreSQL. It pushes each camera alert to phones first and attaches the alert's images in a follow-up call, so slow image reads cannot hold up the alert.

He also wrote the React Native alerts app as its only developer, rebuilding it on Expo SDK 55 with a filtered alert feed, images, and acknowledge, reject or silence actions. He secured mobile access with per-tenant, per-user and per-camera checks, SHA-256 hashed single-device tokens, and HMAC-SHA256 signed sync with Redis replay protection.

<!-- rag-chunk: aivid-escalation-retention | AIVID Techvision current work: alert escalation design, the zero-retention mode, who hosts the mobile server, and which numbers are not published -->
## Alert escalation and data retention at AIVID Techvision

Yash designed staged alert escalation across 6 repositories. Escalation policies are published as versioned Redis snapshots that apply to the next alert without a redeploy, Redis claims per event and stage make parallel worker pods send each stage only once, and escalation stops when someone acknowledges the alert. He also added a zero-retention mode across 5 repositories that still pushes alerts to phones but stores no alert rows or images.

He wrote the Kubernetes manifests for the mobile server; the company's DevOps team hosts and deploys it. His portfolio does not publish customer, user or alert counts for this work.
