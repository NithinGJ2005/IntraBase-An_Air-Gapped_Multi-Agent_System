# Security Controls

## Authentication

Production requires `AUTH_MODE=oidc`, `ENABLE_DEVELOPMENT_AUTH=false`, an HTTPS OIDC issuer/JWKS URL, an audience, and a persistent audit-log path. The service validates signed tokens, issuer, audience, expiry, and subject. It accepts only RS256 or ES256 for OIDC tokens.

`AUTH_MODE=development` is solely an isolated local/test adapter. It requires a separate HS256 signing secret and is rejected by production configuration validation. It is not an SSO substitute.

## Authorization

Roles are read only from a verified token and map to permissions through `ROLE_PERMISSION_MAP`, which is server-side configuration. No request body or arbitrary client header can select a user, role, or permission. The default role map is empty, so access is denied until an administrator configures an approved mapping.

Current permissions are `chat:use`, `documents:search`, `database:read`, and `admin:diagnostics`. Each protected endpoint independently checks its required permission. Document and database-level authorization will be added with those services in later phases.

## Audit records

Authentication and authorization decisions record a timestamp, actor where authenticated, action, decision, request ID, and resource identifier. Tokens, passwords, raw prompts, and data results are excluded. In development/tests an in-memory sink is used; production requires an append-only JSONL target protected by filesystem permissions and an organization-defined retention process.

## SSO onboarding prerequisites

IT must supply the OIDC issuer, JWKS endpoint, audience, claim-to-role conventions, approved role-to-permission map, TLS trust policy, audit-log location/access controls, and retention requirements. None are guessed by this project.
