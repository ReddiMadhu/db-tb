# Phase 18: Production Readiness Checklist

This checklist ensures the Tableau to Databricks Lakeview Migration Platform is fully verified, secure, and operational before enterprise launch.

## 1. Pre-Launch Checklist

### 1.1 Development & Testing
- [x] All Phase 1-18 components implemented.
- [ ] 95%+ unit test coverage achieved across Parser, Compiler, and Generator services.
- [ ] Integration tests passing against real Databricks workspace (via Databricks REST API / Asset Bundles).
- [ ] Golden file tests validated for all supported visualization types (Bar, Line, Scatter, Pie, Tables).
- [ ] Edge cases tested (e.g., nested LODs, complex table calculations, missing metadata).

### 1.2 Security & Compliance
- [ ] Internal security audit completed (code scan, dependency check).
- [ ] Penetration testing on API Gateway completed.
- [ ] OAuth2 / OIDC authentication flow verified in production-like environment.
- [ ] Databricks Service Principal / PAT management tested and secure.
- [ ] Role-Based Access Control (RBAC) rules enforced correctly.
- [ ] Compliance review completed (SOC 2 / GDPR requirements addressed regarding PII/data handling).

### 1.3 Operations & SRE
- [ ] Performance benchmarks documented (throughput per CPU core).
- [ ] Load testing completed (Simulate 100 concurrent dashboard migration requests).
- [ ] Kubernetes Helm charts configured for production (HPA tuned).
- [ ] Monitoring dashboards (Grafana) configured (Service latency, Error rates, Queue length).
- [ ] Alerting configured (PagerDuty/Slack integration for critical failures).
- [ ] Disaster recovery tested (Database backup restoration verified).
- [ ] Rollback procedures tested (Reverting an API/Service deployment).
- [ ] Runbooks created and distributed to the operations team.

### 1.4 Documentation
- [ ] User Guide (How to migrate a workbook).
- [ ] Architecture Documentation finalized.
- [ ] API Swagger / OpenAPI documentation published.

---

## 2. Success Criteria & SLAs

| Metric | Target | Measurement Method |
| :--- | :--- | :--- |
| **Visualization Migration Accuracy** | > 90% | Automated Golden File Diff / Visual QA |
| **SQL Translation Accuracy** | > 95% | Semantic equivalence testing against DB SQL |
| **Layout Fidelity** | > 85% | Structural JSON comparison |
| **Migration Speed (per workbook)** | < 30 seconds | System telemetry (P95 latency) |
| **API Availability** | 99.9% | Uptime monitoring (e.g., Datadog) |
| **Supported Tableau Versions** | 2018.x - 2024.x | XML parsing test matrix |
| **Function Coverage** | > 95% | Internal function mapping table coverage |

---

## 3. Operational Runbooks

### 3.1 Migration Failure Investigation
**Symptom**: User reports a failed migration or HTTP 500 error.
**Action**:
1. Obtain the `Job ID` from the user.
2. Query Elasticsearch / Kibana using `trace_id: <Job ID>`.
3. Identify the failing microservice (Parser, Compiler, or Generator).
4. Review the stack trace. If it's an unsupported Tableau feature, update the mappings configuration or route to the AI Fallback Service.

### 3.2 Dashboard Deployment Rollback
**Symptom**: A deployed dashboard in Databricks breaks due to bad SQL generation.
**Action**:
1. The deployment is GitOps controlled.
2. Go to the GitHub / ADO repository containing the dashboard artifacts.
3. Locate the faulty PR or commit.
4. Issue `git revert <commit-hash>` and push.
5. The CI/CD pipeline will automatically run `databricks bundle deploy` with the previous known-good state.

### 3.3 Token Rotation (Service Principal)
**Symptom**: Databricks OAuth token expires or is compromised.
**Action**:
1. Generate a new secret for the Service Principal in Databricks Account Console.
2. Update the vault/secret manager (e.g., Azure Key Vault).
3. Restart the `Deployment Service` pods to fetch the new token.

### 3.4 Service Scaling (Handling Batch Migrations)
**Symptom**: Queue size (Redis) exceeds 500 pending jobs.
**Action**:
1. Check HPA status: `kubectl get hpa`.
2. If max replicas reached, temporarily increase max replicas: `kubectl patch hpa compiler-service -p '{"spec":{"maxReplicas": 20}}'`.
3. Ensure the underlying node pool has autoscaling enabled to provision new VMs.

### 3.5 Incident Response
**Severity 1 (System Down)**: 
* Trigger PagerDuty for Platform Engineering.
* Rollback last Helm release if recent deployment caused outage.
* Check API Gateway logs for DDoS or auth failures.
