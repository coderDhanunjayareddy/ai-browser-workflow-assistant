# Mission Blueprint V1 Wave 2

Wave 2 teaches Mission Intelligence to create passive Mission Blueprints from a
user goal.

## Boundary

Mission Intelligence may now create and persist a Blueprint artifact. The
artifact remains passive:

- no Mission Ledger intents are created
- no Workflow Orchestrator behavior changes
- no Planner Contract V2 changes
- no Intent Runtime changes
- no Mission Completion integration
- no Browser Runtime changes

## Builder

`app.mission.intelligence.blueprint_builder.MissionBlueprintBuilder` converts:

- mission understanding
- mission analysis
- mission classification
- capability requirements
- risk assessment
- dependency analysis

into a validated `MissionBlueprint`.

`create_and_store_blueprint(...)` persists the generated Blueprint through the
`MissionBlueprintRepository` interface and creates revision 1.

## Supported Mission Types

- research
- navigation
- data extraction
- file processing

Each type creates provider-independent objective nodes. Nodes describe mission
work such as discovering sources, collecting records, reading content, validating
coverage, or delivering an artifact. They do not describe clicks, selectors, or
browser-specific commands.

## Capability Mapping

Capabilities are provider-independent labels:

- Browser
- Search
- Knowledge Extraction
- Validation
- Report Generation
- File Processing
- OCR
- Vision
- Human Clarification

Wave 2 records these capabilities in Blueprint metadata and node expansion
metadata only. Capability records do not dispatch executors.

## API Exposure

The existing read-only Blueprint APIs now expose:

- mission analysis
- capability requirements
- risk summary
- clarification requirements
- dependency graph

No mutation API is added.
