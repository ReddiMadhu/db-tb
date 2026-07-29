# Browser Reverse Engineering Guide

As no live workspace is available, this guide outlines the methodology for capturing and analyzing Lakeview API traffic using browser DevTools.

## Setup & Capture
1. **DevTools Setup**: Open Network tab in browser Developer Tools (F12). Ensure "Preserve log" is checked. Filter by `Fetch/XHR`.
2. **HAR Export**: Right-click in the Network tab and select "Save all as HAR with content" to capture a session.

## Expected Endpoints & Payloads
- **Create dashboard**: `POST /api/2.0/workspace/custom-dashboards` (Expects basic metadata).
- **Add widget/dataset & Save**: `PATCH /api/2.0/workspace/custom-dashboards/{id}` (Expects full or partial `serialized_dashboard` JSON).
- **Publish**: `POST /api/2.0/workspace/custom-dashboards/{id}/published`.
- **Run SQL**: Look for endpoints executing dataset queries (e.g., `/api/2.0/sql/statements` or specialized internal endpoints).
- **Delete**: `DELETE /api/2.0/workspace/custom-dashboards/{id}`.
- **Duplicate**: `POST /api/2.0/workspace/custom-dashboards/{id}/clone` (or similar).
- **Import**: `POST /api/2.0/workspace/custom-dashboards/import` (or via standard workspace API).
- **Export**: `GET /api/2.0/workspace/custom-dashboards/{id}/export`.

## Protocols & Authentication
- **Authentication**: Look for `Bearer <token>` in the `Authorization` header.
- **GraphQL**: Check for POST requests to `/api/graphql` or similar. Usually contains `query` and `variables` JSON payload.
- **WebSockets**: Check the "WS" tab in DevTools for real-time collaboration or query status streams.
- **Network timing analysis**: Observe waterfall charts to identify synchronous versus asynchronous API calls and background polling mechanisms.

## State Inspection
- **IndexedDB**: Check Application tab > IndexedDB for local caching of dashboard state, schema, or query results.
- **LocalStorage**: Look for session keys, UI preferences, or draft auto-saves.
- **Cookies**: Analyze cookies for Databricks session tokens and routing information.

## Dashboard Serialization Capture
To capture the full `serialized_dashboard`:
- Perform a minor edit (like moving a widget).
- Observe the resulting `PATCH` request in the Network tab.
- Copy the request payload. The `serialized_dashboard` string is usually stringified JSON, which needs parsing for deep analysis.

## Documentation Template
When traffic is captured, document using this format:
- **Operation**: e.g., Save Dashboard
- **URL**: `...`
- **Method**: `PATCH`
- **Headers**: `...`
- **Payload**: `...`
- **Response**: `...`
