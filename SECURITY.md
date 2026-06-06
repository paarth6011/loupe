# Security Policy

## ⚠️ Before exposing this to a network

This project ships with **development defaults that are not safe for public
deployment**. Change these before putting it on any reachable network:

- **Default credentials.** The admin login defaults to `admin` / `admin`. Set a
  strong `ADMIN_PASSWORD` (and ideally a non-default `ADMIN_USERNAME`).
- **JWT secret.** `JWT_SECRET` defaults to `change-me-in-prod`. Set a long random
  value; anyone who knows it can forge sessions.
- **Secrets in env.** Don't commit real secrets. In a real deployment use a
  secret manager (the GCP Terraform in `infra/` uses Secret Manager).
- **TLS.** Terminate HTTPS in front of the services (load balancer / reverse
  proxy). The app does not do TLS itself.

> Hardening the defaults (refusing to boot with `admin/admin` or a default JWT
> secret) is tracked in [ROADMAP.md](ROADMAP.md).

## Reporting a vulnerability

Please **do not open a public issue** for security problems. Instead, report
privately via GitHub Security Advisories ("Report a vulnerability" on the
repository's Security tab), or by email to the maintainer. We'll acknowledge and
work on a fix as quickly as we can.
