# Project diagram patterns

Load only during Design when the Engine reports a required project diagram that
is not current. These are syntax and presentation patterns, not application architecture,
evidence, lifecycle state, or authority. Replace every example identifier and
label with current canonical PRD records. Remove unused nodes and paths.

## Composition rules

### Authority and purpose

- Use only current canonical requirements, architecture, interface, event, data, boundary, state, technology, and actor records.
- Bind every displayed node and relationship through the Project Diagram Contract. Never invent an element for visual symmetry.
- Give each diagram one owner question. Use focused views for data, failure, migration, journey, and state detail instead of combining several stories into one dense view.
- Diagrams describe planned design unless observed evidence explicitly establishes otherwise. They never prove implementation, testing, deployment, AWS access, spending, or authorization.
- This procedure grants no application write, AWS, deployment, publication, or GitHub authority.

### Professional layout

- Put external actors and systems outside the main system boundary. Express membership through containment, never an arrow labeled includes.
- Use no more than three boundary levels. Group peers by public entry, processing, automation, data, messaging, observability, cost, delivery, or recovery.
- Use a left-to-right flow only for a compact linear story. Use top-to-bottom flow for complete architecture, AWS implementation, branching, and component-rich views.
- Do not rely on a nested subgraph direction when its nodes connect outside that subgraph. Organize the parent direction, declaration order, and boundaries.
- Aim for 12–20 nodes in broad views. Keep nodes to at most three visual lines, boundaries to at most two, and relationships to at most two; every line contains 1–48 visible characters.
- Use solid arrows for primary runtime and data flow. Use dashed arrows for trust, telemetry, control, planning, and optional relationships.
- Start new flowcharts with the exact linear-arrow initialization shown below.
  It is the supported static presentation configuration; do not add other init
  settings, callbacks, HTML-label options, or active directives. Existing
  diagrams without it remain readable. Styling does not change semantic relationships.
- Use comments to divide request, data, failure, and operations flows in Mermaid source.
- Declare the primary owner-to-outcome runtime spine in reading order. Keep
  operations and recovery on one side of that spine and data and safeguards on
  the other when the renderer permits it. Reorder declarations or move detail
  to a focused view before accepting long edges that cross unrelated groups.
- Use at most six semantic class styles. Assign color by meaning, keep fills
  light and text dark, and never rely on color alone.
- Keep each node to at most three intentional visual lines, each near 40
  visible characters. Break a long relationship label into at most two short
  lines without changing its wording. Review the same source on both the dark
  and default canvases; the restrained pastel role palette must remain legible
  on each.
- Use only the owner-selected Primary Region in project diagrams. A recommendation
  remains unresolved until the owner confirms it; never choose or render a default.
- Avoid experimental Mermaid syntax, external icon packs, custom JavaScript, and renderer-specific layout hacks.

### Connect relationships to the actual component

- Every arrow starts at the canonical component producing the request, event, data, signal, or decision and ends at the canonical component receiving it.
- Show every participating service as an explicit hop: visitor to CloudFront to S3, or API Gateway to Lambda to DynamoDB.
- Never draw one arrow through, behind, or across a participating service box. End the incoming relationship at that service and begin the next relationship from it.
- A cloud, Region, environment, trust, or functional boundary is containment, not an endpoint, unless the canonical design explicitly defines that boundary as the target.
- Never connect to a subgraph title, empty container area, nearby component, or generic stack box when a specific receiving service is known.
- Dashed trust, telemetry, control, and planning relationships follow the same endpoint rule.
- If the correct source, destination, or intermediate hop is unknown, leave the relationship unresolved instead of guessing.

- Use the canonical ID only as the Mermaid node identifier. The quoted label names the real project element and never repeats the ID.
- Use `flowchart TB` for the complete architecture and AWS implementation views. Group layers in two or more labeled subgraphs and keep the main outcome path visually central.
- Give every relationship a short verb phrase. Put detail in focused diagrams rather than making the complete view unreadably wide or dense.
- Keep labels concise, avoid unexplained abbreviations, and add one `accTitle` and one `accDescr` that explain the diagram without relying on color or position.
- Render the result before Gate B. Correct crossed paths, uneven groups, crowded labels, and excessive detail while preserving the canonical endpoints and relationships.

## Complete architecture pattern

Use the section-14 view for the selected architecture, real actors, trust and
data boundaries, selected AWS capabilities, observability, and recovery.

```mermaid
%%{init: {"flowchart": {"curve": "linear", "nodeSpacing": 24, "rankSpacing": 120, "subGraphTitleMargin": {"top": 8, "bottom": 16}}, "themeVariables": {"fontSize": "16px"}}}%%
flowchart TB
    accTitle: Complete proposed application architecture
    accDescr: The customer enters through the public interface, the application applies identity and business rules, and managed data, operations, and recovery services support the outcome.
    ACT-000["Invited project customer"]:::actor
    subgraph CLOUD["Cloud platform · proposed architecture"]
        subgraph REGION["Selected Region or environment"]
            subgraph ENTRY["Managed public entry"]
                API-000["Secure application interface"]:::compute
            end
            subgraph APPLICATION["Application · trust boundary"]
                BOUNDARY-000["Authenticated application boundary"]:::entry
                ARCH-0000["Project application"]:::compute
            end
            subgraph OPERATIONS["Data and operations"]
                TECH-0004[("Selected owner data service")]:::data
                TECH-0005["Selected recovery mechanism"]:::ops
            end
        end
    end
    %% Primary request and data path
    ACT-000 -->|uses| API-000
    API-000 -->|enters through| BOUNDARY-000
    BOUNDARY-000 -->|invokes| ARCH-0000
    ARCH-0000 -->|stores approved records in| TECH-0004
    %% Recovery path
    TECH-0005 -. "restores" .-> ARCH-0000
    classDef actor fill:#FFFFFF,stroke:#232F3E,color:#232F3E,stroke-width:2px;
    classDef entry fill:#EAF3FF,stroke:#147EBA,color:#232F3E;
    classDef compute fill:#FFF1E8,stroke:#D86613,color:#232F3E;
    classDef data fill:#EDF7ED,stroke:#248814,color:#232F3E;
    classDef ops fill:#FFF7DF,stroke:#D38B00,color:#232F3E;
```

## AWS implementation pattern

Use the section-20 table to retain all eight validated AWS concerns. Show only
applicable selected services and mechanisms in the diagram; do not reproduce an AWS catalog or draw a non-applicable path.

```mermaid
%%{init: {"flowchart": {"curve": "linear", "nodeSpacing": 24, "rankSpacing": 120, "subGraphTitleMargin": {"top": 8, "bottom": 16}}, "themeVariables": {"fontSize": "16px"}}}%%
flowchart TB
    accTitle: Proposed AWS implementation
    accDescr: Requests enter through the selected AWS edge and identity services, run through the application compute and data path, and are supported by messaging, observability, deployment, and encryption controls.
    subgraph AWS_CLOUD["AWS Cloud · proposed implementation"]
        subgraph REGION["Selected AWS Region"]
            subgraph ENTRY["Managed entry and identity"]
                TECH-0002["Selected API and edge service"]:::entry
                TECH-0003["Selected identity service"]:::entry
            end
            subgraph APPLICATION["Application · compute"]
                TECH-0001["Selected application runtime"]:::compute
                ARCH-0000["Project application"]:::compute
            end
            subgraph DATA["Data and coordination"]
                TECH-0004[("Selected data service")]:::data
                TECH-0005["Selected messaging mechanism"]:::event
            end
            subgraph OPERATE["Operations and safeguards"]
                TECH-0006["Selected observability service"]:::ops
                TECH-0007["Selected deployment mechanism"]:::ops
                TECH-0008["Selected encryption and secrets controls"]:::event
            end
        end
    end
    %% Primary request and data path
    TECH-0003 -. "provides token issuer trust to" .-> TECH-0002
    TECH-0002 -->|routes requests to| TECH-0001
    TECH-0001 -->|implements| ARCH-0000
    ARCH-0000 -->|reads and writes| TECH-0004
    ARCH-0000 -->|coordinates through| TECH-0005
    %% Telemetry, delivery, and protection
    ARCH-0000 -. "emits operational signals to" .-> TECH-0006
    TECH-0007 -. "delivers and rolls back" .-> TECH-0001
    TECH-0008 -. "protects" .-> ARCH-0000
    classDef entry fill:#EAF3FF,stroke:#147EBA,color:#232F3E;
    classDef compute fill:#FFF1E8,stroke:#D86613,color:#232F3E;
    classDef data fill:#EDF7ED,stroke:#248814,color:#232F3E;
    classDef event fill:#F3ECFF,stroke:#8C4FFF,color:#232F3E;
    classDef ops fill:#FFF7DF,stroke:#D38B00,color:#232F3E;
```

## Focused views

- `PRIMARY_OUTCOME` shows the shortest approved end-to-end owner outcome.
- `JOURNEY` shows material actors, alternate paths, and rich-use-case behavior.
- `STATE` uses compact canonical state-model cards and only the exact recorded
  transitions. Never paste a whole register into one giant label or invent a
  self-loop merely to make the diagram nonempty. If the exact transition model
  cannot be shown cleanly with current canonical endpoints, keep the State
  register authoritative and leave the conditional diagram not yet created.
- `DATA_LIFECYCLE` shows ownership, retention, deletion, backup, and recovery movement.
- `FAILURE_RECOVERY` shows the material failure, bounded retry, rollback, and recovery path.
- `MIGRATION` shows the preserved source, bounded transition, validation point, and rollback target.

```mermaid
%%{init: {"flowchart": {"curve": "linear", "nodeSpacing": 24, "rankSpacing": 120, "subGraphTitleMargin": {"top": 8, "bottom": 16}}, "themeVariables": {"fontSize": "16px"}}}%%
flowchart LR
    accTitle: Customer journey with a safe alternate path
    accDescr: The invited customer submits one request and receives the validated result, while a recoverable failure follows the selected recovery path before returning to the interface.
    ACT-000["Invited customer"]
    API-000["Customer request interface"]
    TECH-0005["Selected recovery mechanism"]
    ACT-000 -->|submits the request to| API-000
    API-000 -->|returns the validated result to| ACT-000
    API-000 -. "uses the recovery path" .-> TECH-0005
    TECH-0005 -. "returns to" .-> API-000
```

```mermaid
%%{init: {"flowchart": {"curve": "linear", "nodeSpacing": 24, "rankSpacing": 120, "subGraphTitleMargin": {"top": 8, "bottom": 16}}, "themeVariables": {"fontSize": "16px"}}}%%
flowchart TB
    accTitle: Compact project state flow
    accDescr: The application points to one canonical state-model card whose relationship names the exact validation and publication transitions recorded in the State register.
    ARCH-0000["Project application"]:::compute
    STATE-000["DRAFT<br/>VALIDATED<br/>PUBLISHED"]:::event
    ARCH-0000 -->|permits DRAFT to VALIDATED<br/>and VALIDATED to PUBLISHED| STATE-000
    classDef compute fill:#FFF1E8,stroke:#D86613,color:#232F3E;
    classDef event fill:#F3ECFF,stroke:#8C4FFF,color:#232F3E;
```

Every focused view follows the same human-label, relationship-label,
accessibility, and rendered-review rules. Never imply that a planned diagram was
deployed or observed. Moving an unchanged Mermaid block preserves its semantic
and presentation-source digests. Changing labels or group names updates the
presentation fingerprint without changing the architecture. Moving components
across containment groups or changing endpoints, edge kinds, or relationships
is a semantic design change.
