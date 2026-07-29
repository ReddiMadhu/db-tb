# Phase 18: Enterprise Architecture

This document outlines the enterprise architecture for the Tableau to Databricks Lakeview Migration Platform, ensuring scalability, reliability, and security for large-scale BI modernization initiatives.

## 1. System Architecture

The migration platform is designed as a scalable microservices-based system.

### 1.1 High-Level Architecture Diagram

```mermaid
graph TD
    %% Define Layers
    subgraph Client Layer
        WebUI[React/Next.js Web App]
        CLI[Migration CLI]
        APIClient[REST API Client]
    end

    subgraph API Gateway Layer
        AG[FastAPI Gateway]
        AG --> Auth[Auth / OIDC]
        AG --> RL[Rate Limiting]
    end

    subgraph Service Layer (Microservices)
        PS[Parser Service]
        CS[Compiler Service]
        GS[Generator Service]
        VS[Validation Service]
        DS[Deployment Service]
        DiffS[Diff Service]
        AIS[AI Service]
    end

    subgraph Data Layer
        PG[(PostgreSQL<br>Metadata)]
        Redis[(Redis<br>Queue/Cache)]
        S3[(S3/Blob<br>Artifacts)]
        ES[(Elasticsearch<br>Logs)]
    end

    subgraph Databricks Environment
        Workspace[Databricks Workspace]
        Lakeview[Lakeview Dashboards]
        SQLW[SQL Warehouse]
    end

    %% Connections
    WebUI --> AG
    CLI --> AG
    APIClient --> AG

    AG --> PS
    AG --> CS
    AG --> GS
    AG --> VS
    AG --> DS
    AG --> DiffS
    AG --> AIS

    PS <--> S3
    CS <--> PG
    GS <--> S3
    DS --> Workspace
    DS --> Lakeview
    DS --> SQLW

    PS --> Redis
    CS --> Redis
    GS --> Redis
    
    %% Logs
    PS -.-> ES
    CS -.-> ES
    GS -.-> ES
```

### 1.2 Frontend Layer
*   **Technology Stack**: React, Next.js, Tailwind CSS
*   **Components**:
    *   **Dashboard**: Upload Tableau workbooks (.twb/.twbx), monitor batch migration progress, view overall success rates.
    *   **Migration Wizard**: Step-by-step configuration for workspace mapping, data source substitution, and semantic model definitions.
    *   **Diff Viewer**: Side-by-side visual comparison of the original Tableau layout and the generated Lakeview layout.
    *   **Report Viewer**: Detailed migration report highlighting translation issues, unsupported functions, and suggested manual interventions.

### 1.3 API Gateway
*   **Technology Stack**: FastAPI (Python), Uvicorn
*   **Responsibilities**:
    *   REST API routing for migration operations.
    *   WebSocket connections for real-time job progress updates.
    *   Authentication and Authorization (OAuth2 / OIDC).
    *   Rate limiting and payload validation.

### 1.4 Service Layer (Microservices)
The core processing is divided into stateless, horizontally scalable microservices.

1.  **Parser Service**: Accepts `.twb` (XML) or `.twbx` (Zip archive), extracts components, and returns the parsed Tableau Object Model (TOM).
2.  **Compiler Service**: Accepts TOM, executes the multi-pass compilation (Expression Translation, AST manipulation, SQL generation), and returns the Universal BI Model (UBI).
3.  **Generator Service**: Accepts UBI Model, maps components to Lakeview widget types, and generates the final `.lvdash.json` Databricks Asset Bundle definition.
4.  **Validation Service**: Validates the generated JSON schema against the Lakeview API specifications and performs dry-run validations.
5.  **Deployment Service**: Authenticates with Databricks Workspace via OAuth or PAT, deploys the dashboard, creates datasets, and returns deployment status.
6.  **Diff Service**: Computes structural and visual diffs between existing BI assets and the new Lakeview dashboard.
7.  **AI Service**: Provides LLM-assisted translation for highly complex LOD expressions or custom SQL that fails standard compilation.

### 1.5 Data Layer
*   **PostgreSQL**: Relational storage for migration metadata, job history, user configurations, and workspace mapping definitions.
*   **Redis**: In-memory data structure store used for job queuing (Celery/RQ), caching, and session state.
*   **S3/Azure Blob Storage**: Object storage for uploaded `.twb`/`.twbx` files, temporary intermediate models (TOM/UBI), and generated `.lvdash.json` artifacts.
*   **Elasticsearch (ELK Stack)**: Centralized logging for migration events, errors, and audit trails.

### 1.6 Infrastructure & Deployment
*   **Kubernetes (K8s)**: Container orchestration using Helm charts for declarative deployments.
*   **Docker**: Containerized deployment for each microservice.
*   **HPA (Horizontal Pod Autoscaler)**: Automatic scaling of Parser and Compiler services based on CPU/Queue metrics during bulk migrations.
*   **Observability**:
    *   **Monitoring**: Prometheus metrics + Grafana dashboards.
    *   **Logging**: FluentBit -> Elasticsearch -> Kibana.
    *   **Tracing**: OpenTelemetry / Jaeger for distributed request tracing.

---

## 2. Scalability Design

To handle enterprise-scale migrations (1000+ workbooks), the system implements the following patterns:

*   **Stateless Services**: All microservices maintain no internal state, allowing Kubernetes to spin up multiple replicas seamlessly.
*   **Asynchronous Job Processing**: The API Gateway offloads heavy parsing and compilation tasks to Redis-backed queues processed by worker pools.
*   **Batch Processing**: Endpoints support bulk upload, scheduling migrations during off-peak hours to manage load on source and target systems.
*   **Multi-Tenancy**: Tenant isolation at the database layer (Row-Level Security) and dedicated object storage prefixes to serve multiple organizational units securely.

---

## 3. Disaster Recovery

*   **Database Backups**: Automated daily snapshots of PostgreSQL with Point-In-Time-Recovery (PITR) up to 7 days.
*   **Cross-Region Replication**: Critical metadata and S3 buckets are replicated to a secondary region.
*   **Stateless Recovery**: Complete platform redeployment from GitOps (ArgoCD) takes < 15 minutes.
*   **Data Retention Policies**: Uploaded `.twb` files are purged after 30 days. PII is never stored permanently.

---

## 4. API Design (REST)

```yaml
openapi: 3.0.0
info:
  title: Migration Platform API
  version: v1
paths:
  /api/v1/migrations:
    post:
      summary: Upload workbook and start migration
      requestBody:
        content:
          multipart/form-data:
            schema:
              type: object
              properties:
                file:
                  type: string
                  format: binary
                targetWorkspaceId:
                  type: string
      responses:
        '202':
          description: Migration job accepted
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/JobReference'

  /api/v1/migrations/{id}:
    get:
      summary: Get migration status
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Status returned (Pending, Processing, Completed, Failed)

  /api/v1/migrations/{id}/report:
    get:
      summary: Get detailed migration report
      responses:
        '200':
          description: Report with success rate, warnings, and errors.

  /api/v1/migrations/{id}/deploy:
    post:
      summary: Deploy generated dashboard to Databricks
      requestBody:
        content:
          application/json:
            schema:
              properties:
                folderPath:
                  type: string
      responses:
        '200':
          description: Deployment successful

  /api/v1/migrations/{id}/diff:
    get:
      summary: Get diff report
      responses:
        '200':
          description: Structural diff JSON

  /api/v1/migrations/{id}:
    delete:
      summary: Cancel job or delete artifacts
      responses:
        '204':
          description: Successfully deleted
```
