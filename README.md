# Tableau to Databricks Migration Engine

Automated migration suite for converting Tableau Workbooks (`.twb`/`.twbx`) into Databricks Lakeview dashboards (`.lvdash.json`).

## Documentation

All documentation, architecture specifications, design guides, and process manifests have been consolidated into the [`docs/`](docs/) directory:

- **Architecture & System Design**: See [`docs/01_architecture.md`](docs/01_architecture.md) & [`docs/P23_enterprise_architecture.md`](docs/P23_enterprise_architecture.md)
- **REST API Reference**: See [`docs/02_rest_api_reference.md`](docs/02_rest_api_reference.md)
- **Tableau Mapping & Translation Guides**: See [`docs/11_tableau_mapping_guide.md`](docs/11_tableau_mapping_guide.md) & [`docs/P08_tableau_function_mapping.md`](docs/P08_tableau_function_mapping.md)
- **Frontend Documentation**: See [`docs/frontend_README.md`](docs/frontend_README.md)
**Updated Data Flow (matches the new diagram)**

1. **Front end:** Users open the application in a browser and sign in with Microsoft Entra ID SSO. Requests pass through the App Gateway to the React front end, served as build files from a Databricks App. Users upload the required input files here.

2. **Backend:** The React app calls the FastAPI backend, hosted as a Databricks App, over secure REST APIs. The backend securely scans, analyzes, and categorizes the files using Python libraries and GenAI models, then saves the data in PostgreSQL (knowledge layer). When the user starts an agent, the app:
   - connects to the Databricks platform through the Databricks SDK;
   - retrieves governed data through Unity Catalog;
   - reads secrets and environment keys from Databricks Secrets;
   - runs the agentic workflow step by step, saving each stage's output back to the database;
   - writes logs and audit data to Databricks System Tables.

3. **GenAI:** Intermediate results, with sensitive information anonymized, are sent to Azure AI Foundry (Azure OpenAI models). The models generate plain-English summaries and extract key semantic elements and roles. The processed results are streamed back to the user interface, giving a live view of the agentic workflow and its outputs.

4. **Deployment:** Azure DevOps CI/CD pipelines build and deploy the front-end and backend code to the Databricks Apps.

**A1) Planned for Production environment:** Authentication uses Microsoft Entra ID SSO, with user identity and roles taken from the Entra ID token. JWT tokens are used for authorization, enabling secure, stateless access control across APIs.

**A2) Planned for Production environment:** API security is implemented using JWT validation along with rate limiting to prevent misuse. All communication is secured over HTTPS using TLS encryption. Network security is strengthened using best practices like API gateways, firewall rules, and private network isolation.

**Changes and things to check**
- The old A1 said email and password authentication with hashed passwords. The diagram now shows Entra ID SSO, so I replaced it. If you still store local users, keep the old wording.
- I fixed "senstive" and changed "Azure Model (Managed Services)" to "Azure AI Foundry (Azure OpenAI)".
- I changed "VPC-based isolation" to "private network isolation", since you are on Azure.
- On the slide, the Azure CI/CD arrow ends inside the backend box and doesn't clearly point at the Databricks App. Extend it to the app icon. Since the front end is also a Databricks App, you could add a second arrow to it.
Here is a professional, business-focused workflow structured for stakeholders and product owners:

---

### **Executive Summary: End-to-End SAS to PySpark Migration & Verification Workflow**

A governed, automated migration pipeline that translates legacy SAS workflows to modern Databricks PySpark workloads with human-in-the-loop oversight, automated error recovery, and deterministic output reconciliation.

---

### **Business Workflow & Lifecycle**

* **1. Ingestion & Environment Configuration**
  * The user provides the source SAS script along with the designated Databricks input and output storage paths.
  * The workbench registers the migration scope and prepares the target execution environment.

* **2. Automated PySpark Code Generation**
  * The migration engine analyzes the business logic and automatically generates equivalent PySpark code tailored for Databricks.

* **3. Human Review & Execution Approval (Governance Gate)**
  * The generated PySpark code is presented to the user for quality review.
  * **Gate:** No code is executed without explicit user authorization, ensuring complete compliance and control.

* **4. Managed Execution & Self-Healing Loop**
  * Upon approval, the workbench submits and monitors the job execution directly in Databricks.
  * **Success:** Execution metrics and logs are captured, and the workflow advances to verification.
  * **Failure / Error Recovery Loop:** If a runtime or syntax error occurs:
    * Error diagnostics are captured and fed back into the code generation engine.
    * The engine remediates the issue and produces a corrected PySpark script.
    * The updated code is re-submitted for review and execution until successful.

* **5. Automated Output Reconciliation & Comparison**
  * Once the PySpark job completes successfully, the system automatically formulates comparison routines to evaluate:
    * Baseline outputs produced by the original SAS process.
    * New target outputs generated by the PySpark job.

* **6. Parity Verification & Acceptance Loop**
  * The engine executes automated parity checks (row counts, schema alignment, data distributions, and value matching).
  * **Success:** A certified parity report is generated, marking the migration unit complete.
  * **Discrepancy Remediation Loop:** If data variances exceed acceptable tolerances:
    * Discrepancies are flagged for analysis.
    * Transformation logic is refined and re-tested through the cycle until full data parity is achieved and certified.

---

### **Key Business Value Highlights**
* **Risk Mitigation:** Human-in-the-loop checkpoints prevent unvetted code from running in production or staging clusters.
* **Accelerated Time-to-Value:** Automated self-healing loops resolve execution issues without manual debugging.
* **Guaranteed Data Integrity:** Mathematical and logical parity checks ensure the modern PySpark solution produces identical results to legacy SAS systems.
