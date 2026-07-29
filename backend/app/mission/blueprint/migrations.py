"""Mission Blueprint V1 Wave 1B additive migration metadata.

The current application registers SQLAlchemy models and creates tables through
Base.metadata.create_all() on startup. These statements document the equivalent
additive DDL and rollback plan for environments that adopt explicit migrations.
"""

BLUEPRINT_TABLES = [
    "mission_blueprints",
    "mission_blueprint_revisions",
    "mission_blueprint_nodes",
    "mission_blueprint_dependencies",
    "mission_blueprint_readiness_snapshots",
    "mission_blueprint_expansions",
]

UPGRADE_SQL = [
    """
    CREATE TABLE IF NOT EXISTS mission_blueprints (
        blueprint_id VARCHAR PRIMARY KEY,
        mission_id VARCHAR NOT NULL,
        schema_version VARCHAR NOT NULL,
        objective TEXT NOT NULL,
        revision INTEGER NOT NULL DEFAULT 1,
        status VARCHAR NOT NULL DEFAULT 'active',
        constraints JSON,
        success_criteria JSON,
        recovery_rules JSON,
        termination_rules JSON,
        approval_policy JSON,
        blueprint_metadata JSON,
        snapshot JSON,
        created_at TIMESTAMP NOT NULL,
        updated_at TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS mission_blueprint_revisions (
        revision_id VARCHAR PRIMARY KEY,
        blueprint_id VARCHAR NOT NULL REFERENCES mission_blueprints(blueprint_id) ON DELETE CASCADE,
        mission_id VARCHAR NOT NULL,
        revision INTEGER NOT NULL,
        reason TEXT,
        created_by VARCHAR,
        snapshot JSON,
        created_at TIMESTAMP NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS mission_blueprint_nodes (
        node_record_id VARCHAR PRIMARY KEY,
        blueprint_id VARCHAR NOT NULL REFERENCES mission_blueprints(blueprint_id) ON DELETE CASCADE,
        revision_id VARCHAR NOT NULL REFERENCES mission_blueprint_revisions(revision_id) ON DELETE CASCADE,
        mission_id VARCHAR NOT NULL,
        node_id VARCHAR NOT NULL,
        kind VARCHAR NOT NULL,
        state VARCHAR NOT NULL,
        objective TEXT NOT NULL,
        priority INTEGER NOT NULL DEFAULT 3,
        owner_capabilities JSON,
        success_criteria JSON,
        evidence_requirements JSON,
        expansion_rules JSON,
        clarification_requirements JSON,
        node_metadata JSON,
        created_at TIMESTAMP NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS mission_blueprint_dependencies (
        dependency_record_id VARCHAR PRIMARY KEY,
        blueprint_id VARCHAR NOT NULL REFERENCES mission_blueprints(blueprint_id) ON DELETE CASCADE,
        revision_id VARCHAR NOT NULL REFERENCES mission_blueprint_revisions(revision_id) ON DELETE CASCADE,
        mission_id VARCHAR NOT NULL,
        dependency_id VARCHAR NOT NULL,
        from_node_id VARCHAR NOT NULL,
        to_node_id VARCHAR NOT NULL,
        kind VARCHAR NOT NULL,
        required BOOLEAN NOT NULL DEFAULT TRUE,
        dependency_metadata JSON,
        created_at TIMESTAMP NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS mission_blueprint_readiness_snapshots (
        snapshot_id VARCHAR PRIMARY KEY,
        blueprint_id VARCHAR NOT NULL REFERENCES mission_blueprints(blueprint_id) ON DELETE CASCADE,
        mission_id VARCHAR NOT NULL,
        revision INTEGER NOT NULL,
        snapshot JSON,
        created_at TIMESTAMP NOT NULL
    )
    """,
    """
    ALTER TABLE mission_intents ADD COLUMN IF NOT EXISTS blueprint_id VARCHAR
    """,
    """
    ALTER TABLE mission_intents ADD COLUMN IF NOT EXISTS blueprint_node_id VARCHAR
    """,
    """
    ALTER TABLE mission_intents ADD COLUMN IF NOT EXISTS blueprint_revision INTEGER
    """,
    """
    CREATE TABLE IF NOT EXISTS mission_blueprint_expansions (
        expansion_id VARCHAR PRIMARY KEY,
        blueprint_id VARCHAR NOT NULL REFERENCES mission_blueprints(blueprint_id) ON DELETE CASCADE,
        mission_id VARCHAR NOT NULL,
        blueprint_node_id VARCHAR NOT NULL,
        blueprint_revision INTEGER NOT NULL,
        status VARCHAR NOT NULL DEFAULT 'expanded',
        generated_intent_ids JSON,
        diagnostics JSON,
        created_at TIMESTAMP NOT NULL
    )
    """,
]

DOWNGRADE_SQL = [
    "DROP TABLE IF EXISTS mission_blueprint_expansions",
    "DROP TABLE IF EXISTS mission_blueprint_readiness_snapshots",
    "DROP TABLE IF EXISTS mission_blueprint_dependencies",
    "DROP TABLE IF EXISTS mission_blueprint_nodes",
    "DROP TABLE IF EXISTS mission_blueprint_revisions",
    "DROP TABLE IF EXISTS mission_blueprints",
]
