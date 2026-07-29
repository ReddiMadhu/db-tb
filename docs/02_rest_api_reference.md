# Databricks Lakeview (AI/BI Dashboards) REST API Reference

This document provides a comprehensive REST API reference for Databricks Lakeview (AI/BI Dashboards), including dashboard CRUD, publishing, scheduling, embedding, workspace operations, and permissions.

> **Evidence Levels:**
> - `[Verified]`: Confirmed via SDK source code or official documentation.
> - `[Observed]`: Seen in network traffic or live API responses.
> - `[Inferred]`: Deduced based on standard Databricks API patterns.

---

## Authentication [Verified]

All endpoints require standard Databricks authentication.

- **Bearer token**: Personal Access Token (PAT) or OAuth.
- **Header**: `Authorization: Bearer <token>`
- **Optional Header**: `X-Databricks-Workspace-Id` (useful for multi-workspace integrations).
- **Content-Type**: `application/json` (for POST/PUT/PATCH requests).
- **Accept**: `application/json`

---

## Dashboard Object Schema [Verified]

When a dashboard is returned by the API (except in list endpoints where fields might be omitted), it conforms to the following schema:

```json
{
  "dashboard_id": "string (UUID)",
  "display_name": "string",
  "create_time": "string (ISO 8601)",
  "update_time": "string (ISO 8601)",
  "lifecycle_state": "ACTIVE | TRASHED",
  "parent_path": "string",
  "path": "string (ends in .lvdash.json)",
  "serialized_dashboard": "string (JSON string)",
  "warehouse_id": "string",
  "etag": "string"
}
```

---

## Endpoints

### 1. Dashboard CRUD

#### 1.1 Create Dashboard [Verified]
Creates a new Lakeview dashboard.

- **URL:** `POST /api/2.0/lakeview/dashboards`
- **Query Parameters:**
  - `dataset_catalog` (string, optional)
  - `dataset_schema` (string, optional)
- **Request Body:**
  ```json
  {
    "display_name": "string",
    "warehouse_id": "string",
    "serialized_dashboard": "string (JSON)",
    "parent_path": "string (optional)"
  }
  ```
- **Response:** Dashboard object.
- **Error Codes:** 400 (Bad Request), 401 (Unauthorized), 403 (Forbidden), 404 (Not Found for parent_path).

#### 1.2 Get Dashboard [Verified]
Retrieves a specific dashboard by ID.

- **URL:** `GET /api/2.0/lakeview/dashboards/{dashboard_id}`
- **Response:** Dashboard object (includes `serialized_dashboard` and `etag`).

#### 1.3 Update Dashboard [Verified]
Updates an existing dashboard. Supports optimistic locking via `etag`.

- **URL:** `PATCH /api/2.0/lakeview/dashboards/{dashboard_id}`
- **Query Parameters:**
  - `dataset_catalog` (string, optional)
  - `dataset_schema` (string, optional)
- **Request Body:** Same as Create, plus `etag`:
  ```json
  {
    "display_name": "string",
    "warehouse_id": "string",
    "serialized_dashboard": "string (JSON)",
    "parent_path": "string",
    "etag": "string (for optimistic locking)"
  }
  ```
- **Response:** Dashboard object.

#### 1.4 Trash Dashboard [Verified]
Moves a dashboard to the trash. This is a soft delete (sets `lifecycle_state` to `TRASHED`).

- **URL:** `DELETE /api/2.0/lakeview/dashboards/{dashboard_id}`
- **Response:** Empty (204 No Content or 200 OK with empty body) `[Observed]`.

#### 1.5 List Dashboards [Verified]
Lists dashboards in the workspace.

- **URL:** `GET /api/2.0/lakeview/dashboards`
- **Query Parameters:**
  - `page_size` (integer, optional)
  - `page_token` (string, optional)
  - `view` (string, optional, e.g., `DASHBOARD_VIEW_BASIC`)
- **Response:**
  ```json
  {
    "dashboards": [ ... ],
    "next_page_token": "string"
  }
  ```
  *Note:* `serialized_dashboard`, `parent_path`, `path`, and `etag` are EXCLUDED when using `DASHBOARD_VIEW_BASIC` `[Verified]`.

### 2. Publishing

#### 2.1 Publish Dashboard [Verified]
Publishes a draft dashboard.

- **URL:** `POST /api/2.0/lakeview/dashboards/{dashboard_id}/published`
- **Request Body:**
  ```json
  {
    "embed_credentials": true,
    "warehouse_id": "string (optional)"
  }
  ```
- **Response:** Published Dashboard object `[Inferred]`.

#### 2.2 Get Published Dashboard [Verified]
Retrieves the published version of a dashboard.

- **URL:** `GET /api/2.0/lakeview/dashboards/{dashboard_id}/published`
- **Response:** Dashboard object representing the published state.

#### 2.3 Unpublish Dashboard [Verified]
Removes the published version, returning it to draft-only state.

- **URL:** `DELETE /api/2.0/lakeview/dashboards/{dashboard_id}/published`
- **Response:** Empty.

### 3. Lifecycle

#### 3.1 Revert to Published [Verified]
Reverts draft changes back to the currently published state.

- **URL:** `POST /api/2.0/lakeview/dashboards/{dashboard_id}/revert`
- **Response:** Dashboard object (reverted state).

#### 3.2 Migrate Legacy Dashboard [Verified]
Migrates a legacy Databricks SQL Dashboard to a Lakeview Dashboard.

- **URL:** `POST /api/2.0/lakeview/dashboards/migrate`
- **Request Body:**
  ```json
  {
    "source_dashboard_id": "string (UUID of legacy dashboard)"
  }
  ```
- **Response:** Dashboard object (newly created Lakeview dashboard).

### 4. Scheduling [Verified]

#### 4.1 Schedule Operations
Manage automated updates/refreshes.

- **Create:** `POST /api/2.0/lakeview/dashboards/{dashboard_id}/schedules`
- **Get:** `GET /api/2.0/lakeview/dashboards/{dashboard_id}/schedules/{schedule_id}`
- **Update:** `PUT /api/2.0/lakeview/dashboards/{dashboard_id}/schedules/{schedule_id}` (or PATCH)
- **List:** `GET /api/2.0/lakeview/dashboards/{dashboard_id}/schedules`
- **Delete:** `DELETE /api/2.0/lakeview/dashboards/{dashboard_id}/schedules/{schedule_id}`

**Schedule Object Schema:**
```json
{
  "display_name": "string",
  "pause_status": "PAUSED | UNPAUSED",
  "cron_schedule": {
    "quartz_cron_expression": "string",
    "timezone_id": "string"
  }
}
```

#### 4.2 Subscription Operations
Manage email or notification subscriptions for a schedule.

- **Create:** `POST /api/2.0/lakeview/dashboards/{dashboard_id}/schedules/{schedule_id}/subscriptions`
- **List:** `GET /api/2.0/lakeview/dashboards/{dashboard_id}/schedules/{schedule_id}/subscriptions`
- **Delete:** `DELETE /api/2.0/lakeview/dashboards/{dashboard_id}/schedules/{schedule_id}/subscriptions/{subscription_id}`

### 5. Embedding

#### 5.1 Get Token Info [Verified]
Retrieves token information for embedding dashboards.

- **URL:** `GET /api/2.0/lakeview/dashboards/{dashboard_id}/published/tokeninfo`
- **Response:** Contains token details for authenticated embedding.

### 6. Workspace Operations [Verified]

Lakeview dashboards are backed by workspace files (`.lvdash.json`).

- **Export:** `GET /api/2.0/workspace/export?path=...&format=AUTO`
- **Import:** `POST /api/2.0/workspace/import`
  *(Body includes path, format, content, overwrite)*
- **Get Status:** `GET /api/2.0/workspace/get-status?path=...`

### 7. Permissions [Verified]

Standard Databricks permissions API applies to dashboards.

- **Get Permissions:** `GET /api/2.0/permissions/dashboards/{dashboard_id}`
- **Set Permissions:** `PUT /api/2.0/permissions/dashboards/{dashboard_id}` (Overwrites all)
- **Update Permissions:** `PATCH /api/2.0/permissions/dashboards/{dashboard_id}` (Modifies subset)

**Permission Levels:**
- `CAN_VIEW`: Read-only access to published dashboard.
- `CAN_RUN`: Access to refresh the dashboard `[Inferred]`.
- `CAN_EDIT`: Access to modify the draft dashboard.
- `CAN_MANAGE`: Full access including permissions and deletion.

---

## Pagination [Verified]

List endpoints use token-based pagination.
- Pass the `next_page_token` from the response as `page_token` in the next request.
- Default `page_size` varies by endpoint.

## Rate Limits [Inferred]

Standard Databricks API rate limits apply (typically limits per second/minute based on tier and endpoint classification). Handle 429 Too Many Requests with exponential backoff.
