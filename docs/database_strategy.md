# Database Strategy

## Why Alembic

The backend schema now changes frequently across Mission Blueprint, Cognitive Runtime, Mission Result, Browser Intelligence, validation, scheduler, and product-layer APIs. `Base.metadata.create_all()` can create missing tables, but it does not evolve existing columns, indexes, constraints, or data. Alembic is the authoritative schema migration system because it records schema history and makes every database change explicit.

## Migration Workflow

1. Change ORM models.
2. Create an Alembic revision.
3. Review the generated migration.
4. Add upgrade and downgrade behavior where safe.
5. Run migration upgrade on a local database.
6. Run schema drift validation.
7. Add or update tests.

## Developer Workflow

Use `Base.metadata.create_all()` only for isolated tests or disposable local databases. Live databases should be migrated with Alembic.

Common commands:

```bash
cd backend
alembic upgrade head
python scripts/schema_inventory.py
python scripts/infrastructure_check.py
```

## Production Deployment

1. Back up the database.
2. Run `alembic upgrade head`.
3. Start the backend.
4. Check `/system/schema/drift`.
5. Run a smoke workflow.

Backend startup validates migration state and schema compatibility. It logs incompatible drift instead of silently treating it as healthy.

## Rollback Process

Use Alembic downgrade revisions for reversible migrations. Destructive changes require explicit backup and manual recovery planning. Baseline downgrade is intentionally non-destructive for existing deployments.

## Schema Version Policy

Every persistent schema change must have:

- an Alembic revision
- a short migration description
- a validation test when practical
- backward-compatible handling for existing deployments

No ORM schema change should ship without a matching migration.
