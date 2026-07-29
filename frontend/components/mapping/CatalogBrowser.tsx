"use client";

import { useState, useEffect } from "react";
import { Database, Folder, Table2, Search, ChevronRight, ChevronDown, RefreshCw, Loader2 } from "lucide-react";
import { browseCatalog, searchCatalog } from "@/lib/api";
import type { CatalogItem } from "@/lib/types";
import styles from "./CatalogBrowser.module.css";

interface CatalogBrowserProps {
  host: string;
  token: string;
  selectedTable?: string;
  onSelectTable: (fullName: string) => void;
}

interface ExpandedState {
  [key: string]: boolean;
}

interface LoadedChildren {
  [key: string]: CatalogItem[];
}

export default function CatalogBrowser({
  host,
  token,
  selectedTable,
  onSelectTable,
}: CatalogBrowserProps) {
  const [search, setSearch] = useState("");
  const [catalogs, setCatalogs] = useState<CatalogItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<ExpandedState>({});
  const [children, setChildren] = useState<LoadedChildren>({});
  const [searchResults, setSearchResults] = useState<{ full_name: string; table: string; catalog: string; schema: string }[]>([]);
  const [searching, setSearching] = useState(false);

  const loadCatalogs = async () => {
    if (!host || !token) {
      setError("No connection credentials provided.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await browseCatalog(host, token);
      setCatalogs(res.items || []);
    } catch (err: any) {
      setError(err.message || "Failed to load Unity Catalog.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadCatalogs();
  }, [host, token]);

  const toggleCatalog = async (catName: string) => {
    const isExp = !!expanded[catName];
    setExpanded((prev) => ({ ...prev, [catName]: !isExp }));

    if (!isExp && !children[catName]) {
      try {
        const res = await browseCatalog(host, token, catName);
        setChildren((prev) => ({ ...prev, [catName]: res.items || [] }));
      } catch (err) {
        console.error("Failed to load schemas:", err);
      }
    }
  };

  const toggleSchema = async (catName: string, schemaName: string) => {
    const key = `${catName}.${schemaName}`;
    const isExp = !!expanded[key];
    setExpanded((prev) => ({ ...prev, [key]: !isExp }));

    if (!isExp && !children[key]) {
      try {
        const res = await browseCatalog(host, token, catName, schemaName);
        setChildren((prev) => ({ ...prev, [key]: res.items || [] }));
      } catch (err) {
        console.error("Failed to load tables:", err);
      }
    }
  };

  // Debounced Search
  useEffect(() => {
    if (!search.trim()) {
      setSearchResults([]);
      setSearching(false);
      return;
    }

    const timer = setTimeout(async () => {
      setSearching(true);
      try {
        const res = await searchCatalog(host, token, search);
        setSearchResults(res.results || []);
      } catch {
        setSearchResults([]);
      } finally {
        setSearching(false);
      }
    }, 300);

    return () => clearTimeout(timer);
  }, [search, host, token]);

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <div className={styles.title}>
          <Database size={16} color="var(--accent-orange)" />
          Unity Catalog Browser
        </div>
        <button
          onClick={loadCatalogs}
          disabled={loading}
          style={{ background: "none", border: "none", color: "var(--text-tertiary)", cursor: "pointer" }}
          title="Refresh Metadata"
        >
          <RefreshCw size={14} className={loading ? "spin" : ""} />
        </button>
      </div>

      <div className={styles.searchBox}>
        <Search size={14} className={styles.searchIcon} />
        <input
          type="text"
          className={styles.searchInput}
          placeholder="Search catalog, schema, or table..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      <div className={styles.treeContent}>
        {loading ? (
          <div className={styles.loadingState}>
            <Loader2 size={24} className="spin" color="var(--accent-orange)" />
            <span>Connecting to Unity Catalog...</span>
          </div>
        ) : error ? (
          <div className={styles.emptyState}>
            <span style={{ color: "var(--accent-red)" }}>{error}</span>
            <button
              onClick={loadCatalogs}
              style={{
                marginTop: "0.5rem",
                padding: "0.25rem 0.75rem",
                borderRadius: "4px",
                background: "var(--bg-hover)",
                border: "1px solid var(--border-default)",
                color: "#fff",
                fontSize: "0.75rem",
              }}
            >
              Retry Connection
            </button>
          </div>
        ) : search.trim() ? (
          /* Search Results */
          searching ? (
            <div className={styles.loadingState}>
              <Loader2 size={18} className="spin" />
              <span>Searching Unity Catalog...</span>
            </div>
          ) : searchResults.length === 0 ? (
            <div className={styles.emptyState}>
              <span>No tables match "{search}"</span>
            </div>
          ) : (
            <div className={styles.searchResults}>
              {searchResults.map((r) => (
                <div
                  key={r.full_name}
                  className={`${styles.searchResultItem} ${
                    selectedTable === r.full_name ? styles.nodeSelected : ""
                  }`}
                  onClick={() => onSelectTable(r.full_name)}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                    <Table2 size={14} color="var(--accent-cyan)" />
                    <span className={styles.searchResultName}>{r.table}</span>
                  </div>
                  <span className={styles.searchResultPath}>
                    {r.catalog}.{r.schema}
                  </span>
                </div>
              ))}
            </div>
          )
        ) : catalogs.length === 0 ? (
          <div className={styles.emptyState}>
            <span>No catalogs found in workspace</span>
          </div>
        ) : (
          /* Tree View */
          catalogs.map((cat) => {
            const isCatExp = !!expanded[cat.name];
            const catSchemas = children[cat.name] || [];

            return (
              <div key={cat.name}>
                <div
                  className={styles.node}
                  onClick={() => toggleCatalog(cat.name)}
                >
                  {isCatExp ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                  <Database size={14} color="var(--accent-purple)" />
                  <span>{cat.name}</span>
                </div>

                {isCatExp &&
                  catSchemas.map((sch) => {
                    const schKey = `${cat.name}.${sch.name}`;
                    const isSchExp = !!expanded[schKey];
                    const schTables = children[schKey] || [];

                    return (
                      <div key={schKey}>
                        <div
                          className={`${styles.node} ${styles.indent1}`}
                          onClick={() => toggleSchema(cat.name, sch.name)}
                        >
                          {isSchExp ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                          <Folder size={14} color="var(--accent-amber)" />
                          <span>{sch.name}</span>
                        </div>

                        {isSchExp &&
                          schTables.map((tbl) => {
                            const fullName = tbl.full_name || `${cat.name}.${sch.name}.${tbl.name}`;
                            const isSelected = selectedTable === fullName;

                            return (
                              <div
                                key={fullName}
                                className={`${styles.node} ${styles.indent2} ${
                                  isSelected ? styles.nodeSelected : ""
                                }`}
                                onClick={() => onSelectTable(fullName)}
                              >
                                <Table2 size={14} color="var(--accent-cyan)" />
                                <span style={{ fontFamily: "var(--font-family-mono)" }}>
                                  {tbl.name}
                                </span>
                                {tbl.table_type && (
                                  <span className={styles.tableBadge}>
                                    {tbl.table_type.toLowerCase()}
                                  </span>
                                )}
                              </div>
                            );
                          })}
                      </div>
                    );
                  })}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
