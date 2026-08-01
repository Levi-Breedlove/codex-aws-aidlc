# Project diagram patterns

Load only during Design when the Engine reports a required project diagram that
is not current. These are syntax patterns, not application architecture,
evidence, lifecycle state, or authority. Replace every example identifier and
label with current canonical PRD records. Remove unused nodes and paths.

## System context pattern

Use a flowchart for the selected architecture, external actors, interfaces,
data boundaries, and material dependencies.

```mermaid
flowchart LR
    ARCH-0000["Selected application"]
    API-000["Approved interface"]
    ARCH-0000 -->|serves through| API-000
```

## Primary outcome pattern

Show the shortest approved end-to-end user outcome. Keep relationship labels in
plain language and bind every endpoint in the diagram contract.

```mermaid
flowchart LR
    ACT-000["Primary user"]
    API-000["Approved interface"]
    ACT-000 -->|requests outcome through| API-000
    API-000 -->|returns approved result to| ACT-000
```

## Data lifecycle pattern

Use only when current data, retention, deletion, or recovery records make the
view applicable.

```mermaid
flowchart LR
    API-000["Approved interface"]
    DATA-000["Approved data lifecycle"]
    API-000 -->|stores approved data in| DATA-000
```

## Failure and recovery pattern

Use only for current failure, asynchronous, rollback, or recovery behavior.

```mermaid
flowchart LR
    API-000["Approved interface"]
    REL-000["Approved recovery requirement"]
    API-000 -->|fails safely and invokes| REL-000
```

## Migration pattern

Use only for brownfield or migration work. Show the preserved source, bounded
transition, validation point, and rollback target with their canonical IDs.

Never imply that a planned diagram was deployed or observed. Mermaid rendering
changes do not redefine architecture; relationship or canonical-ID changes do.
