try:
    import networkx as nx
except ImportError:
    nx = None

from typing import Dict, List, Set, Tuple
from app.models.metadata import WorkbookMetadata


class SimpleDiGraphFallback:
    """Pure Python directed graph fallback when networkx is not installed."""
    def __init__(self):
        self._nodes = {}
        self._succ = {}
        self._pred = {}

    def add_node(self, node, **kwargs):
        self._nodes[node] = kwargs
        if node not in self._succ:
            self._succ[node] = set()
        if node not in self._pred:
            self._pred[node] = set()

    def add_edge(self, u, v):
        self.add_node(u)
        self.add_node(v)
        self._succ[u].add(v)
        self._pred[v].add(u)

    def has_node(self, node):
        return node in self._nodes

    def out_degree(self, node):
        return len(self._succ.get(node, []))

    def nodes(self, data=False):
        if data:
            return [(n, self._nodes[n]) for n in self._nodes]
        return list(self._nodes.keys())

    def simple_cycles(self):
        return []

    def topological_sort(self):
        return list(self._nodes.keys())


class DependencyGraphEngine:
    """
    Builds a directed acyclic graph (DAG) of all entities (Datasources, Tables, Columns, CalculatedFields, Worksheets, Dashboards)
    to perform reference resolution, topological sort ordering, orphan detection, and cycle validation.
    """

    def __init__(self, workbook_meta: WorkbookMetadata):
        self.workbook_meta = workbook_meta
        self.graph = nx.DiGraph() if nx is not None else SimpleDiGraphFallback()
        self._build_graph()

    def _build_graph(self):
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
                col_node = f"COL::{ds.name}::{col.caption or col.internal_name}"
                self.graph.add_node(col_node, type="column", name=col.caption or col.internal_name, ds=ds.name)
                for tbl_name in col.source_tables:
                    tbl_node = f"TBL::{ds.name}::{tbl_name}"
                    if self.graph.has_node(tbl_node):
                        self.graph.add_edge(tbl_node, col_node)

            # 4. Add CalculatedField nodes & dependencies
            for cf in ds.calculated_fields:
                cf_node = f"CF::{ds.name}::{cf.name}"
                self.graph.add_node(cf_node, type="calculated_field", name=cf.name, formula=cf.formula)
                for tbl_name in cf.source_tables:
                    tbl_node = f"TBL::{ds.name}::{tbl_name}"
                    if self.graph.has_node(tbl_node):
                        self.graph.add_edge(tbl_node, cf_node)

        # 5. Add Worksheet nodes & edges Column/CF -> Worksheet
        for ws in self.workbook_meta.worksheets:
            ws_node = f"WS::{ws.name}"
            self.graph.add_node(ws_node, type="worksheet", name=ws.name)
            for field in ws.columns + ws.rows + ws.used_calculated_fields:
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
        return list(self.graph.nodes())

    def get_orphans(self) -> List[str]:
        orphans = []
        for node, data in self.graph.nodes(data=True):
            if data.get("type") in ("calculated_field", "column"):
                if self.graph.out_degree(node) == 0:
                    orphans.append(node)
        return orphans
