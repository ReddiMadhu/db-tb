"""
dependency_graph.py — Directed Acyclic Graph (DAG) Engine
===========================================================
Builds a DAG of all workbook entities (Datasources, Tables, Columns,
CalculatedFields, Worksheets, Dashboards) to perform reference resolution,
topological ordering, orphan field detection, and cycle validation.
"""

import re
from typing import Dict, List, Set, Tuple, Any
from app.models.metadata import WorkbookMetadata

try:
    import networkx as nx
except ImportError:
    nx = None


class SimpleDiGraphFallback:
    """Pure Python directed graph fallback with Kahn's topological sort and cycle detection."""
    
    def __init__(self):
        self._nodes: Dict[str, Dict[str, Any]] = {}
        self._succ: Dict[str, Set[str]] = {}
        self._pred: Dict[str, Set[str]] = {}

    def add_node(self, node: str, **kwargs):
        if node not in self._nodes:
            self._nodes[node] = kwargs
        else:
            self._nodes[node].update(kwargs)
        if node not in self._succ:
            self._succ[node] = set()
        if node not in self._pred:
            self._pred[node] = set()

    def add_edge(self, u: str, v: str):
        self.add_node(u)
        self.add_node(v)
        self._succ[u].add(v)
        self._pred[v].add(u)

    def has_node(self, node: str) -> bool:
        return node in self._nodes

    def out_degree(self, node: str) -> int:
        return len(self._succ.get(node, set()))

    def in_degree(self, node: str) -> int:
        return len(self._pred.get(node, set()))

    def nodes(self, data: bool = False):
        if data:
            return [(n, self._nodes[n]) for n in self._nodes]
        return list(self._nodes.keys())

    def simple_cycles(self) -> List[List[str]]:
        """DFS-based cycle detection for pure Python fallback."""
        visited = set()
        rec_stack = set()
        cycles = []

        def dfs(node, path):
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for neighbor in self._succ.get(node, set()):
                if neighbor not in visited:
                    dfs(neighbor, path)
                elif neighbor in rec_stack:
                    cycle_start = path.index(neighbor)
                    cycles.append(path[cycle_start:])

            path.pop()
            rec_stack.remove(node)

        for n in self._nodes:
            if n not in visited:
                dfs(n, [])

        return cycles

    def topological_sort(self) -> List[str]:
        """Kahn's Algorithm for Topological Sort."""
        in_degree = {n: len(self._pred[n]) for n in self._nodes}
        queue = [n for n in self._nodes if in_degree[n] == 0]
        result = []

        while queue:
            node = queue.pop(0)
            result.append(node)
            for neighbor in self._succ.get(node, set()):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(result) == len(self._nodes):
            return result
        # Fallback to node list if cycle exists
        return list(self._nodes.keys())


class DependencyGraphEngine:
    """
    Builds a directed acyclic graph (DAG) of all entities to perform reference
    resolution, topological sort ordering, orphan detection, and cycle validation.
    """

    def __init__(self, workbook_meta: WorkbookMetadata):
        self.workbook_meta = workbook_meta
        self.graph = nx.DiGraph() if nx is not None else SimpleDiGraphFallback()
        self._build_graph()

    def _build_graph(self):
        # Build map of all calculated field names -> node IDs
        cf_map: Dict[str, str] = {}
        for ds in self.workbook_meta.datasources:
            for cf in ds.calculated_fields:
                cf_map[cf.name] = f"CF::{ds.name}::{cf.name}"

        # 1. Add Datasource nodes
        for ds in self.workbook_meta.datasources:
            ds_node = f"DS::{ds.name}"
            self.graph.add_node(ds_node, type="datasource", name=ds.name)

            # 2. Add Table nodes & edges DS -> Table
            for tbl in ds.tables:
                tbl_node = f"TBL::{ds.name}::{tbl.name}"
                self.graph.add_node(tbl_node, type="table", name=tbl.name, ds=ds.name)
                self.graph.add_edge(ds_node, tbl_node)

            # 3. Add Column nodes & edges Table -> Column
            for col in ds.columns:
                col_name = col.caption or col.internal_name
                col_node = f"COL::{ds.name}::{col_name}"
                self.graph.add_node(col_node, type="column", name=col_name, ds=ds.name)
                for tbl_name in col.source_tables:
                    tbl_node = f"TBL::{ds.name}::{tbl_name}"
                    if self.graph.has_node(tbl_node):
                        self.graph.add_edge(tbl_node, col_node)

            # 4. Add CalculatedField nodes & dependencies (Table -> CF and CF -> CF)
            for cf in ds.calculated_fields:
                cf_node = f"CF::{ds.name}::{cf.name}"
                self.graph.add_node(cf_node, type="calculated_field", name=cf.name, formula=cf.formula)
                
                # Source table edges
                for tbl_name in cf.source_tables:
                    tbl_node = f"TBL::{ds.name}::{tbl_name}"
                    if self.graph.has_node(tbl_node):
                        self.graph.add_edge(tbl_node, cf_node)
                
                # Inter-calculated-field edges (CF_B -> CF_A if CF_A references CF_B)
                for ref_name in re.findall(r'\[([^\]]+)\]', cf.formula or ""):
                    if ref_name in cf_map and cf_map[ref_name] != cf_node:
                        ref_cf_node = cf_map[ref_name]
                        self.graph.add_edge(ref_cf_node, cf_node)

        # 5. Add Worksheet nodes & edges Column/CF -> Worksheet
        for ws in self.workbook_meta.worksheets:
            ws_node = f"WS::{ws.name}"
            self.graph.add_node(ws_node, type="worksheet", name=ws.name)
            referenced_fields = set(ws.columns + ws.rows + ws.used_calculated_fields)
            for sf in ws.columns_shelves + ws.rows_shelves:
                referenced_fields.add(sf.field_name)
            for enc in ws.encodings:
                referenced_fields.add(enc.field_name)

            for field in referenced_fields:
                for ds in self.workbook_meta.datasources:
                    cf_node = f"CF::{ds.name}::{field}"
                    col_node = f"COL::{ds.name}::{field}"
                    if self.graph.has_node(cf_node):
                        self.graph.add_edge(cf_node, ws_node)
                    elif self.graph.has_node(col_node):
                        self.graph.add_edge(col_node, ws_node)

        # 6. Add Dashboard nodes & edges Worksheet -> Dashboard
        for db in self.workbook_meta.dashboards:
            db_node = f"DB::{db.name}"
            self.graph.add_node(db_node, type="dashboard", name=db.name)
            for ws_name in db.worksheets:
                ws_node = f"WS::{ws_name}"
                if self.graph.has_node(ws_node):
                    self.graph.add_edge(ws_node, db_node)

    def detect_cycles(self) -> List[List[str]]:
        try:
            if nx is not None:
                return list(nx.simple_cycles(self.graph))
            return self.graph.simple_cycles()
        except Exception:
            return []

    def get_topological_order(self) -> List[str]:
        if nx is not None and nx.is_directed_acyclic_graph(self.graph):
            return list(nx.topological_sort(self.graph))
        return self.graph.topological_sort()

    def get_orphans(self) -> List[str]:
        orphans = []
        for node, data in self.graph.nodes(data=True):
            if data.get("type") in ("calculated_field", "column"):
                if self.graph.out_degree(node) == 0:
                    orphans.append(node)
        return orphans
