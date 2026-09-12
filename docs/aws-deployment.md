# AWS Deployment Preparation

No deployment is performed by these instructions. Review expected monthly costs in the intended AWS region before creating resources.

## Recommended MVP architecture

- **ECR** stores immutable application images tagged with the Git commit SHA.
- **ECS Fargate** runs at least two application tasks across two availability zones when production availability requires it.
- **Application Load Balancer** performs health checks on `/health`, terminates TLS and redirects HTTP to HTTPS.
- **RDS PostgreSQL** runs privately with encryption, automated backups and deletion protection.
- **Secrets Manager** supplies the database password and session `SECRET_KEY`; non-secret settings may use SSM Parameter Store or the task definition.
- **CloudWatch Logs and alarms** cover application logs, unhealthy targets, task restarts, ALB 5xx responses, RDS storage/CPU/connections and backup failures.
- **Route 53 and ACM** provide DNS and a managed TLS certificate.

This is simpler and safer for the MVP than Kubernetes/EKS, removes server patching from the application team and supports rolling task replacement.

## Network and IAM

1. Put the ALB in public subnets and ECS tasks plus RDS in private subnets across at least two availability zones.
2. ALB security group: inbound 443 from the internet; optional 80 only for redirect.
3. ECS security group: application port only from the ALB security group.
4. RDS security group: PostgreSQL only from the ECS security group.
5. Use separate ECS execution and task roles. The execution role needs ECR pull, log delivery and selected secret reads. The application task needs no broad AWS permissions.
6. Never place long-lived AWS access keys in the image, environment file or GitHub workflow.

## Configuration checklist

- `ENVIRONMENT=production`
- a new high-entropy `SECRET_KEY`
- exact public hostname in `ALLOWED_HOSTS`
- `COOKIE_SECURE=true`
- RDS endpoint and database values
- `GYM_TIMEZONE=Africa/Cairo` unless the gym chooses another IANA zone
- ALB health check `/health` with a separate operational database check using `/health/db`

## Release procedure

1. Run CI and build the exact commit image.
2. Scan and push the immutable image to ECR.
3. Confirm a recent RDS backup and available rollback image.
4. Run `alembic upgrade head` once as a controlled one-off ECS task using the new image.
5. Verify `alembic current` reports `b4216f0c8e21` and inspect migration logs.
6. Update the ECS service task definition and wait for ALB target health.
7. Smoke-test login, CSRF, dashboard and one read-only report.
8. Monitor errors, latency, task restarts and database metrics.

Do not run the interactive initial-admin command in normal task startup. Run it once in a protected one-off task with an operator-attached terminal, or use a reviewed secure operational process.

## Backups and recovery

- Enable automated backups, point-in-time recovery and deletion protection.
- Choose retention based on business/legal requirements and create a manual snapshot before risky migrations.
- Regularly test restoring to an isolated RDS instance; an untested backup is not a recovery plan.
- Exporting application CSV reports is not a database backup.

## Rollback

If application verification fails, restore the previous ECS task definition/image. Migrations in this release only add tables and indexes, so application rollback does not require destroying data. Do not automatically run `alembic downgrade` in production. For a future incompatible schema change, use expand/migrate/contract and document a forward-fix plan.

If a migration itself fails, stop the deployment, preserve logs, confirm the database revision, and repair forward from the actual state. Never drop production tables to make the revision marker match.

## Go-live verification

- HTTPS is valid and HTTP redirects.
- Cookies carry Secure, HttpOnly and SameSite attributes.
- `/health` succeeds through the ALB and tasks are healthy.
- RDS is not publicly accessible.
- Secrets are not visible in task definitions, logs or image history.
- Migrations are at head, the first admin exists, RBAC is seeded and critical flows pass.
- CloudWatch alarms and an operator escalation path are active.

**No AWS deployment was performed.**
