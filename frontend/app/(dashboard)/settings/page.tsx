"use client";

import { useState, useEffect } from "react";
import { Save, CheckCircle2, Cpu, Globe, Key, Layers, Server } from "lucide-react";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import styles from "./Settings.module.css";

export default function SettingsPage() {
  const [provider, setProvider] = useState("azure");
  const [apiKey, setApiKey] = useState("");
  const [azureEndpoint, setAzureEndpoint] = useState("");
  const [azureDeployment, setAzureDeployment] = useState("gpt-4o");
  const [azureApiVersion, setAzureApiVersion] = useState("2024-02-15-preview");
  const [savedNotice, setSavedNotice] = useState(false);

  useEffect(() => {
    const savedProv = localStorage.getItem("lakeview_llm_provider");
    const savedKey = localStorage.getItem("lakeview_api_key");
    const savedEnd = localStorage.getItem("lakeview_azure_endpoint");
    const savedDep = localStorage.getItem("lakeview_azure_deployment");
    const savedVer = localStorage.getItem("lakeview_azure_version");

    if (savedProv) setProvider(savedProv);
    if (savedKey) setApiKey(savedKey);
    if (savedEnd) setAzureEndpoint(savedEnd);
    if (savedDep) setAzureDeployment(savedDep);
    if (savedVer) setAzureApiVersion(savedVer);
  }, []);

  const handleSave = () => {
    localStorage.setItem("lakeview_llm_provider", provider);
    localStorage.setItem("lakeview_api_key", apiKey);
    localStorage.setItem("lakeview_azure_endpoint", azureEndpoint);
    localStorage.setItem("lakeview_azure_deployment", azureDeployment);
    localStorage.setItem("lakeview_azure_version", azureApiVersion);
    setSavedNotice(true);
    setTimeout(() => setSavedNotice(false), 3000);
  };

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>Platform Settings</h1>
          <p className={styles.subtitle}>
            Configure Azure AI / OpenAI LLM providers, pipeline execution parameters, and target environment defaults.
          </p>
        </div>

        <Button variant="primary" icon={<Save size={16} />} onClick={handleSave}>
          Save Settings
        </Button>
      </div>

      {savedNotice && (
        <div
          style={{
            padding: "0.75rem 1.25rem",
            borderRadius: "6px",
            background: "rgba(46, 204, 113, 0.12)",
            border: "1px solid rgba(46, 204, 113, 0.3)",
            color: "var(--accent-green)",
            display: "flex",
            alignItems: "center",
            gap: "0.5rem",
            fontSize: "0.875rem",
          }}
        >
          <CheckCircle2 size={18} />
          <span>Azure AI & LLM platform settings saved successfully!</span>
        </div>
      )}

      <div className={styles.section}>
        <Card>
          <h2>LLM Compiler Fallback Configuration</h2>
          <p className={styles.desc}>
            Used for AI-assisted fallback compilations of unsupported complex Tableau expressions.
          </p>

          <div className={styles.formGroup}>
            <label className={styles.label}>LLM Provider Engine</label>
            <select
              className={styles.select}
              value={provider}
              onChange={(e) => setProvider(e.target.value)}
            >
              <option value="azure">Azure OpenAI Service (Azure AI)</option>
              <option value="openai">OpenAI Direct (GPT-4o)</option>
              <option value="anthropic">Anthropic (Claude 3.5 Sonnet)</option>
            </select>
          </div>

          {provider === "azure" && (
            <>
              <div className={styles.formGroup}>
                <label className={styles.label}>Azure OpenAI Endpoint URL</label>
                <input
                  type="text"
                  className={styles.input}
                  placeholder="https://your-resource-name.openai.azure.com/"
                  value={azureEndpoint}
                  onChange={(e) => setAzureEndpoint(e.target.value)}
                />
              </div>

              <div className={styles.formGroup}>
                <label className={styles.label}>Azure API Key</label>
                <input
                  type="password"
                  className={styles.input}
                  placeholder="Enter Azure OpenAI Key..."
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                />
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
                <div className={styles.formGroup}>
                  <label className={styles.label}>Deployment Name</label>
                  <input
                    type="text"
                    className={styles.input}
                    placeholder="gpt-4o"
                    value={azureDeployment}
                    onChange={(e) => setAzureDeployment(e.target.value)}
                  />
                </div>

                <div className={styles.formGroup}>
                  <label className={styles.label}>API Version</label>
                  <input
                    type="text"
                    className={styles.input}
                    placeholder="2024-02-15-preview"
                    value={azureApiVersion}
                    onChange={(e) => setAzureApiVersion(e.target.value)}
                  />
                </div>
              </div>
            </>
          )}

          {provider !== "azure" && (
            <div className={styles.formGroup}>
              <label className={styles.label}>API Key</label>
              <input
                type="password"
                className={styles.input}
                placeholder="sk-..."
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
              />
            </div>
          )}
        </Card>

        <Card>
          <h2>Pipeline Engine Configuration</h2>

          <div className={styles.formGroup}>
            <label className={styles.label}>Database Persistence</label>
            <input
              type="text"
              className={styles.input}
              value="sqlite:///./migrations.db (WAL Mode)"
              readOnly
            />
          </div>

          <div className={styles.formGroup}>
            <label className={styles.label}>Default Target AST Schema</label>
            <input
              type="text"
              className={styles.input}
              value="24_json_schema.json (Databricks Lakeview)"
              readOnly
            />
          </div>
        </Card>
      </div>
    </div>
  );
}
