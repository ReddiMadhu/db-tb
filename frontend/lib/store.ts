/* ═══════════════════════════════════════════════
   LakeShift Zustand Stores
   ═══════════════════════════════════════════════ */

import { create } from "zustand";
import type { Migration, Project } from "./types";

// ── UI Store ──
interface UIState {
  sidebarCollapsed: boolean;
  inspectorOpen: boolean;
  theme: "dark" | "light";
  commandPaletteOpen: boolean;
  toggleSidebar: () => void;
  toggleInspector: () => void;
  toggleTheme: () => void;
  setCommandPaletteOpen: (open: boolean) => void;
}

export const useUIStore = create<UIState>((set) => ({
  sidebarCollapsed: false,
  inspectorOpen: true,
  theme: "dark",
  commandPaletteOpen: false,
  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
  toggleInspector: () => set((s) => ({ inspectorOpen: !s.inspectorOpen })),
  toggleTheme: () =>
    set((s) => {
      const next = s.theme === "dark" ? "light" : "dark";
      if (typeof document !== "undefined") {
        document.documentElement.setAttribute("data-theme", next);
      }
      return { theme: next };
    }),
  setCommandPaletteOpen: (open) => set({ commandPaletteOpen: open }),
}));

// ── Projects Store (local state, no backend for projects yet) ──
interface ProjectsState {
  projects: Project[];
  activeProjectId: string | null;
  addProject: (project: Project) => void;
  setActiveProject: (id: string) => void;
  addMigrationToProject: (projectId: string, migration: Migration) => void;
  updateMigration: (projectId: string, jobUuid: string, updates: Partial<Migration>) => void;
}

export const useProjectsStore = create<ProjectsState>((set) => ({
  projects: [],
  activeProjectId: null,
  addProject: (project) =>
    set((s) => ({ projects: [...s.projects, project] })),
  setActiveProject: (id) => set({ activeProjectId: id }),
  addMigrationToProject: (projectId, migration) =>
    set((s) => ({
      projects: s.projects.map((p) =>
        p.id === projectId
          ? { ...p, migrations: [...p.migrations, migration] }
          : p
      ),
    })),
  updateMigration: (projectId, jobUuid, updates) =>
    set((s) => ({
      projects: s.projects.map((p) =>
        p.id === projectId
          ? {
              ...p,
              migrations: p.migrations.map((m) =>
                m.jobUuid === jobUuid ? { ...m, ...updates } : m
              ),
            }
          : p
      ),
    })),
}));

// ── Selection Store ──
interface SelectionState {
  selectedAssetType: string | null;
  selectedAssetId: string | null;
  selectAsset: (type: string, id: string) => void;
  clearSelection: () => void;
}

export const useSelectionStore = create<SelectionState>((set) => ({
  selectedAssetType: null,
  selectedAssetId: null,
  selectAsset: (type, id) => set({ selectedAssetType: type, selectedAssetId: id }),
  clearSelection: () => set({ selectedAssetType: null, selectedAssetId: null }),
}));
