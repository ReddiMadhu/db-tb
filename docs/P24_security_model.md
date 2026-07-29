# Phase 18: Security Model

This document outlines the security architecture and compliance models for the Tableau to Databricks Lakeview Migration Platform.

## 1. Authentication

The platform enforces strict authentication boundaries to ensure only authorized users can initiate migrations or access target Databricks workspaces.

### 1.1 Identity Provider Integration
*   **OAuth2 / OIDC**: The Web UI and API authenticate users via Enterprise Identity Providers (Azure AD, Okta, Ping Identity).
*   **SSO Integration**: Users authenticate using their corporate credentials. Tokens are validated via OIDC JWKS endpoints.

### 1.2 Databricks Authentication
*   **Service Principals**: For automated pipeline deployments, the platform uses Databricks Service Principals (OAuth M2M) rather than individual user credentials.
*   **Personal Access Tokens (PAT)**: For ad-hoc user-driven deployments, the platform accepts short-lived PATs.
*   **Token Management**:
    *   Tokens are **never** stored in plain text.
    *   Tokens are encrypted at rest in PostgreSQL using AES-256 (GCM mode).
    *   Encryption keys are managed by a Cloud KMS (Key Management Service).
    *   Strict token rotation policies are enforced (e.g., maximum 90-day lifetime).

## 2. Authorization

### 2.1 Role-Based Access Control (RBAC)

The platform defines three primary roles:

| Role | Permissions | Scope |
| :--- | :--- | :--- |
| **Platform Admin** | System config, user management, global job view | Platform-wide |
| **Migrator** | Upload workbooks, configure mappings, execute deployment | Assigned Workspaces |
| **Viewer** | View migration reports, view diffs, read-only access | Assigned Workspaces |

### 2.2 Workspace-Level Permissions
*   Users are mapped to specific Databricks Workspaces. A Migrator can only deploy assets to the workspaces they are explicitly authorized to access within the platform.

### 2.3 Dashboard-Level Permissions Mapping
*   During migration, Tableau permissions (Row-Level Security, User Filters) are mapped to Databricks Unity Catalog data access controls and Lakeview dynamic views.
*   *Note: Tableau explicit user group mapping requires pre-configuration to map Active Directory groups from Tableau to Databricks Account Groups.*

## 3. Data Security

### 3.1 Encryption in Transit
*   All communication between Client, API Gateway, Microservices, and Databricks occurs over TLS 1.2+ via HTTPS or secure WebSockets (WSS).

### 3.2 Encryption at Rest
*   **Database**: PostgreSQL databases are encrypted at the storage volume level. Sensitive columns (credentials) are application-level encrypted.
*   **Storage**: S3 / Blob Storage buckets enforce Server-Side Encryption (SSE-S3 or SSE-KMS).

### 3.3 Data Handling & PII
*   **PII Detection**: The Parser Service scans extracted data connections and parameters for potential Personally Identifiable Information (PII) and flags them in the migration report.
*   **No Data Migration**: The platform migrates **metadata** (queries, layouts, logic), not raw row-level data. TWBX embedded extracts are discarded during processing; the platform relies on Databricks Unity Catalog for data governance.
*   **Secure Credential Handling**: Tableau embedded credentials (e.g., database passwords in `.twb`) are aggressively stripped during the initial parsing phase and are never logged or stored.

### 3.4 Audit Logging
Comprehensive audit logs are maintained for:
*   Who initiated a migration.
*   Which workbook was processed.
*   Who deployed to Databricks and to which path.
*   Changes in permissions or workspace mappings.

Logs are immutable and forwarded to an enterprise SIEM (Security Information and Event Management) system.

## 4. Compliance

*   **SOC 2 Considerations**: The architecture supports SOC 2 Type II compliance through strict access controls, audit logging, and change management procedures.
*   **GDPR**: The platform minimizes data collection. User metadata can be purged upon request (Right to be Forgotten). No production BI data is persisted in the migration platform.
*   **Data Residency**: The platform can be deployed regionally to ensure artifacts (parsed workbooks) remain within geographical boundaries (e.g., EU deployment for EU data).
