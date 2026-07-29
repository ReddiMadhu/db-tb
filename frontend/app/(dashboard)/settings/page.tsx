"use client";

import { useState } from "react";
import { Save } from "lucide-react";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import { useToast } from "@/components/ui/ToastProvider";
import styles from "./Settings.module.css";

export default function SettingsPage() {
  const { success } = useToast();
  const [provider, setProvider] = useState(() => {
    if (typeof window !== "undefined") return localStorage.getItem("lakeview_llm_provider") || "azure";
    return "azure";
  });
  const [apiKey, setApiKey] = useState(() => {
    if (typeof window !== "undefined") return localStorage.getItem("lakeview_api_key") || "";
    return "";
  });
  const [azureEndpoint, setAzureEndpoint] = useState(() => {
    if (typeof window !== "undefined") return localStorage.getItem("lakeview_azure_endpoint") || "";
    return "";
  });
  const [azureDeployment, setAzureDeployment] = useState(() => {
    if (typeof window !== "undefined") return localStorage.getItem("lakeview_azure_deployment") || "gpt-4o";
    return "gpt-4o";
  });
  const [azureApiVersion, setAzureApiVersion] = useState(() => {
    if (typeof window !== "undefined") return localStorage.getItem("lakeview_azure_version") || "2024-02-15-preview";
    return "2024-02-15-preview";
  });
  const [saving, setSaving] = useState(false);

  const handleSave = () => {
    setSaving(true);
    setTimeout(() => {
      localStorage.setItem("lakeview_llm_provider", provider);
      localStorage.setItem("lakeview_api_key", apiKey);
      localStorage.setItem("lakeview_azure_endpoint", azureEndpoint);
      localStorage.setItem("lakeview_azure_deployment", azureDeployment);
      localStorage.setItem("lakeview_azure_version", azureApiVersion);
      setSaving(false);
      success("Platform & Azure AI configuration saved successfully!", "Settings Saved");
    }, 600);
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

        <Button
          variant="primary"
          isLoading={saving}
          loadingText="Saving..."
          icon={<Save size={16} />}
          onClick={handleSave}
        >
          Save Settings
        </Button>
      </div>

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
