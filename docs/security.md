# Security Notes

## Implemented controls

- Argon2id password hashes and no public signup.
- Signed cookie identity plus hashed, revocable server-side session records.
- Absolute session expiry and session revocation when an account is deactivated.
- CSRF validation for login, logout and every state-changing operation.
- Permission checks at route boundaries with a centralized database-backed RBAC matrix.
- Generic invalid-login responses, redacted validation errors and hidden SQL parameters.
- Host-header validation, HSTS in production, frame denial, content-type sniffing protection, a content security policy and restrictive browser feature policy.
- Production API documentation disabled and production cookies forced secure by configuration.

## Deployment requirements

- Terminate TLS at the load balancer and redirect HTTP to HTTPS.
- Set `ENVIRONMENT=production`, `COOKIE_SECURE=true` and exact `ALLOWED_HOSTS`.
- Retrieve database credentials and `SECRET_KEY` from a secret store at runtime.
- Never log request bodies, cookies, CSRF values, password fields or connection strings.
- Give the application database role only the privileges it needs. Use a separately controlled migration procedure if operational policy requires it.
- Restrict RDS to private subnets and accept port 5432 only from the application security group.

## Known MVP limits

The Content Security Policy permits inline scripts because a small number of templates use confirmation/submit helpers. Moving these handlers into the static JavaScript bundle would allow removing `'unsafe-inline'`. Formal audit logging and MFA are recommended before higher-risk or multi-site use.
