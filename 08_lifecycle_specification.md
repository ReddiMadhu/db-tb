# Dashboard Lifecycle Specification

## State Management
- **Draft state**: [Verified] The default state after a dashboard is created or updated.
- **Autosave**: [Observed] A UI-only behavior. The API requires explicit `PATCH` requests to save changes.
- **Optimistic locking**: [Verified] Implemented via the `etag` field on `GET` responses, and is optional on `PATCH` requests.
- **Version history**: [Verified] Only maintains draft vs. published states. No numbered historical versions are kept.

## Publishing & Operations
- **Publish**: [Verified] `POST .../published` payload includes `embed_credentials` and `warehouse_id`.
- **Unpublish**: [Verified] `DELETE .../published` (The draft version is retained).
- **Revert**: [Verified] `POST .../revert` (Resets the current draft to match the last published version).
- **Trash**: [Verified] `DELETE .../dashboards/{id}` results in a soft delete, transitioning to `lifecycle_state=TRASHED`.

## Storage & Access
- **Workspace storage**: [Verified] Dashboards are stored in the TreeStore as `.lvdash.json` files.
- **Folders**: [Verified] `parent_path` specifies the containing folder within the workspace.
- **Ownership**: [Verified] The creator acts as the owner.
- **Permissions**: [Verified] Role-based access control includes `CAN_VIEW`, `CAN_RUN`, `CAN_EDIT`, and `CAN_MANAGE`.
- **Sharing**: [Verified] Managed via the standard Databricks permissions API.

## Integrations
- **Scheduling**: [Verified] Supported via `CronSchedule` using quartz expressions.
- **Subscriptions**: [Verified] Email notifications can be configured for scheduled runs.
- **Embedding**: [Verified] Published dashboards can be embedded in external apps via iframe.
- **Import/Export**: [Verified] Supported via the workspace API or using the `databricks bundle generate` CLI command.

## Terraform Lifecycle
- [Verified from provider source] Typical flow: `create` → auto-publish (if configured) → `read` with etag drift detection → `update` → re-publish → `trash` on destroy.
