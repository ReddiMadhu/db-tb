"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { FolderOpen, Plus, Search, Trash2, ArrowRight, X, Layers } from "lucide-react";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import Badge from "@/components/ui/Badge";
import styles from "./Projects.module.css";

interface ProjectItem {
  id: string;
  name: string;
  description: string;
  workbookCount: number;
  environment: string;
  status: "ACTIVE" | "ARCHIVED" | "COMPLETED";
  createdAt: string;
}

const DEFAULT_PROJECTS: ProjectItem[] = [
  {
    id: "proj-1",
    name: "Enterprise Analytics Migration",
    description: "Insurance & Claims Analytics Tableau Workbooks",
    workbookCount: 0,
    environment: "Production Workspace (AWS)",
    status: "ACTIVE",
    createdAt: "2026-07-01",
  },
];

export default function ProjectsPage() {
  const [projects, setProjects] = useState<ProjectItem[]>([]);
  const [search, setSearch] = useState("");
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [newEnv, setNewEnv] = useState("Production Workspace (AWS)");

  useEffect(() => {
    const saved = localStorage.getItem("lakeview_projects");
    if (saved) {
      try {
        setProjects(JSON.parse(saved));
      } catch {
        setProjects(DEFAULT_PROJECTS);
      }
    } else {
      setProjects(DEFAULT_PROJECTS);
    }
  }, []);

  const saveProjects = (items: ProjectItem[]) => {
    setProjects(items);
    localStorage.setItem("lakeview_projects", JSON.stringify(items));
  };

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName) return;

    const item: ProjectItem = {
      id: `proj-${Date.now()}`,
      name: newName,
      description: newDesc || "Tableau → Databricks Migration Group",
      workbookCount: 0,
      environment: newEnv,
      status: "ACTIVE",
      createdAt: new Date().toISOString().split("T")[0],
    };

    saveProjects([item, ...projects]);
    setNewName("");
    setNewDesc("");
    setIsModalOpen(false);
  };

  const handleDelete = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (confirm("Are you sure you want to delete this project?")) {
      saveProjects(projects.filter((p) => p.id !== id));
    }
  };

  const filtered = projects.filter(
    (p) =>
      p.name.toLowerCase().includes(search.toLowerCase()) ||
      p.description.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className={styles.container}>
      <div className={styles.header} style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <h1 className={styles.title}>Projects</h1>
          <p className={styles.subtitle}>Workspace migration project groups and team organization.</p>
        </div>

        <Button variant="primary" icon={<Plus size={16} />} onClick={() => setIsModalOpen(true)}>
          New Project
        </Button>
      </div>

      {/* Search Bar */}
      <div style={{ display: "flex", gap: "1rem", alignItems: "center" }}>
        <div style={{ position: "relative", flex: 1 }}>
          <Search size={16} style={{ position: "absolute", left: "0.75rem", top: "50%", transform: "translateY(-50%)", color: "var(--text-tertiary)" }} />
          <input
            type="text"
            placeholder="Search projects by name or description..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{
              width: "100%",
              padding: "0.6rem 0.8rem 0.6rem 2.4rem",
              background: "var(--bg-card)",
              border: "1px solid var(--border-default)",
              borderRadius: "6px",
              color: "#fff",
              fontSize: "0.875rem",
            }}
          />
        </div>
      </div>

      {filtered.length === 0 ? (
        <Card>
          <div style={{ padding: "3rem", textAlign: "center", color: "var(--text-muted)" }}>
            <FolderOpen size={40} style={{ marginBottom: "1rem", opacity: 0.4 }} />
            <h3 style={{ color: "var(--text-primary)", marginBottom: "0.5rem" }}>No projects found</h3>
            <p style={{ fontSize: "0.875rem", marginBottom: "1.5rem" }}>
              Create a new migration project to organize your Tableau workbooks.
            </p>
            <Button variant="primary" icon={<Plus size={16} />} onClick={() => setIsModalOpen(true)}>
              Create Project
            </Button>
          </div>
        </Card>
      ) : (
        <div className={styles.grid}>
          {filtered.map((p) => (
            <Card key={p.id} clickable>
              <div className={styles.cardHeader} style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div className={styles.titleGroup} style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                  <FolderOpen size={18} color="var(--accent-orange)" />
                  <span className={styles.name} style={{ fontWeight: 600, fontSize: "1rem" }}>{p.name}</span>
                </div>
                <Badge status="COMPLETED" label={p.status} />
              </div>
              <p className={styles.desc} style={{ fontSize: "0.85rem", color: "var(--text-secondary)", margin: "0.5rem 0" }}>
                {p.description}
              </p>
              <div className={styles.footer} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "1rem" }}>
                <span style={{ fontSize: "0.75rem", color: "var(--text-tertiary)" }}>Target: {p.environment}</span>
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                  <Button variant="ghost" size="sm" icon={<Trash2 size={14} />} onClick={(e) => handleDelete(p.id, e)} />
                  <Link href="/migrations" className={styles.link} style={{ display: "inline-flex", alignItems: "center", gap: "0.25rem", color: "var(--accent-orange)", fontSize: "0.85rem", fontWeight: 600 }}>
                    Browse <ArrowRight size={14} />
                  </Link>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* Modal */}
      {isModalOpen && (
        <div
          style={{
            position: "fixed",
            top: 0, left: 0, right: 0, bottom: 0,
            background: "rgba(0,0,0,0.7)",
            display: "flex", alignItems: "center", justifyContent: "center",
            zIndex: 1000,
            backdropFilter: "blur(4px)",
          }}
        >
          <div
            style={{
              background: "var(--bg-card)",
              border: "1px solid var(--border-default)",
              borderRadius: "12px",
              padding: "1.75rem",
              width: "100%",
              maxWidth: "480px",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.25rem" }}>
              <h2 style={{ fontSize: "1.2rem", fontWeight: 600, margin: 0 }}>Create Migration Project</h2>
              <button onClick={() => setIsModalOpen(false)} style={{ background: "none", border: "none", color: "#fff", cursor: "pointer" }}>
                <X size={18} />
              </button>
            </div>

            <form onSubmit={handleCreate} style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
              <div>
                <label style={{ display: "block", fontSize: "0.85rem", color: "var(--text-secondary)", marginBottom: "0.35rem" }}>Project Name</label>
                <input
                  type="text"
                  placeholder="e.g. Finance Analytics Migration"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  style={{ width: "100%", padding: "0.6rem 0.8rem", background: "var(--bg-primary)", border: "1px solid var(--border-default)", borderRadius: "6px", color: "#fff" }}
                  required
                />
              </div>

              <div>
                <label style={{ display: "block", fontSize: "0.85rem", color: "var(--text-secondary)", marginBottom: "0.35rem" }}>Description</label>
                <textarea
                  placeholder="Project details and scope..."
                  value={newDesc}
                  onChange={(e) => setNewDesc(e.target.value)}
                  style={{ width: "100%", padding: "0.6rem 0.8rem", background: "var(--bg-primary)", border: "1px solid var(--border-default)", borderRadius: "6px", color: "#fff", minHeight: "80px" }}
                />
              </div>

              <div>
                <label style={{ display: "block", fontSize: "0.85rem", color: "var(--text-secondary)", marginBottom: "0.35rem" }}>Target Environment</label>
                <select
                  value={newEnv}
                  onChange={(e) => setNewEnv(e.target.value)}
                  style={{ width: "100%", padding: "0.6rem 0.8rem", background: "var(--bg-primary)", border: "1px solid var(--border-default)", borderRadius: "6px", color: "#fff" }}
                >
                  <option value="Production Workspace (AWS)">Production Workspace (AWS)</option>
                  <option value="Dev / Staging Workspace">Dev / Staging Workspace</option>
                </select>
              </div>

              <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem", marginTop: "0.5rem" }}>
                <Button type="button" variant="secondary" onClick={() => setIsModalOpen(false)}>Cancel</Button>
                <Button type="submit" variant="primary">Create Project</Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
