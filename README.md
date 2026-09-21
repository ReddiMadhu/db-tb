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