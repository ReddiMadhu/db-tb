# Diff Engine Design

## Overview
The Diff Engine supports incremental deployment by computing the minimal structural difference between a remote Databricks dashboard (the base) and a locally generated dashboard definition (the remote). It generates an update payload for the API `PATCH` method to avoid destructive `DELETE`/`CREATE` cycles.

## Problem Statement
When a dashboard is updated via complete overwrite, the entity ID changes. This breaks:
- Permissions/ACLs.
- Existing schedules and alerts.
- Subscription lists.
- Published states and URLs.
Using the `PATCH` API preserves the entity ID and its associated metadata.

## Architecture

```mermaid
graph TD
    API[GET /api/2.0/lakeview/dashboards/{id}] --> Base[Base Dashboard JSON]
    Local[Local File/Generator] --> Target[Target Dashboard JSON]
    Base --> DiffEngine[Diff Engine]
    Target --> DiffEngine
    DiffEngine --> DiffReport[Diff Report]
    DiffEngine --> PatchPayload[PATCH JSON Payload]
    DiffEngine --> MigrationCLI[Migration Script]
```

## Diff Algorithm
The dashboard JSON is a complex graph. The diff engine performs a hierarchical tree-diff.

### 1. Dataset-level Diff
- Identify datasets by `name` or ID.
- Determine Added, Removed, or Modified datasets (SQL query changes).

### 2. Page-level Diff
- Identify pages by `name` or internal ID.
- Detect reordering, additions, and deletions.

### 3. Widget-level Diff
- Matched by widget `id` or structural heuristic if ID is missing.
- Detect added, removed, and modified widgets.

### 4. Position-level Diff
- Detect changes in `x`, `y`, `width`, `height`.

### 5. Spec & Query Diff
- Detect changes in JSON specs (e.g., visualization configurations, encodings).
- Compare normalized SQL queries (ignoring whitespace).

## Conflict Resolution
- **Optimistic Locking**: Utilize the `etag` returned by the `GET` API. The `PATCH` request must include this `etag`. If the server's `etag` has changed, a conflict is detected.
- **Three-Way Merge**: If concurrent edits occurred, perform a 3-way merge (Base, Local, Remote server state) to flag conflicts.

## Output Types

### 1. Diff Report
A human-readable JSON or text report detailing exact changes.
```json
{
  "entity_id": "dashboard_abc123",
  "changes": [
    {
      "type": "modified",
      "path": "pages[0].widgets[1].position.width",
      "before": 2,
      "after": 4
    }
  ]
}
```

### 2. Patch Payload
The minimal JSON required by the API.

### 3. Migration Script
CLI commands to apply changes, useful for auditing or CI/CD debugging.
