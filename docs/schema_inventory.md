# Schema Inventory

- Schema version: `schema_validation.v1`
- Alembic current: `20260802_0003`
- Alembic head: `20260802_0003`
- Compatible: `True`

| Object | Status | Severity | ORM | Database | Detail |
| --- | --- | --- | --- | --- | --- |
| benchmark_execution_traces | MATCH | INFO |  |  | Table exists |
| benchmark_execution_traces.benchmark_id | MATCH | INFO | varchar | varchar | Column type matches |
| benchmark_execution_traces.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| benchmark_execution_traces.mission_id | MATCH | INFO | varchar | varchar | Column type matches |
| benchmark_execution_traces.run_id | MATCH | INFO | varchar | varchar | Column type matches |
| benchmark_execution_traces.snapshot | MATCH | INFO | json | json | Column type matches |
| benchmark_execution_traces.timeline | MATCH | INFO | json | json | Column type matches |
| benchmark_execution_traces.trace_id | MATCH | INFO | varchar | varchar | Column type matches |
| benchmark_execution_traces.ix_benchmark_execution_traces_benchmark_id | MATCH | INFO |  |  | Index presence comparison |
| benchmark_execution_traces.ix_benchmark_execution_traces_created_at | MATCH | INFO |  |  | Index presence comparison |
| benchmark_execution_traces.ix_benchmark_execution_traces_mission_id | MATCH | INFO |  |  | Index presence comparison |
| benchmark_execution_traces.ix_benchmark_execution_traces_run_id | MATCH | INFO |  |  | Index presence comparison |
| benchmark_failures | MATCH | INFO |  |  | Table exists |
| benchmark_failures.affected_subsystem | MATCH | INFO | varchar | varchar | Column type matches |
| benchmark_failures.benchmark_id | MATCH | INFO | varchar | varchar | Column type matches |
| benchmark_failures.category | MATCH | INFO | varchar | varchar | Column type matches |
| benchmark_failures.confidence | MATCH | INFO | float | double precision | Column type matches |
| benchmark_failures.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| benchmark_failures.failure_id | MATCH | INFO | varchar | varchar | Column type matches |
| benchmark_failures.recommended_fix | MATCH | INFO | text | text | Column type matches |
| benchmark_failures.root_cause | MATCH | INFO | text | text | Column type matches |
| benchmark_failures.run_id | MATCH | INFO | varchar | varchar | Column type matches |
| benchmark_failures.timeline | MATCH | INFO | json | json | Column type matches |
| benchmark_failures.ix_benchmark_failures_affected_subsystem | MATCH | INFO |  |  | Index presence comparison |
| benchmark_failures.ix_benchmark_failures_benchmark_id | MATCH | INFO |  |  | Index presence comparison |
| benchmark_failures.ix_benchmark_failures_category | MATCH | INFO |  |  | Index presence comparison |
| benchmark_failures.ix_benchmark_failures_created_at | MATCH | INFO |  |  | Index presence comparison |
| benchmark_failures.ix_benchmark_failures_run_id | MATCH | INFO |  |  | Index presence comparison |
| benchmark_metrics | MATCH | INFO |  |  | Table exists |
| benchmark_metrics.benchmark_id | MATCH | INFO | varchar | varchar | Column type matches |
| benchmark_metrics.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| benchmark_metrics.metric_id | MATCH | INFO | varchar | varchar | Column type matches |
| benchmark_metrics.metrics | MATCH | INFO | json | json | Column type matches |
| benchmark_metrics.run_id | MATCH | INFO | varchar | varchar | Column type matches |
| benchmark_metrics.ix_benchmark_metrics_benchmark_id | MATCH | INFO |  |  | Index presence comparison |
| benchmark_metrics.ix_benchmark_metrics_created_at | MATCH | INFO |  |  | Index presence comparison |
| benchmark_metrics.ix_benchmark_metrics_run_id | MATCH | INFO |  |  | Index presence comparison |
| benchmark_reports | MATCH | INFO |  |  | Table exists |
| benchmark_reports.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| benchmark_reports.json_report | MATCH | INFO | json | json | Column type matches |
| benchmark_reports.markdown_report | MATCH | INFO | text | text | Column type matches |
| benchmark_reports.report_id | MATCH | INFO | varchar | varchar | Column type matches |
| benchmark_reports.report_type | MATCH | INFO | varchar | varchar | Column type matches |
| benchmark_reports.run_id | MATCH | INFO | varchar | varchar | Column type matches |
| benchmark_reports.ix_benchmark_reports_created_at | MATCH | INFO |  |  | Index presence comparison |
| benchmark_reports.ix_benchmark_reports_report_type | MATCH | INFO |  |  | Index presence comparison |
| benchmark_reports.ix_benchmark_reports_run_id | MATCH | INFO |  |  | Index presence comparison |
| benchmark_runs | MATCH | INFO |  |  | Table exists |
| benchmark_runs.benchmark_id | MATCH | INFO | varchar | varchar | Column type matches |
| benchmark_runs.category | MATCH | INFO | varchar | varchar | Column type matches |
| benchmark_runs.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| benchmark_runs.duration_ms | MATCH | INFO | integer | integer | Column type matches |
| benchmark_runs.mission_id | MATCH | INFO | varchar | varchar | Column type matches |
| benchmark_runs.run_id | MATCH | INFO | varchar | varchar | Column type matches |
| benchmark_runs.run_metadata | MATCH | INFO | json | json | Column type matches |
| benchmark_runs.score | MATCH | INFO | float | double precision | Column type matches |
| benchmark_runs.status | MATCH | INFO | varchar | varchar | Column type matches |
| benchmark_runs.ix_benchmark_runs_benchmark_id | MATCH | INFO |  |  | Index presence comparison |
| benchmark_runs.ix_benchmark_runs_category | MATCH | INFO |  |  | Index presence comparison |
| benchmark_runs.ix_benchmark_runs_created_at | MATCH | INFO |  |  | Index presence comparison |
| benchmark_runs.ix_benchmark_runs_mission_id | MATCH | INFO |  |  | Index presence comparison |
| cognitive_checkpoints | MATCH | INFO |  |  | Table exists |
| cognitive_checkpoints.blueprint_revision | MATCH | INFO | integer | integer | Column type matches |
| cognitive_checkpoints.checkpoint_id | MATCH | INFO | varchar | varchar | Column type matches |
| cognitive_checkpoints.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| cognitive_checkpoints.mission_id | MATCH | INFO | varchar | varchar | Column type matches |
| cognitive_checkpoints.serialized_state | MATCH | INFO | json | json | Column type matches |
| cognitive_checkpoints.ix_cognitive_checkpoints_created_at | MATCH | INFO |  |  | Index presence comparison |
| cognitive_checkpoints.ix_cognitive_checkpoints_mission_id | MATCH | INFO |  |  | Index presence comparison |
| cognitive_decision_comparisons | MATCH | INFO |  |  | Table exists |
| cognitive_decision_comparisons.agreement | MATCH | INFO | varchar | varchar | Column type matches |
| cognitive_decision_comparisons.blueprint_node_id | MATCH | INFO | varchar | varchar | Column type matches |
| cognitive_decision_comparisons.cognitive_decision | MATCH | INFO | varchar | varchar | Column type matches |
| cognitive_decision_comparisons.cognitive_reason | MATCH | INFO | text | text | Column type matches |
| cognitive_decision_comparisons.comparison_id | MATCH | INFO | varchar | varchar | Column type matches |
| cognitive_decision_comparisons.comparison_metadata | MATCH | INFO | json | json | Column type matches |
| cognitive_decision_comparisons.confidence | MATCH | INFO | float | double precision | Column type matches |
| cognitive_decision_comparisons.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| cognitive_decision_comparisons.explanation | MATCH | INFO | json | json | Column type matches |
| cognitive_decision_comparisons.intent_id | MATCH | INFO | varchar | varchar | Column type matches |
| cognitive_decision_comparisons.mission_id | MATCH | INFO | varchar | varchar | Column type matches |
| cognitive_decision_comparisons.runtime_decision | MATCH | INFO | varchar | varchar | Column type matches |
| cognitive_decision_comparisons.runtime_reason | MATCH | INFO | text | text | Column type matches |
| cognitive_decision_comparisons.ix_cognitive_decision_comparisons_agreement | MATCH | INFO |  |  | Index presence comparison |
| cognitive_decision_comparisons.ix_cognitive_decision_comparisons_blueprint_node_id | MATCH | INFO |  |  | Index presence comparison |
| cognitive_decision_comparisons.ix_cognitive_decision_comparisons_cognitive_decision | MATCH | INFO |  |  | Index presence comparison |
| cognitive_decision_comparisons.ix_cognitive_decision_comparisons_created_at | MATCH | INFO |  |  | Index presence comparison |
| cognitive_decision_comparisons.ix_cognitive_decision_comparisons_intent_id | MATCH | INFO |  |  | Index presence comparison |
| cognitive_decision_comparisons.ix_cognitive_decision_comparisons_mission_id | MATCH | INFO |  |  | Index presence comparison |
| cognitive_decision_comparisons.ix_cognitive_decision_comparisons_runtime_decision | MATCH | INFO |  |  | Index presence comparison |
| cognitive_evidence | MATCH | INFO |  |  | Table exists |
| cognitive_evidence.confidence | MATCH | INFO | float | double precision | Column type matches |
| cognitive_evidence.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| cognitive_evidence.evidence_id | MATCH | INFO | varchar | varchar | Column type matches |
| cognitive_evidence.evidence_type | MATCH | INFO | varchar | varchar | Column type matches |
| cognitive_evidence.mission_id | MATCH | INFO | varchar | varchar | Column type matches |
| cognitive_evidence.payload | MATCH | INFO | json | json | Column type matches |
| cognitive_evidence.provenance | MATCH | INFO | json | json | Column type matches |
| cognitive_evidence.provider | MATCH | INFO | varchar | varchar | Column type matches |
| cognitive_evidence.source | MATCH | INFO | varchar | varchar | Column type matches |
| cognitive_evidence.ix_cognitive_evidence_created_at | MATCH | INFO |  |  | Index presence comparison |
| cognitive_evidence.ix_cognitive_evidence_evidence_type | MATCH | INFO |  |  | Index presence comparison |
| cognitive_evidence.ix_cognitive_evidence_mission_id | MATCH | INFO |  |  | Index presence comparison |
| cognitive_metrics | MATCH | INFO |  |  | Table exists |
| cognitive_metrics.clarification_count | MATCH | INFO | integer | integer | Column type matches |
| cognitive_metrics.confidence_average | MATCH | INFO | float | double precision | Column type matches |
| cognitive_metrics.evidence_count | MATCH | INFO | integer | integer | Column type matches |
| cognitive_metrics.execution_duration_ms | MATCH | INFO | integer | integer | Column type matches |
| cognitive_metrics.metrics_metadata | MATCH | INFO | json | json | Column type matches |
| cognitive_metrics.mission_id | MATCH | INFO | varchar | varchar | Column type matches |
| cognitive_metrics.reasoning_iterations | MATCH | INFO | integer | integer | Column type matches |
| cognitive_metrics.recovery_count | MATCH | INFO | integer | integer | Column type matches |
| cognitive_metrics.replanning_count | MATCH | INFO | integer | integer | Column type matches |
| cognitive_metrics.snapshot | MATCH | INFO | json | json | Column type matches |
| cognitive_metrics.updated_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| cognitive_missions | MATCH | INFO |  |  | Table exists |
| cognitive_missions.blueprint_id | MATCH | INFO | varchar | varchar | Column type matches |
| cognitive_missions.blueprint_revision | MATCH | INFO | integer | integer | Column type matches |
| cognitive_missions.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| cognitive_missions.mission_id | MATCH | INFO | varchar | varchar | Column type matches |
| cognitive_missions.runtime_metadata | MATCH | INFO | json | json | Column type matches |
| cognitive_missions.runtime_version | MATCH | INFO | varchar | varchar | Column type matches |
| cognitive_missions.schema_version | MATCH | INFO | varchar | varchar | Column type matches |
| cognitive_missions.snapshot | MATCH | INFO | json | json | Column type matches |
| cognitive_missions.state | MATCH | INFO | varchar | varchar | Column type matches |
| cognitive_missions.updated_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| cognitive_missions.ix_cognitive_missions_blueprint_id | MATCH | INFO |  |  | Index presence comparison |
| cognitive_sessions | MATCH | INFO |  |  | Table exists |
| cognitive_sessions.active_intent | MATCH | INFO | varchar | varchar | Column type matches |
| cognitive_sessions.conversation_id | MATCH | INFO | varchar | varchar | Column type matches |
| cognitive_sessions.conversation_summary | MATCH | INFO | text | text | Column type matches |
| cognitive_sessions.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| cognitive_sessions.entities_json | MATCH | INFO | text | text | Column type matches |
| cognitive_sessions.entity_order_json | MATCH | INFO | text | text | Column type matches |
| cognitive_sessions.goal_json | MATCH | INFO | text | text | Column type matches |
| cognitive_sessions.turn_count | MATCH | INFO | integer | integer | Column type matches |
| cognitive_sessions.updated_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| failure_records | MATCH | INFO |  |  | Table exists |
| failure_records.error_code | MATCH | INFO | varchar | varchar | Column type matches |
| failure_records.id | MATCH | INFO | varchar | varchar | Column type matches |
| failure_records.node_id | MATCH | INFO | varchar | varchar | Column type matches |
| failure_records.recovery_attempted | MATCH | INFO | varchar | varchar | Column type matches |
| failure_records.recovery_success | MATCH | INFO | boolean | boolean | Column type matches |
| failure_records.selector_used | MATCH | INFO | text | text | Column type matches |
| failure_records.session_id | MATCH | INFO | varchar | varchar | Column type matches |
| failure_records.timestamp | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| heuristic_records | MATCH | INFO |  |  | Table exists |
| heuristic_records.attempt_count | MATCH | INFO | integer | integer | Column type matches |
| heuristic_records.failure_code | MATCH | INFO | varchar | varchar | Column type matches |
| heuristic_records.id | MATCH | INFO | varchar | varchar | Column type matches |
| heuristic_records.remedy_code | MATCH | INFO | varchar | varchar | Column type matches |
| heuristic_records.site_domain | MATCH | INFO | varchar | varchar | Column type matches |
| heuristic_records.success_count | MATCH | INFO | integer | integer | Column type matches |
| mission_blueprint_dependencies | MATCH | INFO |  |  | Table exists |
| mission_blueprint_dependencies.blueprint_id | MATCH | INFO | varchar | varchar | Column type matches |
| mission_blueprint_dependencies.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| mission_blueprint_dependencies.dependency_id | MATCH | INFO | varchar | varchar | Column type matches |
| mission_blueprint_dependencies.dependency_metadata | MATCH | INFO | json | json | Column type matches |
| mission_blueprint_dependencies.dependency_record_id | MATCH | INFO | varchar | varchar | Column type matches |
| mission_blueprint_dependencies.from_node_id | MATCH | INFO | varchar | varchar | Column type matches |
| mission_blueprint_dependencies.kind | MATCH | INFO | varchar | varchar | Column type matches |
| mission_blueprint_dependencies.mission_id | MATCH | INFO | varchar | varchar | Column type matches |
| mission_blueprint_dependencies.required | MATCH | INFO | boolean | boolean | Column type matches |
| mission_blueprint_dependencies.revision_id | MATCH | INFO | varchar | varchar | Column type matches |
| mission_blueprint_dependencies.to_node_id | MATCH | INFO | varchar | varchar | Column type matches |
| mission_blueprint_dependencies.ix_mission_blueprint_dependencies_blueprint_id | MATCH | INFO |  |  | Index presence comparison |
| mission_blueprint_dependencies.ix_mission_blueprint_dependencies_dependency_id | MATCH | INFO |  |  | Index presence comparison |
| mission_blueprint_dependencies.ix_mission_blueprint_dependencies_mission_id | MATCH | INFO |  |  | Index presence comparison |
| mission_blueprint_dependencies.ix_mission_blueprint_dependencies_revision_id | MATCH | INFO |  |  | Index presence comparison |
| mission_blueprint_expansions | MATCH | INFO |  |  | Table exists |
| mission_blueprint_expansions.blueprint_id | MATCH | INFO | varchar | varchar | Column type matches |
| mission_blueprint_expansions.blueprint_node_id | MATCH | INFO | varchar | varchar | Column type matches |
| mission_blueprint_expansions.blueprint_revision | MATCH | INFO | integer | integer | Column type matches |
| mission_blueprint_expansions.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| mission_blueprint_expansions.diagnostics | MATCH | INFO | json | json | Column type matches |
| mission_blueprint_expansions.expansion_id | MATCH | INFO | varchar | varchar | Column type matches |
| mission_blueprint_expansions.generated_intent_ids | MATCH | INFO | json | json | Column type matches |
| mission_blueprint_expansions.mission_id | MATCH | INFO | varchar | varchar | Column type matches |
| mission_blueprint_expansions.status | MATCH | INFO | varchar | varchar | Column type matches |
| mission_blueprint_expansions.ix_mission_blueprint_expansions_blueprint_id | MATCH | INFO |  |  | Index presence comparison |
| mission_blueprint_expansions.ix_mission_blueprint_expansions_blueprint_node_id | MATCH | INFO |  |  | Index presence comparison |
| mission_blueprint_expansions.ix_mission_blueprint_expansions_created_at | MATCH | INFO |  |  | Index presence comparison |
| mission_blueprint_expansions.ix_mission_blueprint_expansions_mission_id | MATCH | INFO |  |  | Index presence comparison |
| mission_blueprint_nodes | MATCH | INFO |  |  | Table exists |
| mission_blueprint_nodes.blueprint_id | MATCH | INFO | varchar | varchar | Column type matches |
| mission_blueprint_nodes.clarification_requirements | MATCH | INFO | json | json | Column type matches |
| mission_blueprint_nodes.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| mission_blueprint_nodes.evidence_requirements | MATCH | INFO | json | json | Column type matches |
| mission_blueprint_nodes.expansion_rules | MATCH | INFO | json | json | Column type matches |
| mission_blueprint_nodes.kind | MATCH | INFO | varchar | varchar | Column type matches |
| mission_blueprint_nodes.mission_id | MATCH | INFO | varchar | varchar | Column type matches |
| mission_blueprint_nodes.node_id | MATCH | INFO | varchar | varchar | Column type matches |
| mission_blueprint_nodes.node_metadata | MATCH | INFO | json | json | Column type matches |
| mission_blueprint_nodes.node_record_id | MATCH | INFO | varchar | varchar | Column type matches |
| mission_blueprint_nodes.objective | MATCH | INFO | text | text | Column type matches |
| mission_blueprint_nodes.owner_capabilities | MATCH | INFO | json | json | Column type matches |
| mission_blueprint_nodes.priority | MATCH | INFO | integer | integer | Column type matches |
| mission_blueprint_nodes.revision_id | MATCH | INFO | varchar | varchar | Column type matches |
| mission_blueprint_nodes.state | MATCH | INFO | varchar | varchar | Column type matches |
| mission_blueprint_nodes.success_criteria | MATCH | INFO | json | json | Column type matches |
| mission_blueprint_nodes.ix_mission_blueprint_nodes_blueprint_id | MATCH | INFO |  |  | Index presence comparison |
| mission_blueprint_nodes.ix_mission_blueprint_nodes_mission_id | MATCH | INFO |  |  | Index presence comparison |
| mission_blueprint_nodes.ix_mission_blueprint_nodes_node_id | MATCH | INFO |  |  | Index presence comparison |
| mission_blueprint_nodes.ix_mission_blueprint_nodes_revision_id | MATCH | INFO |  |  | Index presence comparison |
| mission_blueprint_readiness_snapshots | MATCH | INFO |  |  | Table exists |
| mission_blueprint_readiness_snapshots.blueprint_id | MATCH | INFO | varchar | varchar | Column type matches |
| mission_blueprint_readiness_snapshots.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| mission_blueprint_readiness_snapshots.mission_id | MATCH | INFO | varchar | varchar | Column type matches |
| mission_blueprint_readiness_snapshots.revision | MATCH | INFO | integer | integer | Column type matches |
| mission_blueprint_readiness_snapshots.snapshot | MATCH | INFO | json | json | Column type matches |
| mission_blueprint_readiness_snapshots.snapshot_id | MATCH | INFO | varchar | varchar | Column type matches |
| mission_blueprint_readiness_snapshots.ix_mission_blueprint_readiness_snapshots_blueprint_id | MATCH | INFO |  |  | Index presence comparison |
| mission_blueprint_readiness_snapshots.ix_mission_blueprint_readiness_snapshots_created_at | MATCH | INFO |  |  | Index presence comparison |
| mission_blueprint_readiness_snapshots.ix_mission_blueprint_readiness_snapshots_mission_id | MATCH | INFO |  |  | Index presence comparison |
| mission_blueprint_revisions | MATCH | INFO |  |  | Table exists |
| mission_blueprint_revisions.blueprint_id | MATCH | INFO | varchar | varchar | Column type matches |
| mission_blueprint_revisions.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| mission_blueprint_revisions.created_by | MATCH | INFO | varchar | varchar | Column type matches |
| mission_blueprint_revisions.mission_id | MATCH | INFO | varchar | varchar | Column type matches |
| mission_blueprint_revisions.reason | MATCH | INFO | text | text | Column type matches |
| mission_blueprint_revisions.revision | MATCH | INFO | integer | integer | Column type matches |
| mission_blueprint_revisions.revision_id | MATCH | INFO | varchar | varchar | Column type matches |
| mission_blueprint_revisions.snapshot | MATCH | INFO | json | json | Column type matches |
| mission_blueprint_revisions.ix_mission_blueprint_revisions_blueprint_id | MATCH | INFO |  |  | Index presence comparison |
| mission_blueprint_revisions.ix_mission_blueprint_revisions_mission_id | MATCH | INFO |  |  | Index presence comparison |
| mission_blueprints | MATCH | INFO |  |  | Table exists |
| mission_blueprints.approval_policy | MATCH | INFO | json | json | Column type matches |
| mission_blueprints.blueprint_id | MATCH | INFO | varchar | varchar | Column type matches |
| mission_blueprints.blueprint_metadata | MATCH | INFO | json | json | Column type matches |
| mission_blueprints.constraints | MATCH | INFO | json | json | Column type matches |
| mission_blueprints.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| mission_blueprints.mission_id | MATCH | INFO | varchar | varchar | Column type matches |
| mission_blueprints.objective | MATCH | INFO | text | text | Column type matches |
| mission_blueprints.recovery_rules | MATCH | INFO | json | json | Column type matches |
| mission_blueprints.revision | MATCH | INFO | integer | integer | Column type matches |
| mission_blueprints.schema_version | MATCH | INFO | varchar | varchar | Column type matches |
| mission_blueprints.snapshot | MATCH | INFO | json | json | Column type matches |
| mission_blueprints.status | MATCH | INFO | varchar | varchar | Column type matches |
| mission_blueprints.success_criteria | MATCH | INFO | json | json | Column type matches |
| mission_blueprints.termination_rules | MATCH | INFO | json | json | Column type matches |
| mission_blueprints.updated_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| mission_blueprints.ix_mission_blueprints_mission_id | MATCH | INFO |  |  | Index presence comparison |
| mission_intents | MATCH | INFO |  |  | Table exists |
| mission_intents.blueprint_id | MATCH | INFO | varchar | varchar | Column type matches |
| mission_intents.blueprint_node_id | MATCH | INFO | varchar | varchar | Column type matches |
| mission_intents.blueprint_revision | MATCH | INFO | integer | integer | Column type matches |
| mission_intents.capability | MATCH | INFO | varchar | varchar | Column type matches |
| mission_intents.completed_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| mission_intents.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| mission_intents.dispatch_target | MATCH | INFO | varchar | varchar | Column type matches |
| mission_intents.dispatched_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| mission_intents.evidence | MATCH | INFO | json | json | Column type matches |
| mission_intents.execution_owner | MATCH | INFO | varchar | varchar | Column type matches |
| mission_intents.intent | MATCH | INFO | varchar | varchar | Column type matches |
| mission_intents.intent_id | MATCH | INFO | varchar | varchar | Column type matches |
| mission_intents.mission_id | MATCH | INFO | varchar | varchar | Column type matches |
| mission_intents.parent_intent_id | MATCH | INFO | varchar | varchar | Column type matches |
| mission_intents.payload | MATCH | INFO | json | json | Column type matches |
| mission_intents.provenance | MATCH | INFO | json | json | Column type matches |
| mission_intents.provider | MATCH | INFO | varchar | varchar | Column type matches |
| mission_intents.resume_metadata | MATCH | INFO | json | json | Column type matches |
| mission_intents.retries | MATCH | INFO | integer | integer | Column type matches |
| mission_intents.status | MATCH | INFO | varchar | varchar | Column type matches |
| mission_intents.updated_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| mission_intents.ix_mission_intents_blueprint_id | MATCH | INFO |  |  | Index presence comparison |
| mission_intents.ix_mission_intents_blueprint_node_id | MATCH | INFO |  |  | Index presence comparison |
| mission_intents.ix_mission_intents_mission_id | MATCH | INFO |  |  | Index presence comparison |
| mission_result_artifacts | MATCH | INFO |  |  | Table exists |
| mission_result_artifacts.artifact_id | MATCH | INFO | varchar | varchar | Column type matches |
| mission_result_artifacts.artifact_metadata | MATCH | INFO | json | json | Column type matches |
| mission_result_artifacts.content | MATCH | INFO | text | text | Column type matches |
| mission_result_artifacts.content_type | MATCH | INFO | varchar | varchar | Column type matches |
| mission_result_artifacts.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| mission_result_artifacts.kind | MATCH | INFO | varchar | varchar | Column type matches |
| mission_result_artifacts.mission_id | MATCH | INFO | varchar | varchar | Column type matches |
| mission_result_artifacts.mission_result_id | MATCH | INFO | varchar | varchar | Column type matches |
| mission_result_artifacts.structured | MATCH | INFO | json | json | Column type matches |
| mission_result_artifacts.title | MATCH | INFO | text | text | Column type matches |
| mission_result_artifacts.ix_mission_result_artifacts_kind | MATCH | INFO |  |  | Index presence comparison |
| mission_result_artifacts.ix_mission_result_artifacts_mission_id | MATCH | INFO |  |  | Index presence comparison |
| mission_result_artifacts.ix_mission_result_artifacts_mission_result_id | MATCH | INFO |  |  | Index presence comparison |
| mission_result_versions | MATCH | INFO |  |  | Table exists |
| mission_result_versions.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| mission_result_versions.mission_id | MATCH | INFO | varchar | varchar | Column type matches |
| mission_result_versions.mission_result_id | MATCH | INFO | varchar | varchar | Column type matches |
| mission_result_versions.reason | MATCH | INFO | text | text | Column type matches |
| mission_result_versions.snapshot | MATCH | INFO | json | json | Column type matches |
| mission_result_versions.version | MATCH | INFO | integer | integer | Column type matches |
| mission_result_versions.version_id | MATCH | INFO | varchar | varchar | Column type matches |
| mission_result_versions.ix_mission_result_versions_mission_id | MATCH | INFO |  |  | Index presence comparison |
| mission_result_versions.ix_mission_result_versions_mission_result_id | MATCH | INFO |  |  | Index presence comparison |
| mission_results | MATCH | INFO |  |  | Table exists |
| mission_results.completion_reason | MATCH | INFO | text | text | Column type matches |
| mission_results.confidence | MATCH | INFO | float | double precision | Column type matches |
| mission_results.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| mission_results.final_answer | MATCH | INFO | text | text | Column type matches |
| mission_results.knowledge_artifact_id | MATCH | INFO | varchar | varchar | Column type matches |
| mission_results.mission_id | MATCH | INFO | varchar | varchar | Column type matches |
| mission_results.mission_result_id | MATCH | INFO | varchar | varchar | Column type matches |
| mission_results.outcome | MATCH | INFO | varchar | varchar | Column type matches |
| mission_results.report_artifact_id | MATCH | INFO | varchar | varchar | Column type matches |
| mission_results.report_format | MATCH | INFO | varchar | varchar | Column type matches |
| mission_results.result_metadata | MATCH | INFO | json | json | Column type matches |
| mission_results.updated_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| mission_results.ix_mission_results_knowledge_artifact_id | MATCH | INFO |  |  | Index presence comparison |
| mission_results.ix_mission_results_mission_id | MATCH | INFO |  |  | Index presence comparison |
| mission_results.ix_mission_results_outcome | MATCH | INFO |  |  | Index presence comparison |
| mission_results.ix_mission_results_report_artifact_id | MATCH | INFO |  |  | Index presence comparison |
| mission_tasks | MATCH | INFO |  |  | Table exists |
| mission_tasks.attached_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| mission_tasks.id | MATCH | INFO | integer | integer | Column type matches |
| mission_tasks.mission_id | MATCH | INFO | varchar | varchar | Column type matches |
| mission_tasks.position | MATCH | INFO | integer | integer | Column type matches |
| mission_tasks.task_id | MATCH | INFO | varchar | varchar | Column type matches |
| mission_tasks.ix_mission_tasks_mission_id | MATCH | INFO |  |  | Index presence comparison |
| mission_tasks.ix_mission_tasks_task_id | MATCH | INFO |  |  | Index presence comparison |
| missions | MATCH | INFO |  |  | Table exists |
| missions.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| missions.metadata_json | MATCH | INFO | text | text | Column type matches |
| missions.mission_id | MATCH | INFO | varchar | varchar | Column type matches |
| missions.objective | MATCH | INFO | text | text | Column type matches |
| missions.priority | MATCH | INFO | integer | integer | Column type matches |
| missions.state | MATCH | INFO | varchar | varchar | Column type matches |
| missions.title | MATCH | INFO | text | text | Column type matches |
| missions.updated_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| run_ledger_events | MATCH | INFO |  |  | Table exists |
| run_ledger_events.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| run_ledger_events.event_id | MATCH | INFO | varchar | varchar | Column type matches |
| run_ledger_events.event_type | MATCH | INFO | varchar | varchar | Column type matches |
| run_ledger_events.links | MATCH | INFO | json | json | Column type matches |
| run_ledger_events.payload | MATCH | INFO | json | json | Column type matches |
| run_ledger_events.producer | MATCH | INFO | varchar | varchar | Column type matches |
| run_ledger_events.run_id | MATCH | INFO | varchar | varchar | Column type matches |
| run_ledger_events.schema_version | MATCH | INFO | varchar | varchar | Column type matches |
| run_ledger_events.step_index | MATCH | INFO | integer | integer | Column type matches |
| run_ledger_events.ix_run_ledger_events_created_at | MATCH | INFO |  |  | Index presence comparison |
| run_ledger_events.ix_run_ledger_events_event_type | MATCH | INFO |  |  | Index presence comparison |
| run_ledger_events.ix_run_ledger_events_run_id | MATCH | INFO |  |  | Index presence comparison |
| sessions | MATCH | INFO |  |  | Table exists |
| sessions.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| sessions.id | MATCH | INFO | varchar | varchar | Column type matches |
| sessions.status | MATCH | INFO | varchar | varchar | Column type matches |
| sessions.tab_title | MATCH | INFO | text | text | Column type matches |
| sessions.tab_url | MATCH | INFO | text | text | Column type matches |
| task_nodes | MATCH | INFO |  |  | Table exists |
| task_nodes.description | MATCH | INFO | text | text | Column type matches |
| task_nodes.id | MATCH | INFO | varchar | varchar | Column type matches |
| task_nodes.node_id | MATCH | INFO | varchar | varchar | Column type matches |
| task_nodes.prerequisites | MATCH | INFO | json | json | Column type matches |
| task_nodes.session_id | MATCH | INFO | varchar | varchar | Column type matches |
| task_nodes.status | MATCH | INFO | varchar | varchar | Column type matches |
| task_nodes.updated_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| task_nodes.validators | MATCH | INFO | json | json | Column type matches |
| unified_task_approvals | MATCH | INFO |  |  | Table exists |
| unified_task_approvals.action | MATCH | INFO | text | text | Column type matches |
| unified_task_approvals.approval_id | MATCH | INFO | varchar | varchar | Column type matches |
| unified_task_approvals.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| unified_task_approvals.resolution_note | MATCH | INFO | text | text | Column type matches |
| unified_task_approvals.resolved_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| unified_task_approvals.risk_level | MATCH | INFO | varchar | varchar | Column type matches |
| unified_task_approvals.status | MATCH | INFO | varchar | varchar | Column type matches |
| unified_task_approvals.task_id | MATCH | INFO | varchar | varchar | Column type matches |
| unified_task_approvals.ix_unified_task_approvals_task_id | MATCH | INFO |  |  | Index presence comparison |
| unified_task_snapshots | MATCH | INFO |  |  | Table exists |
| unified_task_snapshots.context_json | MATCH | INFO | text | text | Column type matches |
| unified_task_snapshots.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| unified_task_snapshots.snapshot_id | MATCH | INFO | varchar | varchar | Column type matches |
| unified_task_snapshots.task_id | MATCH | INFO | varchar | varchar | Column type matches |
| unified_task_snapshots.task_state | MATCH | INFO | varchar | varchar | Column type matches |
| unified_task_snapshots.trigger | MATCH | INFO | varchar | varchar | Column type matches |
| unified_task_snapshots.ix_unified_task_snapshots_task_id | MATCH | INFO |  |  | Index presence comparison |
| unified_task_timeline | MATCH | INFO |  |  | Table exists |
| unified_task_timeline.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| unified_task_timeline.event_id | MATCH | INFO | varchar | varchar | Column type matches |
| unified_task_timeline.event_type | MATCH | INFO | varchar | varchar | Column type matches |
| unified_task_timeline.payload_json | MATCH | INFO | text | text | Column type matches |
| unified_task_timeline.task_id | MATCH | INFO | varchar | varchar | Column type matches |
| unified_task_timeline.timestamp | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| unified_task_timeline.ix_unified_task_timeline_task_id | MATCH | INFO |  |  | Index presence comparison |
| unified_tasks | MATCH | INFO |  |  | Table exists |
| unified_tasks.approval_state | MATCH | INFO | varchar | varchar | Column type matches |
| unified_tasks.cognitive_session_id | MATCH | INFO | varchar | varchar | Column type matches |
| unified_tasks.conversation_id | MATCH | INFO | varchar | varchar | Column type matches |
| unified_tasks.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| unified_tasks.current_goal | MATCH | INFO | text | text | Column type matches |
| unified_tasks.entities_json | MATCH | INFO | text | text | Column type matches |
| unified_tasks.execution_plan_json | MATCH | INFO | text | text | Column type matches |
| unified_tasks.intelligence_summary_json | MATCH | INFO | text | text | Column type matches |
| unified_tasks.original_query | MATCH | INFO | text | text | Column type matches |
| unified_tasks.research_report_json | MATCH | INFO | text | text | Column type matches |
| unified_tasks.research_session_id | MATCH | INFO | varchar | varchar | Column type matches |
| unified_tasks.restored_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| unified_tasks.snapshot_count | MATCH | INFO | integer | integer | Column type matches |
| unified_tasks.state | MATCH | INFO | varchar | varchar | Column type matches |
| unified_tasks.task_id | MATCH | INFO | varchar | varchar | Column type matches |
| unified_tasks.updated_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| unified_tasks.workflow_session_id | MATCH | INFO | varchar | varchar | Column type matches |
| unified_tasks.ix_unified_tasks_conversation_id | MATCH | INFO |  |  | Index presence comparison |
| v5_admin_diagnostics | MATCH | INFO |  |  | Table exists |
| v5_admin_diagnostics.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_admin_diagnostics.created_by | MATCH | INFO | varchar | varchar | Column type matches |
| v5_admin_diagnostics.diagnostic_type | MATCH | INFO | varchar | varchar | Column type matches |
| v5_admin_diagnostics.id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_admin_diagnostics.metadata_json | MATCH | INFO | json | json | Column type matches |
| v5_admin_diagnostics.org_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_admin_diagnostics.status | MATCH | INFO | varchar | varchar | Column type matches |
| v5_admin_diagnostics.summary | MATCH | INFO | text | text | Column type matches |
| v5_admin_diagnostics.ix_v5_admin_diagnostics_created_at | MATCH | INFO |  |  | Index presence comparison |
| v5_admin_diagnostics.ix_v5_admin_diagnostics_diagnostic_type | MATCH | INFO |  |  | Index presence comparison |
| v5_admin_diagnostics.ix_v5_admin_diagnostics_org_id | MATCH | INFO |  |  | Index presence comparison |
| v5_advanced_audit_records | MATCH | INFO |  |  | Table exists |
| v5_advanced_audit_records.actor_user_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_advanced_audit_records.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_advanced_audit_records.event_type | MATCH | INFO | varchar | varchar | Column type matches |
| v5_advanced_audit_records.id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_advanced_audit_records.immutable_hash | MATCH | INFO | text | text | Column type matches |
| v5_advanced_audit_records.metadata_json | MATCH | INFO | json | json | Column type matches |
| v5_advanced_audit_records.org_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_advanced_audit_records.resource_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_advanced_audit_records.resource_type | MATCH | INFO | varchar | varchar | Column type matches |
| v5_advanced_audit_records.retention_until | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_advanced_audit_records.risk_classification | MATCH | INFO | varchar | varchar | Column type matches |
| v5_advanced_audit_records.source_audit_event_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_advanced_audit_records.workspace_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_advanced_audit_records.ix_v5_advanced_audit_records_actor_user_id | MATCH | INFO |  |  | Index presence comparison |
| v5_advanced_audit_records.ix_v5_advanced_audit_records_created_at | MATCH | INFO |  |  | Index presence comparison |
| v5_advanced_audit_records.ix_v5_advanced_audit_records_event_type | MATCH | INFO |  |  | Index presence comparison |
| v5_advanced_audit_records.ix_v5_advanced_audit_records_org_id | MATCH | INFO |  |  | Index presence comparison |
| v5_advanced_audit_records.ix_v5_advanced_audit_records_resource_id | MATCH | INFO |  |  | Index presence comparison |
| v5_advanced_audit_records.ix_v5_advanced_audit_records_resource_type | MATCH | INFO |  |  | Index presence comparison |
| v5_advanced_audit_records.ix_v5_advanced_audit_records_risk_classification | MATCH | INFO |  |  | Index presence comparison |
| v5_advanced_audit_records.ix_v5_advanced_audit_records_source_audit_event_id | MATCH | INFO |  |  | Index presence comparison |
| v5_advanced_audit_records.ix_v5_advanced_audit_records_workspace_id | MATCH | INFO |  |  | Index presence comparison |
| v5_api_keys | MATCH | INFO |  |  | Table exists |
| v5_api_keys.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_api_keys.created_by | MATCH | INFO | varchar | varchar | Column type matches |
| v5_api_keys.id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_api_keys.key_hash | MATCH | INFO | text | text | Column type matches |
| v5_api_keys.key_preview | MATCH | INFO | varchar | varchar | Column type matches |
| v5_api_keys.last_used_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_api_keys.name | MATCH | INFO | varchar | varchar | Column type matches |
| v5_api_keys.org_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_api_keys.revoked_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_api_keys.rotated_from_key_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_api_keys.scopes | MATCH | INFO | json | json | Column type matches |
| v5_api_keys.status | MATCH | INFO | varchar | varchar | Column type matches |
| v5_api_keys.usage_count | MATCH | INFO | integer | integer | Column type matches |
| v5_api_keys.workspace_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_api_keys.ix_v5_api_keys_created_by | MATCH | INFO |  |  | Index presence comparison |
| v5_api_keys.ix_v5_api_keys_org_id | MATCH | INFO |  |  | Index presence comparison |
| v5_api_keys.ix_v5_api_keys_status | MATCH | INFO |  |  | Index presence comparison |
| v5_api_keys.ix_v5_api_keys_workspace_id | MATCH | INFO |  |  | Index presence comparison |
| v5_api_keys.v5_api_keys_key_hash_key | EXTRA | INFO |  |  | Database index is not declared as explicit ORM Index |
| v5_assistant_versions | MATCH | INFO |  |  | Table exists |
| v5_assistant_versions.assistant_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_assistant_versions.capability_permissions | MATCH | INFO | json | json | Column type matches |
| v5_assistant_versions.change_summary | MATCH | INFO | text | text | Column type matches |
| v5_assistant_versions.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_assistant_versions.created_by | MATCH | INFO | varchar | varchar | Column type matches |
| v5_assistant_versions.description | MATCH | INFO | text | text | Column type matches |
| v5_assistant_versions.id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_assistant_versions.instructions | MATCH | INFO | text | text | Column type matches |
| v5_assistant_versions.name | MATCH | INFO | varchar | varchar | Column type matches |
| v5_assistant_versions.version_number | MATCH | INFO | integer | integer | Column type matches |
| v5_assistant_versions.ix_v5_assistant_versions_assistant_id | MATCH | INFO |  |  | Index presence comparison |
| v5_assistant_versions.uq_v5_assistant_version | EXTRA | INFO |  |  | Database index is not declared as explicit ORM Index |
| v5_assistant_workspace_assignments | MATCH | INFO |  |  | Table exists |
| v5_assistant_workspace_assignments.assigned_by | MATCH | INFO | varchar | varchar | Column type matches |
| v5_assistant_workspace_assignments.assistant_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_assistant_workspace_assignments.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_assistant_workspace_assignments.id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_assistant_workspace_assignments.org_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_assistant_workspace_assignments.role | MATCH | INFO | varchar | varchar | Column type matches |
| v5_assistant_workspace_assignments.workspace_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_assistant_workspace_assignments.ix_v5_assistant_workspace_assignments_assistant_id | MATCH | INFO |  |  | Index presence comparison |
| v5_assistant_workspace_assignments.ix_v5_assistant_workspace_assignments_org_id | MATCH | INFO |  |  | Index presence comparison |
| v5_assistant_workspace_assignments.ix_v5_assistant_workspace_assignments_workspace_id | MATCH | INFO |  |  | Index presence comparison |
| v5_assistant_workspace_assignments.uq_v5_assistant_workspace | EXTRA | INFO |  |  | Database index is not declared as explicit ORM Index |
| v5_assistants | MATCH | INFO |  |  | Table exists |
| v5_assistants.capability_permissions | MATCH | INFO | json | json | Column type matches |
| v5_assistants.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_assistants.current_version | MATCH | INFO | integer | integer | Column type matches |
| v5_assistants.description | MATCH | INFO | text | text | Column type matches |
| v5_assistants.id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_assistants.instructions | MATCH | INFO | text | text | Column type matches |
| v5_assistants.metrics_json | MATCH | INFO | json | json | Column type matches |
| v5_assistants.name | MATCH | INFO | varchar | varchar | Column type matches |
| v5_assistants.org_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_assistants.owner_user_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_assistants.status | MATCH | INFO | varchar | varchar | Column type matches |
| v5_assistants.updated_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_assistants.ix_v5_assistants_created_at | MATCH | INFO |  |  | Index presence comparison |
| v5_assistants.ix_v5_assistants_org_id | MATCH | INFO |  |  | Index presence comparison |
| v5_assistants.ix_v5_assistants_owner_user_id | MATCH | INFO |  |  | Index presence comparison |
| v5_assistants.ix_v5_assistants_status | MATCH | INFO |  |  | Index presence comparison |
| v5_audit_events | MATCH | INFO |  |  | Table exists |
| v5_audit_events.actor_user_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_audit_events.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_audit_events.event_type | MATCH | INFO | varchar | varchar | Column type matches |
| v5_audit_events.id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_audit_events.metadata_json | MATCH | INFO | json | json | Column type matches |
| v5_audit_events.org_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_audit_events.resource_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_audit_events.resource_type | MATCH | INFO | varchar | varchar | Column type matches |
| v5_audit_events.risk_level | MATCH | INFO | varchar | varchar | Column type matches |
| v5_audit_events.workspace_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_audit_events.ix_v5_audit_events_actor_user_id | MATCH | INFO |  |  | Index presence comparison |
| v5_audit_events.ix_v5_audit_events_created_at | MATCH | INFO |  |  | Index presence comparison |
| v5_audit_events.ix_v5_audit_events_event_type | MATCH | INFO |  |  | Index presence comparison |
| v5_audit_events.ix_v5_audit_events_org_id | MATCH | INFO |  |  | Index presence comparison |
| v5_audit_events.ix_v5_audit_events_workspace_id | MATCH | INFO |  |  | Index presence comparison |
| v5_billing_events | MATCH | INFO |  |  | Table exists |
| v5_billing_events.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_billing_events.event_type | MATCH | INFO | varchar | varchar | Column type matches |
| v5_billing_events.id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_billing_events.metadata_json | MATCH | INFO | json | json | Column type matches |
| v5_billing_events.org_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_billing_events.provider | MATCH | INFO | varchar | varchar | Column type matches |
| v5_billing_events.resource_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_billing_events.resource_type | MATCH | INFO | varchar | varchar | Column type matches |
| v5_billing_events.ix_v5_billing_events_created_at | MATCH | INFO |  |  | Index presence comparison |
| v5_billing_events.ix_v5_billing_events_event_type | MATCH | INFO |  |  | Index presence comparison |
| v5_billing_events.ix_v5_billing_events_org_id | MATCH | INFO |  |  | Index presence comparison |
| v5_billing_plans | MATCH | INFO |  |  | Table exists |
| v5_billing_plans.active | MATCH | INFO | boolean | boolean | Column type matches |
| v5_billing_plans.billing_model | MATCH | INFO | varchar | varchar | Column type matches |
| v5_billing_plans.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_billing_plans.entitlements_json | MATCH | INFO | json | json | Column type matches |
| v5_billing_plans.id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_billing_plans.included_usage | MATCH | INFO | json | json | Column type matches |
| v5_billing_plans.limits_json | MATCH | INFO | json | json | Column type matches |
| v5_billing_plans.metadata_json | MATCH | INFO | json | json | Column type matches |
| v5_billing_plans.monthly_price_cents | MATCH | INFO | integer | integer | Column type matches |
| v5_billing_plans.name | MATCH | INFO | varchar | varchar | Column type matches |
| v5_billing_plans.plan_key | MATCH | INFO | varchar | varchar | Column type matches |
| v5_billing_plans.seat_price_cents | MATCH | INFO | integer | integer | Column type matches |
| v5_billing_plans.tier | MATCH | INFO | varchar | varchar | Column type matches |
| v5_billing_plans.ix_v5_billing_plans_plan_key | MATCH | INFO |  |  | Index presence comparison |
| v5_billing_plans.ix_v5_billing_plans_tier | MATCH | INFO |  |  | Index presence comparison |
| v5_billing_settings | MATCH | INFO |  |  | Table exists |
| v5_billing_settings.billing_email | MATCH | INFO | varchar | varchar | Column type matches |
| v5_billing_settings.org_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_billing_settings.payment_provider | MATCH | INFO | varchar | varchar | Column type matches |
| v5_billing_settings.provider_customer_ref | MATCH | INFO | varchar | varchar | Column type matches |
| v5_billing_settings.tax_metadata | MATCH | INFO | json | json | Column type matches |
| v5_billing_settings.updated_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_budget_alerts | MATCH | INFO |  |  | Table exists |
| v5_budget_alerts.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_budget_alerts.created_by | MATCH | INFO | varchar | varchar | Column type matches |
| v5_budget_alerts.id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_budget_alerts.last_triggered_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_budget_alerts.monthly_budget_cents | MATCH | INFO | integer | integer | Column type matches |
| v5_budget_alerts.name | MATCH | INFO | varchar | varchar | Column type matches |
| v5_budget_alerts.org_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_budget_alerts.status | MATCH | INFO | varchar | varchar | Column type matches |
| v5_budget_alerts.threshold_percent | MATCH | INFO | integer | integer | Column type matches |
| v5_budget_alerts.workspace_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_budget_alerts.ix_v5_budget_alerts_org_id | MATCH | INFO |  |  | Index presence comparison |
| v5_budget_alerts.ix_v5_budget_alerts_status | MATCH | INFO |  |  | Index presence comparison |
| v5_budget_alerts.ix_v5_budget_alerts_workspace_id | MATCH | INFO |  |  | Index presence comparison |
| v5_compliance_exports | MATCH | INFO |  |  | Table exists |
| v5_compliance_exports.artifact_ref | MATCH | INFO | varchar | varchar | Column type matches |
| v5_compliance_exports.completed_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_compliance_exports.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_compliance_exports.export_type | MATCH | INFO | varchar | varchar | Column type matches |
| v5_compliance_exports.filters_json | MATCH | INFO | json | json | Column type matches |
| v5_compliance_exports.id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_compliance_exports.org_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_compliance_exports.requested_by | MATCH | INFO | varchar | varchar | Column type matches |
| v5_compliance_exports.retention_until | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_compliance_exports.status | MATCH | INFO | varchar | varchar | Column type matches |
| v5_compliance_exports.ix_v5_compliance_exports_created_at | MATCH | INFO |  |  | Index presence comparison |
| v5_compliance_exports.ix_v5_compliance_exports_export_type | MATCH | INFO |  |  | Index presence comparison |
| v5_compliance_exports.ix_v5_compliance_exports_org_id | MATCH | INFO |  |  | Index presence comparison |
| v5_compliance_exports.ix_v5_compliance_exports_status | MATCH | INFO |  |  | Index presence comparison |
| v5_entitlement_snapshots | MATCH | INFO |  |  | Table exists |
| v5_entitlement_snapshots.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_entitlement_snapshots.enforcement_metadata | MATCH | INFO | json | json | Column type matches |
| v5_entitlement_snapshots.features_json | MATCH | INFO | json | json | Column type matches |
| v5_entitlement_snapshots.id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_entitlement_snapshots.limits_json | MATCH | INFO | json | json | Column type matches |
| v5_entitlement_snapshots.org_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_entitlement_snapshots.plan_key | MATCH | INFO | varchar | varchar | Column type matches |
| v5_entitlement_snapshots.usage_json | MATCH | INFO | json | json | Column type matches |
| v5_entitlement_snapshots.ix_v5_entitlement_snapshots_created_at | MATCH | INFO |  |  | Index presence comparison |
| v5_entitlement_snapshots.ix_v5_entitlement_snapshots_org_id | MATCH | INFO |  |  | Index presence comparison |
| v5_entitlement_snapshots.ix_v5_entitlement_snapshots_plan_key | MATCH | INFO |  |  | Index presence comparison |
| v5_governance_approval_workflows | MATCH | INFO |  |  | Table exists |
| v5_governance_approval_workflows.approver_rules | MATCH | INFO | json | json | Column type matches |
| v5_governance_approval_workflows.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_governance_approval_workflows.created_by | MATCH | INFO | varchar | varchar | Column type matches |
| v5_governance_approval_workflows.id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_governance_approval_workflows.name | MATCH | INFO | varchar | varchar | Column type matches |
| v5_governance_approval_workflows.org_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_governance_approval_workflows.status | MATCH | INFO | varchar | varchar | Column type matches |
| v5_governance_approval_workflows.trigger_policy | MATCH | INFO | json | json | Column type matches |
| v5_governance_approval_workflows.workspace_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_governance_approval_workflows.ix_v5_governance_approval_workflows_org_id | MATCH | INFO |  |  | Index presence comparison |
| v5_governance_approval_workflows.ix_v5_governance_approval_workflows_status | MATCH | INFO |  |  | Index presence comparison |
| v5_governance_approval_workflows.ix_v5_governance_approval_workflows_workspace_id | MATCH | INFO |  |  | Index presence comparison |
| v5_governance_settings | MATCH | INFO |  |  | Table exists |
| v5_governance_settings.org_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_governance_settings.settings_json | MATCH | INFO | json | json | Column type matches |
| v5_governance_settings.updated_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_governance_settings.updated_by | MATCH | INFO | varchar | varchar | Column type matches |
| v5_governance_settings.v3_governance_ref | MATCH | INFO | varchar | varchar | Column type matches |
| v5_integration_catalog | MATCH | INFO |  |  | Table exists |
| v5_integration_catalog.auth_type | MATCH | INFO | varchar | varchar | Column type matches |
| v5_integration_catalog.capabilities | MATCH | INFO | json | json | Column type matches |
| v5_integration_catalog.category | MATCH | INFO | varchar | varchar | Column type matches |
| v5_integration_catalog.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_integration_catalog.id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_integration_catalog.metadata_json | MATCH | INFO | json | json | Column type matches |
| v5_integration_catalog.name | MATCH | INFO | varchar | varchar | Column type matches |
| v5_integration_catalog.provider_key | MATCH | INFO | varchar | varchar | Column type matches |
| v5_integration_catalog.scopes | MATCH | INFO | json | json | Column type matches |
| v5_integration_catalog.status | MATCH | INFO | varchar | varchar | Column type matches |
| v5_integration_catalog.ix_v5_integration_catalog_provider_key | MATCH | INFO |  |  | Index presence comparison |
| v5_integration_connections | MATCH | INFO |  |  | Table exists |
| v5_integration_connections.connected_by | MATCH | INFO | varchar | varchar | Column type matches |
| v5_integration_connections.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_integration_connections.health_status | MATCH | INFO | varchar | varchar | Column type matches |
| v5_integration_connections.id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_integration_connections.last_health_check_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_integration_connections.org_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_integration_connections.provider_key | MATCH | INFO | varchar | varchar | Column type matches |
| v5_integration_connections.status | MATCH | INFO | varchar | varchar | Column type matches |
| v5_integration_connections.token_metadata | MATCH | INFO | json | json | Column type matches |
| v5_integration_connections.token_ref | MATCH | INFO | varchar | varchar | Column type matches |
| v5_integration_connections.updated_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_integration_connections.workspace_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_integration_connections.ix_v5_integration_connections_created_at | MATCH | INFO |  |  | Index presence comparison |
| v5_integration_connections.ix_v5_integration_connections_org_id | MATCH | INFO |  |  | Index presence comparison |
| v5_integration_connections.ix_v5_integration_connections_provider_key | MATCH | INFO |  |  | Index presence comparison |
| v5_integration_connections.ix_v5_integration_connections_status | MATCH | INFO |  |  | Index presence comparison |
| v5_integration_connections.ix_v5_integration_connections_workspace_id | MATCH | INFO |  |  | Index presence comparison |
| v5_integration_health_events | MATCH | INFO |  |  | Table exists |
| v5_integration_health_events.connection_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_integration_health_events.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_integration_health_events.id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_integration_health_events.latency_ms | MATCH | INFO | integer | integer | Column type matches |
| v5_integration_health_events.message | MATCH | INFO | text | text | Column type matches |
| v5_integration_health_events.metadata_json | MATCH | INFO | json | json | Column type matches |
| v5_integration_health_events.status | MATCH | INFO | varchar | varchar | Column type matches |
| v5_integration_health_events.ix_v5_integration_health_events_connection_id | MATCH | INFO |  |  | Index presence comparison |
| v5_integration_health_events.ix_v5_integration_health_events_created_at | MATCH | INFO |  |  | Index presence comparison |
| v5_invitations | MATCH | INFO |  |  | Table exists |
| v5_invitations.accepted_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_invitations.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_invitations.email | MATCH | INFO | varchar | varchar | Column type matches |
| v5_invitations.expires_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_invitations.id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_invitations.invited_by | MATCH | INFO | varchar | varchar | Column type matches |
| v5_invitations.org_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_invitations.role | MATCH | INFO | varchar | varchar | Column type matches |
| v5_invitations.status | MATCH | INFO | varchar | varchar | Column type matches |
| v5_invitations.team_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_invitations.token | MATCH | INFO | varchar | varchar | Column type matches |
| v5_invitations.workspace_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_invitations.ix_v5_invitations_created_at | MATCH | INFO |  |  | Index presence comparison |
| v5_invitations.ix_v5_invitations_email | MATCH | INFO |  |  | Index presence comparison |
| v5_invitations.ix_v5_invitations_org_id | MATCH | INFO |  |  | Index presence comparison |
| v5_invitations.ix_v5_invitations_status | MATCH | INFO |  |  | Index presence comparison |
| v5_invitations.ix_v5_invitations_team_id | MATCH | INFO |  |  | Index presence comparison |
| v5_invitations.ix_v5_invitations_token | MATCH | INFO |  |  | Index presence comparison |
| v5_invitations.ix_v5_invitations_workspace_id | MATCH | INFO |  |  | Index presence comparison |
| v5_invoices | MATCH | INFO |  |  | Table exists |
| v5_invoices.amount_due_cents | MATCH | INFO | integer | integer | Column type matches |
| v5_invoices.currency | MATCH | INFO | varchar | varchar | Column type matches |
| v5_invoices.id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_invoices.invoice_number | MATCH | INFO | varchar | varchar | Column type matches |
| v5_invoices.issued_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_invoices.line_items | MATCH | INFO | json | json | Column type matches |
| v5_invoices.org_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_invoices.paid_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_invoices.period_end | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_invoices.period_start | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_invoices.status | MATCH | INFO | varchar | varchar | Column type matches |
| v5_invoices.subscription_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_invoices.ix_v5_invoices_invoice_number | MATCH | INFO |  |  | Index presence comparison |
| v5_invoices.ix_v5_invoices_org_id | MATCH | INFO |  |  | Index presence comparison |
| v5_invoices.ix_v5_invoices_subscription_id | MATCH | INFO |  |  | Index presence comparison |
| v5_notifications | MATCH | INFO |  |  | Table exists |
| v5_notifications.body | MATCH | INFO | text | text | Column type matches |
| v5_notifications.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_notifications.event_type | MATCH | INFO | varchar | varchar | Column type matches |
| v5_notifications.id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_notifications.metadata_json | MATCH | INFO | json | json | Column type matches |
| v5_notifications.org_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_notifications.read_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_notifications.title | MATCH | INFO | varchar | varchar | Column type matches |
| v5_notifications.user_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_notifications.workspace_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_notifications.ix_v5_notifications_created_at | MATCH | INFO |  |  | Index presence comparison |
| v5_notifications.ix_v5_notifications_event_type | MATCH | INFO |  |  | Index presence comparison |
| v5_notifications.ix_v5_notifications_org_id | MATCH | INFO |  |  | Index presence comparison |
| v5_notifications.ix_v5_notifications_user_id | MATCH | INFO |  |  | Index presence comparison |
| v5_notifications.ix_v5_notifications_workspace_id | MATCH | INFO |  |  | Index presence comparison |
| v5_organization_members | MATCH | INFO |  |  | Table exists |
| v5_organization_members.id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_organization_members.joined_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_organization_members.org_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_organization_members.role | MATCH | INFO | varchar | varchar | Column type matches |
| v5_organization_members.status | MATCH | INFO | varchar | varchar | Column type matches |
| v5_organization_members.user_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_organization_members.ix_v5_organization_members_org_id | MATCH | INFO |  |  | Index presence comparison |
| v5_organization_members.ix_v5_organization_members_user_id | MATCH | INFO |  |  | Index presence comparison |
| v5_organization_members.uq_v5_org_member | EXTRA | INFO |  |  | Database index is not declared as explicit ORM Index |
| v5_organization_settings | MATCH | INFO |  |  | Table exists |
| v5_organization_settings.org_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_organization_settings.settings | MATCH | INFO | json | json | Column type matches |
| v5_organization_settings.updated_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_organizations | MATCH | INFO |  |  | Table exists |
| v5_organizations.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_organizations.created_by | MATCH | INFO | varchar | varchar | Column type matches |
| v5_organizations.id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_organizations.name | MATCH | INFO | varchar | varchar | Column type matches |
| v5_organizations.slug | MATCH | INFO | varchar | varchar | Column type matches |
| v5_organizations.status | MATCH | INFO | varchar | varchar | Column type matches |
| v5_organizations.updated_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_organizations.ix_v5_organizations_slug | MATCH | INFO |  |  | Index presence comparison |
| v5_replay_shares | MATCH | INFO |  |  | Table exists |
| v5_replay_shares.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_replay_shares.created_by | MATCH | INFO | varchar | varchar | Column type matches |
| v5_replay_shares.expires_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_replay_shares.id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_replay_shares.org_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_replay_shares.redaction_policy | MATCH | INFO | json | json | Column type matches |
| v5_replay_shares.share_token | MATCH | INFO | varchar | varchar | Column type matches |
| v5_replay_shares.visibility | MATCH | INFO | varchar | varchar | Column type matches |
| v5_replay_shares.workflow_run_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_replay_shares.workspace_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_replay_shares.ix_v5_replay_shares_created_by | MATCH | INFO |  |  | Index presence comparison |
| v5_replay_shares.ix_v5_replay_shares_org_id | MATCH | INFO |  |  | Index presence comparison |
| v5_replay_shares.ix_v5_replay_shares_share_token | MATCH | INFO |  |  | Index presence comparison |
| v5_replay_shares.ix_v5_replay_shares_workflow_run_id | MATCH | INFO |  |  | Index presence comparison |
| v5_replay_shares.ix_v5_replay_shares_workspace_id | MATCH | INFO |  |  | Index presence comparison |
| v5_resource_versions | MATCH | INFO |  |  | Table exists |
| v5_resource_versions.change_summary | MATCH | INFO | text | text | Column type matches |
| v5_resource_versions.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_resource_versions.created_by | MATCH | INFO | varchar | varchar | Column type matches |
| v5_resource_versions.diff_metadata | MATCH | INFO | json | json | Column type matches |
| v5_resource_versions.id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_resource_versions.org_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_resource_versions.resource_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_resource_versions.resource_type | MATCH | INFO | varchar | varchar | Column type matches |
| v5_resource_versions.rollback_of_version_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_resource_versions.snapshot_json | MATCH | INFO | json | json | Column type matches |
| v5_resource_versions.version_number | MATCH | INFO | integer | integer | Column type matches |
| v5_resource_versions.workspace_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_resource_versions.ix_v5_resource_versions_created_at | MATCH | INFO |  |  | Index presence comparison |
| v5_resource_versions.ix_v5_resource_versions_org_id | MATCH | INFO |  |  | Index presence comparison |
| v5_resource_versions.ix_v5_resource_versions_resource_id | MATCH | INFO |  |  | Index presence comparison |
| v5_resource_versions.ix_v5_resource_versions_resource_type | MATCH | INFO |  |  | Index presence comparison |
| v5_resource_versions.ix_v5_resource_versions_workspace_id | MATCH | INFO |  |  | Index presence comparison |
| v5_retention_jobs | MATCH | INFO |  |  | Table exists |
| v5_retention_jobs.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_retention_jobs.id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_retention_jobs.metadata_json | MATCH | INFO | json | json | Column type matches |
| v5_retention_jobs.org_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_retention_jobs.rule_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_retention_jobs.scheduled_for | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_retention_jobs.status | MATCH | INFO | varchar | varchar | Column type matches |
| v5_retention_jobs.ix_v5_retention_jobs_org_id | MATCH | INFO |  |  | Index presence comparison |
| v5_retention_jobs.ix_v5_retention_jobs_rule_id | MATCH | INFO |  |  | Index presence comparison |
| v5_retention_jobs.ix_v5_retention_jobs_status | MATCH | INFO |  |  | Index presence comparison |
| v5_retention_rules | MATCH | INFO |  |  | Table exists |
| v5_retention_rules.action | MATCH | INFO | varchar | varchar | Column type matches |
| v5_retention_rules.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_retention_rules.created_by | MATCH | INFO | varchar | varchar | Column type matches |
| v5_retention_rules.data_type | MATCH | INFO | varchar | varchar | Column type matches |
| v5_retention_rules.id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_retention_rules.org_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_retention_rules.retention_days | MATCH | INFO | integer | integer | Column type matches |
| v5_retention_rules.status | MATCH | INFO | varchar | varchar | Column type matches |
| v5_retention_rules.workspace_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_retention_rules.ix_v5_retention_rules_data_type | MATCH | INFO |  |  | Index presence comparison |
| v5_retention_rules.ix_v5_retention_rules_org_id | MATCH | INFO |  |  | Index presence comparison |
| v5_retention_rules.ix_v5_retention_rules_status | MATCH | INFO |  |  | Index presence comparison |
| v5_retention_rules.ix_v5_retention_rules_workspace_id | MATCH | INFO |  |  | Index presence comparison |
| v5_saved_tasks | MATCH | INFO |  |  | Table exists |
| v5_saved_tasks.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_saved_tasks.description | MATCH | INFO | text | text | Column type matches |
| v5_saved_tasks.favorite | MATCH | INFO | boolean | boolean | Column type matches |
| v5_saved_tasks.id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_saved_tasks.input_prompt | MATCH | INFO | text | text | Column type matches |
| v5_saved_tasks.org_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_saved_tasks.owner_user_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_saved_tasks.parameters_json | MATCH | INFO | json | json | Column type matches |
| v5_saved_tasks.run_count | MATCH | INFO | integer | integer | Column type matches |
| v5_saved_tasks.scope | MATCH | INFO | varchar | varchar | Column type matches |
| v5_saved_tasks.source_workflow_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_saved_tasks.tags | MATCH | INFO | json | json | Column type matches |
| v5_saved_tasks.title | MATCH | INFO | varchar | varchar | Column type matches |
| v5_saved_tasks.updated_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_saved_tasks.workspace_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_saved_tasks.ix_v5_saved_tasks_created_at | MATCH | INFO |  |  | Index presence comparison |
| v5_saved_tasks.ix_v5_saved_tasks_org_id | MATCH | INFO |  |  | Index presence comparison |
| v5_saved_tasks.ix_v5_saved_tasks_owner_user_id | MATCH | INFO |  |  | Index presence comparison |
| v5_saved_tasks.ix_v5_saved_tasks_scope | MATCH | INFO |  |  | Index presence comparison |
| v5_saved_tasks.ix_v5_saved_tasks_source_workflow_id | MATCH | INFO |  |  | Index presence comparison |
| v5_saved_tasks.ix_v5_saved_tasks_workspace_id | MATCH | INFO |  |  | Index presence comparison |
| v5_scim_configurations | MATCH | INFO |  |  | Table exists |
| v5_scim_configurations.base_url | MATCH | INFO | text | text | Column type matches |
| v5_scim_configurations.bearer_token_hash | MATCH | INFO | text | text | Column type matches |
| v5_scim_configurations.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_scim_configurations.group_mapping | MATCH | INFO | json | json | Column type matches |
| v5_scim_configurations.id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_scim_configurations.metadata_json | MATCH | INFO | json | json | Column type matches |
| v5_scim_configurations.org_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_scim_configurations.provisioning_status | MATCH | INFO | varchar | varchar | Column type matches |
| v5_scim_configurations.updated_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_scim_configurations.updated_by | MATCH | INFO | varchar | varchar | Column type matches |
| v5_scim_configurations.user_mapping | MATCH | INFO | json | json | Column type matches |
| v5_scim_configurations.ix_v5_scim_configurations_org_id | MATCH | INFO |  |  | Index presence comparison |
| v5_scim_configurations.ix_v5_scim_configurations_provisioning_status | MATCH | INFO |  |  | Index presence comparison |
| v5_scim_sync_events | MATCH | INFO |  |  | Table exists |
| v5_scim_sync_events.action | MATCH | INFO | varchar | varchar | Column type matches |
| v5_scim_sync_events.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_scim_sync_events.external_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_scim_sync_events.id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_scim_sync_events.metadata_json | MATCH | INFO | json | json | Column type matches |
| v5_scim_sync_events.org_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_scim_sync_events.resource_type | MATCH | INFO | varchar | varchar | Column type matches |
| v5_scim_sync_events.scim_config_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_scim_sync_events.status | MATCH | INFO | varchar | varchar | Column type matches |
| v5_scim_sync_events.ix_v5_scim_sync_events_created_at | MATCH | INFO |  |  | Index presence comparison |
| v5_scim_sync_events.ix_v5_scim_sync_events_org_id | MATCH | INFO |  |  | Index presence comparison |
| v5_scim_sync_events.ix_v5_scim_sync_events_resource_type | MATCH | INFO |  |  | Index presence comparison |
| v5_scim_sync_events.ix_v5_scim_sync_events_scim_config_id | MATCH | INFO |  |  | Index presence comparison |
| v5_security_policies | MATCH | INFO |  |  | Table exists |
| v5_security_policies.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_security_policies.created_by | MATCH | INFO | varchar | varchar | Column type matches |
| v5_security_policies.current_version | MATCH | INFO | integer | integer | Column type matches |
| v5_security_policies.id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_security_policies.name | MATCH | INFO | varchar | varchar | Column type matches |
| v5_security_policies.org_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_security_policies.policy_type | MATCH | INFO | varchar | varchar | Column type matches |
| v5_security_policies.rules_json | MATCH | INFO | json | json | Column type matches |
| v5_security_policies.status | MATCH | INFO | varchar | varchar | Column type matches |
| v5_security_policies.updated_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_security_policies.workspace_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_security_policies.ix_v5_security_policies_org_id | MATCH | INFO |  |  | Index presence comparison |
| v5_security_policies.ix_v5_security_policies_policy_type | MATCH | INFO |  |  | Index presence comparison |
| v5_security_policies.ix_v5_security_policies_status | MATCH | INFO |  |  | Index presence comparison |
| v5_security_policies.ix_v5_security_policies_workspace_id | MATCH | INFO |  |  | Index presence comparison |
| v5_security_policy_versions | MATCH | INFO |  |  | Table exists |
| v5_security_policy_versions.change_summary | MATCH | INFO | text | text | Column type matches |
| v5_security_policy_versions.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_security_policy_versions.created_by | MATCH | INFO | varchar | varchar | Column type matches |
| v5_security_policy_versions.id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_security_policy_versions.policy_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_security_policy_versions.rules_json | MATCH | INFO | json | json | Column type matches |
| v5_security_policy_versions.version_number | MATCH | INFO | integer | integer | Column type matches |
| v5_security_policy_versions.ix_v5_security_policy_versions_policy_id | MATCH | INFO |  |  | Index presence comparison |
| v5_security_policy_versions.uq_v5_security_policy_version | EXTRA | INFO |  |  | Database index is not declared as explicit ORM Index |
| v5_sessions | MATCH | INFO |  |  | Table exists |
| v5_sessions.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_sessions.expires_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_sessions.id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_sessions.last_seen_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_sessions.revoked | MATCH | INFO | boolean | boolean | Column type matches |
| v5_sessions.token_hash | MATCH | INFO | text | text | Column type matches |
| v5_sessions.user_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_sessions.ix_v5_sessions_user_id | MATCH | INFO |  |  | Index presence comparison |
| v5_sessions.v5_sessions_token_hash_key | EXTRA | INFO |  |  | Database index is not declared as explicit ORM Index |
| v5_sso_configurations | MATCH | INFO |  |  | Table exists |
| v5_sso_configurations.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_sso_configurations.domain_verification | MATCH | INFO | json | json | Column type matches |
| v5_sso_configurations.enforce_sso | MATCH | INFO | boolean | boolean | Column type matches |
| v5_sso_configurations.id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_sso_configurations.idp_metadata | MATCH | INFO | json | json | Column type matches |
| v5_sso_configurations.login_policy | MATCH | INFO | json | json | Column type matches |
| v5_sso_configurations.oidc_metadata | MATCH | INFO | json | json | Column type matches |
| v5_sso_configurations.org_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_sso_configurations.provider_mode | MATCH | INFO | varchar | varchar | Column type matches |
| v5_sso_configurations.saml_metadata | MATCH | INFO | json | json | Column type matches |
| v5_sso_configurations.status | MATCH | INFO | varchar | varchar | Column type matches |
| v5_sso_configurations.updated_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_sso_configurations.updated_by | MATCH | INFO | varchar | varchar | Column type matches |
| v5_sso_configurations.ix_v5_sso_configurations_org_id | MATCH | INFO |  |  | Index presence comparison |
| v5_sso_configurations.ix_v5_sso_configurations_status | MATCH | INFO |  |  | Index presence comparison |
| v5_subscriptions | MATCH | INFO |  |  | Table exists |
| v5_subscriptions.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_subscriptions.current_period_end | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_subscriptions.current_period_start | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_subscriptions.id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_subscriptions.metadata_json | MATCH | INFO | json | json | Column type matches |
| v5_subscriptions.org_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_subscriptions.plan_key | MATCH | INFO | varchar | varchar | Column type matches |
| v5_subscriptions.provider | MATCH | INFO | varchar | varchar | Column type matches |
| v5_subscriptions.provider_ref | MATCH | INFO | varchar | varchar | Column type matches |
| v5_subscriptions.seat_count | MATCH | INFO | integer | integer | Column type matches |
| v5_subscriptions.status | MATCH | INFO | varchar | varchar | Column type matches |
| v5_subscriptions.trial_ends_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_subscriptions.updated_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_subscriptions.ix_v5_subscriptions_org_id | MATCH | INFO |  |  | Index presence comparison |
| v5_subscriptions.ix_v5_subscriptions_plan_key | MATCH | INFO |  |  | Index presence comparison |
| v5_subscriptions.ix_v5_subscriptions_status | MATCH | INFO |  |  | Index presence comparison |
| v5_team_activity | MATCH | INFO |  |  | Table exists |
| v5_team_activity.activity_type | MATCH | INFO | varchar | varchar | Column type matches |
| v5_team_activity.actor_user_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_team_activity.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_team_activity.id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_team_activity.metadata_json | MATCH | INFO | json | json | Column type matches |
| v5_team_activity.org_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_team_activity.summary | MATCH | INFO | text | text | Column type matches |
| v5_team_activity.team_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_team_activity.workspace_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_team_activity.ix_v5_team_activity_activity_type | MATCH | INFO |  |  | Index presence comparison |
| v5_team_activity.ix_v5_team_activity_actor_user_id | MATCH | INFO |  |  | Index presence comparison |
| v5_team_activity.ix_v5_team_activity_created_at | MATCH | INFO |  |  | Index presence comparison |
| v5_team_activity.ix_v5_team_activity_org_id | MATCH | INFO |  |  | Index presence comparison |
| v5_team_activity.ix_v5_team_activity_team_id | MATCH | INFO |  |  | Index presence comparison |
| v5_team_activity.ix_v5_team_activity_workspace_id | MATCH | INFO |  |  | Index presence comparison |
| v5_team_members | MATCH | INFO |  |  | Table exists |
| v5_team_members.id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_team_members.joined_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_team_members.role | MATCH | INFO | varchar | varchar | Column type matches |
| v5_team_members.team_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_team_members.user_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_team_members.ix_v5_team_members_team_id | MATCH | INFO |  |  | Index presence comparison |
| v5_team_members.ix_v5_team_members_user_id | MATCH | INFO |  |  | Index presence comparison |
| v5_team_members.uq_v5_team_member | EXTRA | INFO |  |  | Database index is not declared as explicit ORM Index |
| v5_teams | MATCH | INFO |  |  | Table exists |
| v5_teams.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_teams.created_by | MATCH | INFO | varchar | varchar | Column type matches |
| v5_teams.id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_teams.name | MATCH | INFO | varchar | varchar | Column type matches |
| v5_teams.org_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_teams.ix_v5_teams_org_id | MATCH | INFO |  |  | Index presence comparison |
| v5_template_versions | MATCH | INFO |  |  | Table exists |
| v5_template_versions.body | MATCH | INFO | json | json | Column type matches |
| v5_template_versions.change_summary | MATCH | INFO | text | text | Column type matches |
| v5_template_versions.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_template_versions.created_by | MATCH | INFO | varchar | varchar | Column type matches |
| v5_template_versions.description | MATCH | INFO | text | text | Column type matches |
| v5_template_versions.id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_template_versions.parameter_schema | MATCH | INFO | json | json | Column type matches |
| v5_template_versions.template_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_template_versions.title | MATCH | INFO | varchar | varchar | Column type matches |
| v5_template_versions.version_number | MATCH | INFO | integer | integer | Column type matches |
| v5_template_versions.ix_v5_template_versions_template_id | MATCH | INFO |  |  | Index presence comparison |
| v5_template_versions.uq_v5_template_version | EXTRA | INFO |  |  | Database index is not declared as explicit ORM Index |
| v5_templates | MATCH | INFO |  |  | Table exists |
| v5_templates.body | MATCH | INFO | json | json | Column type matches |
| v5_templates.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_templates.current_version | MATCH | INFO | integer | integer | Column type matches |
| v5_templates.description | MATCH | INFO | text | text | Column type matches |
| v5_templates.forked_from_template_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_templates.id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_templates.org_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_templates.owner_user_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_templates.parameter_schema | MATCH | INFO | json | json | Column type matches |
| v5_templates.status | MATCH | INFO | varchar | varchar | Column type matches |
| v5_templates.title | MATCH | INFO | varchar | varchar | Column type matches |
| v5_templates.updated_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_templates.workspace_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_templates.ix_v5_templates_created_at | MATCH | INFO |  |  | Index presence comparison |
| v5_templates.ix_v5_templates_forked_from_template_id | MATCH | INFO |  |  | Index presence comparison |
| v5_templates.ix_v5_templates_org_id | MATCH | INFO |  |  | Index presence comparison |
| v5_templates.ix_v5_templates_owner_user_id | MATCH | INFO |  |  | Index presence comparison |
| v5_templates.ix_v5_templates_workspace_id | MATCH | INFO |  |  | Index presence comparison |
| v5_usage_records | MATCH | INFO |  |  | Table exists |
| v5_usage_records.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_usage_records.id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_usage_records.metadata_json | MATCH | INFO | json | json | Column type matches |
| v5_usage_records.org_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_usage_records.quantity | MATCH | INFO | integer | integer | Column type matches |
| v5_usage_records.unit | MATCH | INFO | varchar | varchar | Column type matches |
| v5_usage_records.usage_type | MATCH | INFO | varchar | varchar | Column type matches |
| v5_usage_records.user_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_usage_records.workflow_run_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_usage_records.workspace_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_usage_records.ix_v5_usage_records_created_at | MATCH | INFO |  |  | Index presence comparison |
| v5_usage_records.ix_v5_usage_records_org_id | MATCH | INFO |  |  | Index presence comparison |
| v5_usage_records.ix_v5_usage_records_usage_type | MATCH | INFO |  |  | Index presence comparison |
| v5_usage_records.ix_v5_usage_records_user_id | MATCH | INFO |  |  | Index presence comparison |
| v5_usage_records.ix_v5_usage_records_workflow_run_id | MATCH | INFO |  |  | Index presence comparison |
| v5_usage_records.ix_v5_usage_records_workspace_id | MATCH | INFO |  |  | Index presence comparison |
| v5_usage_rollups | MATCH | INFO |  |  | Table exists |
| v5_usage_rollups.id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_usage_rollups.org_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_usage_rollups.period | MATCH | INFO | varchar | varchar | Column type matches |
| v5_usage_rollups.quantity | MATCH | INFO | integer | integer | Column type matches |
| v5_usage_rollups.unit | MATCH | INFO | varchar | varchar | Column type matches |
| v5_usage_rollups.updated_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_usage_rollups.usage_type | MATCH | INFO | varchar | varchar | Column type matches |
| v5_usage_rollups.workspace_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_usage_rollups.ix_v5_usage_rollups_org_id | MATCH | INFO |  |  | Index presence comparison |
| v5_usage_rollups.ix_v5_usage_rollups_period | MATCH | INFO |  |  | Index presence comparison |
| v5_usage_rollups.ix_v5_usage_rollups_usage_type | MATCH | INFO |  |  | Index presence comparison |
| v5_usage_rollups.ix_v5_usage_rollups_workspace_id | MATCH | INFO |  |  | Index presence comparison |
| v5_usage_rollups.uq_v5_usage_rollup | EXTRA | INFO |  |  | Database index is not declared as explicit ORM Index |
| v5_user_preferences | MATCH | INFO |  |  | Table exists |
| v5_user_preferences.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_user_preferences.preferences | MATCH | INFO | json | json | Column type matches |
| v5_user_preferences.updated_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_user_preferences.user_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_user_profiles | MATCH | INFO |  |  | Table exists |
| v5_user_profiles.avatar_url | MATCH | INFO | text | text | Column type matches |
| v5_user_profiles.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_user_profiles.locale | MATCH | INFO | varchar | varchar | Column type matches |
| v5_user_profiles.timezone | MATCH | INFO | varchar | varchar | Column type matches |
| v5_user_profiles.updated_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_user_profiles.user_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_users | MATCH | INFO |  |  | Table exists |
| v5_users.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_users.email | MATCH | INFO | varchar | varchar | Column type matches |
| v5_users.id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_users.name | MATCH | INFO | varchar | varchar | Column type matches |
| v5_users.password_hash | MATCH | INFO | text | text | Column type matches |
| v5_users.status | MATCH | INFO | varchar | varchar | Column type matches |
| v5_users.updated_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_users.ix_v5_users_email | MATCH | INFO |  |  | Index presence comparison |
| v5_workflow_runs | MATCH | INFO |  |  | Table exists |
| v5_workflow_runs.browser_session_ref | MATCH | INFO | varchar | varchar | Column type matches |
| v5_workflow_runs.completed_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_workflow_runs.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_workflow_runs.error_class | MATCH | INFO | varchar | varchar | Column type matches |
| v5_workflow_runs.id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_workflow_runs.input_summary | MATCH | INFO | text | text | Column type matches |
| v5_workflow_runs.org_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_workflow_runs.output_summary | MATCH | INFO | text | text | Column type matches |
| v5_workflow_runs.parameters_json | MATCH | INFO | json | json | Column type matches |
| v5_workflow_runs.rerun_of_workflow_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_workflow_runs.runtime_ref | MATCH | INFO | varchar | varchar | Column type matches |
| v5_workflow_runs.source_workflow_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_workflow_runs.started_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_workflow_runs.status | MATCH | INFO | varchar | varchar | Column type matches |
| v5_workflow_runs.title | MATCH | INFO | text | text | Column type matches |
| v5_workflow_runs.updated_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_workflow_runs.user_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_workflow_runs.workspace_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_workflow_runs.ix_v5_workflow_runs_org_id | MATCH | INFO |  |  | Index presence comparison |
| v5_workflow_runs.ix_v5_workflow_runs_rerun_of_workflow_id | MATCH | INFO |  |  | Index presence comparison |
| v5_workflow_runs.ix_v5_workflow_runs_source_workflow_id | MATCH | INFO |  |  | Index presence comparison |
| v5_workflow_runs.ix_v5_workflow_runs_status | MATCH | INFO |  |  | Index presence comparison |
| v5_workflow_runs.ix_v5_workflow_runs_user_id | MATCH | INFO |  |  | Index presence comparison |
| v5_workflow_runs.ix_v5_workflow_runs_workspace_id | MATCH | INFO |  |  | Index presence comparison |
| v5_workflow_steps | MATCH | INFO |  |  | Table exists |
| v5_workflow_steps.action_type | MATCH | INFO | varchar | varchar | Column type matches |
| v5_workflow_steps.capability_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_workflow_steps.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_workflow_steps.duration_ms | MATCH | INFO | integer | integer | Column type matches |
| v5_workflow_steps.id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_workflow_steps.metadata_json | MATCH | INFO | json | json | Column type matches |
| v5_workflow_steps.status | MATCH | INFO | varchar | varchar | Column type matches |
| v5_workflow_steps.step_index | MATCH | INFO | integer | integer | Column type matches |
| v5_workflow_steps.validation_status | MATCH | INFO | varchar | varchar | Column type matches |
| v5_workflow_steps.workflow_run_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_workflow_steps.ix_v5_workflow_steps_workflow_run_id | MATCH | INFO |  |  | Index presence comparison |
| v5_workspace_members | MATCH | INFO |  |  | Table exists |
| v5_workspace_members.id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_workspace_members.joined_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_workspace_members.role | MATCH | INFO | varchar | varchar | Column type matches |
| v5_workspace_members.user_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_workspace_members.workspace_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_workspace_members.ix_v5_workspace_members_user_id | MATCH | INFO |  |  | Index presence comparison |
| v5_workspace_members.ix_v5_workspace_members_workspace_id | MATCH | INFO |  |  | Index presence comparison |
| v5_workspace_members.uq_v5_workspace_member | EXTRA | INFO |  |  | Database index is not declared as explicit ORM Index |
| v5_workspace_settings | MATCH | INFO |  |  | Table exists |
| v5_workspace_settings.settings | MATCH | INFO | json | json | Column type matches |
| v5_workspace_settings.updated_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_workspace_settings.workspace_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_workspace_shares | MATCH | INFO |  |  | Table exists |
| v5_workspace_shares.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_workspace_shares.created_by | MATCH | INFO | varchar | varchar | Column type matches |
| v5_workspace_shares.id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_workspace_shares.org_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_workspace_shares.role | MATCH | INFO | varchar | varchar | Column type matches |
| v5_workspace_shares.team_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_workspace_shares.workspace_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_workspace_shares.ix_v5_workspace_shares_org_id | MATCH | INFO |  |  | Index presence comparison |
| v5_workspace_shares.ix_v5_workspace_shares_team_id | MATCH | INFO |  |  | Index presence comparison |
| v5_workspace_shares.ix_v5_workspace_shares_workspace_id | MATCH | INFO |  |  | Index presence comparison |
| v5_workspace_shares.uq_v5_workspace_team_share | EXTRA | INFO |  |  | Database index is not declared as explicit ORM Index |
| v5_workspaces | MATCH | INFO |  |  | Table exists |
| v5_workspaces.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_workspaces.created_by | MATCH | INFO | varchar | varchar | Column type matches |
| v5_workspaces.description | MATCH | INFO | text | text | Column type matches |
| v5_workspaces.id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_workspaces.name | MATCH | INFO | varchar | varchar | Column type matches |
| v5_workspaces.org_id | MATCH | INFO | varchar | varchar | Column type matches |
| v5_workspaces.status | MATCH | INFO | varchar | varchar | Column type matches |
| v5_workspaces.updated_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| v5_workspaces.ix_v5_workspaces_org_id | MATCH | INFO |  |  | Index presence comparison |
| validation_benchmark_runs | MATCH | INFO |  |  | Table exists |
| validation_benchmark_runs.benchmark_id | MATCH | INFO | varchar | varchar | Column type matches |
| validation_benchmark_runs.category | MATCH | INFO | varchar | varchar | Column type matches |
| validation_benchmark_runs.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| validation_benchmark_runs.diagnostics | MATCH | INFO | json | json | Column type matches |
| validation_benchmark_runs.metrics | MATCH | INFO | json | json | Column type matches |
| validation_benchmark_runs.mission_id | MATCH | INFO | varchar | varchar | Column type matches |
| validation_benchmark_runs.report | MATCH | INFO | json | json | Column type matches |
| validation_benchmark_runs.run_id | MATCH | INFO | varchar | varchar | Column type matches |
| validation_benchmark_runs.score | MATCH | INFO | float | double precision | Column type matches |
| validation_benchmark_runs.status | MATCH | INFO | varchar | varchar | Column type matches |
| validation_benchmark_runs.ix_validation_benchmark_runs_benchmark_id | MATCH | INFO |  |  | Index presence comparison |
| validation_benchmark_runs.ix_validation_benchmark_runs_category | MATCH | INFO |  |  | Index presence comparison |
| validation_benchmark_runs.ix_validation_benchmark_runs_created_at | MATCH | INFO |  |  | Index presence comparison |
| validation_benchmark_runs.ix_validation_benchmark_runs_mission_id | MATCH | INFO |  |  | Index presence comparison |
| workflow_budgets | MATCH | INFO |  |  | Table exists |
| workflow_budgets.max_duration_seconds | MATCH | INFO | integer | integer | Column type matches |
| workflow_budgets.max_retries | MATCH | INFO | integer | integer | Column type matches |
| workflow_budgets.max_steps | MATCH | INFO | integer | integer | Column type matches |
| workflow_budgets.max_tokens | MATCH | INFO | integer | integer | Column type matches |
| workflow_budgets.retries_used | MATCH | INFO | integer | integer | Column type matches |
| workflow_budgets.session_id | MATCH | INFO | varchar | varchar | Column type matches |
| workflow_budgets.started_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| workflow_budgets.steps_used | MATCH | INFO | integer | integer | Column type matches |
| workflow_budgets.tokens_used | MATCH | INFO | integer | integer | Column type matches |
| workflow_budgets.updated_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| workflow_cost_metrics | MATCH | INFO |  |  | Table exists |
| workflow_cost_metrics.planner_calls | MATCH | INFO | integer | integer | Column type matches |
| workflow_cost_metrics.planning_latency_ms | MATCH | INFO | integer | integer | Column type matches |
| workflow_cost_metrics.session_id | MATCH | INFO | varchar | varchar | Column type matches |
| workflow_cost_metrics.tokens_used | MATCH | INFO | integer | integer | Column type matches |
| workflow_cost_metrics.updated_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| workflow_cost_metrics.vision_calls | MATCH | INFO | integer | integer | Column type matches |
| workflow_events | MATCH | INFO |  |  | Table exists |
| workflow_events.action_type | MATCH | INFO | varchar | varchar | Column type matches |
| workflow_events.ai_reasoning | MATCH | INFO | text | text | Column type matches |
| workflow_events.approved_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| workflow_events.confidence | MATCH | INFO | float | double precision | Column type matches |
| workflow_events.created_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| workflow_events.description | MATCH | INFO | text | text | Column type matches |
| workflow_events.event_type | MATCH | INFO | varchar | varchar | Column type matches |
| workflow_events.executed_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
| workflow_events.execution_result | MATCH | INFO | varchar | varchar | Column type matches |
| workflow_events.id | MATCH | INFO | varchar | varchar | Column type matches |
| workflow_events.safety_level | MATCH | INFO | varchar | varchar | Column type matches |
| workflow_events.session_id | MATCH | INFO | varchar | varchar | Column type matches |
| workflow_events.target_selector | MATCH | INFO | text | text | Column type matches |
| workflow_events.value | MATCH | INFO | text | text | Column type matches |
| workflow_states | MATCH | INFO |  |  | Table exists |
| workflow_states.facts | MATCH | INFO | json | json | Column type matches |
| workflow_states.id | MATCH | INFO | varchar | varchar | Column type matches |
| workflow_states.session_id | MATCH | INFO | varchar | varchar | Column type matches |
| workflow_states.updated_at | MATCH | INFO | timestamp without time zone | timestamp | Column type matches |
