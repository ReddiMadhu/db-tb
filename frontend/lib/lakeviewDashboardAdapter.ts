/**
 * LakeviewDashboardAdapter — normalize + correlate Tableau PARSE/compiler
 * artifacts with raw Databricks Lakeview JSON. Never invents missing data.
 */

export type ScaleKind = "categorical" | "temporal" | "quantitative" | "unknown";

export interface NormalizedField {
  fieldName: string;
  displayName: string;
  scaleType: ScaleKind;
  axisTitle?: string;
  expression?: string;
}

export interface NormalizedWidget {
  id: string;
  name: string;
  title: string;
  widgetType: string;
  datasetName?: string;
  datasetQuery?: string;
  fields: NormalizedField[];
  queryFields: { name: string; expression: string }[];
  raw: Record<string, unknown>;
}

export interface MatchedPair {
  tableauWorksheetName: string;
  widget: NormalizedWidget;
}

export interface ParsedDashboard {
  datasets: Map<string, { name: string; displayName: string; query: string }>;
  widgets: NormalizedWidget[];
}

const NON_CHART_PREFIXES = ["filter-", "textbox", "markdown", "text"];
const NON_CHART_TYPES = new Set([
  "filter",
  "textbox",
  "text",
  "markdown",
  "layout",
  "parameter",
  "page",
]);

const CALC_ID_RE = /Calculation_[0-9a-fA-F]+/g;
const AGG_RE = /\b(SUM|AVG|COUNT|COUNTD|MIN|MAX|MEDIAN|STDDEV|VAR)\s*\(/i;

/** Deterministic name normalization for matching (no fuzzy scoring). */
export function normalizeName(input: string | null | undefined): string {
  if (!input) return "";
  let s = String(input).trim().toLowerCase();
  // Strip common Tableau/copy suffixes
  s = s.replace(/\s*\(\s*\d+\s*\)\s*$/g, "");
  s = s.replace(/\s+copy\s*$/gi, "");
  s = s.replace(/[\s_\-]+/g, "");
  return s;
}

function asRecord(v: unknown): Record<string, unknown> | null {
  return v && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : null;
}

function asArray(v: unknown): unknown[] {
  return Array.isArray(v) ? v : [];
}

function scaleKind(scale: unknown): ScaleKind {
  const t = asRecord(scale)?.type;
  if (typeof t !== "string") return "unknown";
  const lower = t.toLowerCase();
  if (lower === "categorical" || lower === "ordinal" || lower === "nominal") return "categorical";
  if (lower === "temporal" || lower === "time" || lower === "datetime") return "temporal";
  if (lower === "quantitative" || lower === "continuous" || lower === "numeric") return "quantitative";
  return "unknown";
}

function encodingToField(key: string, enc: unknown): NormalizedField | null {
  const obj = asRecord(enc);
  if (!obj) return null;
  const fieldName = typeof obj.fieldName === "string" ? obj.fieldName : "";
  if (!fieldName && key === "label" && !obj.fieldName) return null;
  if (!fieldName) return null;
  const displayName =
    (typeof obj.displayName === "string" && obj.displayName) ||
    (asRecord(obj.axis)?.title as string | undefined) ||
    fieldName;
  const axisTitle =
    typeof asRecord(obj.axis)?.title === "string"
      ? (asRecord(obj.axis)!.title as string)
      : undefined;
  return {
    fieldName,
    displayName,
    scaleType: scaleKind(obj.scale),
    axisTitle,
  };
}

function isChartWidgetType(widgetType: string): boolean {
  const t = (widgetType || "").trim().toLowerCase();
  if (!t) return false;
  if (NON_CHART_TYPES.has(t)) return false;
  for (const p of NON_CHART_PREFIXES) {
    if (t.startsWith(p)) return false;
  }
  return true;
}

export function extractCalculationIds(text: string): string[] {
  if (!text) return [];
  const matches = text.match(CALC_ID_RE) || [];
  return Array.from(new Set(matches));
}

export function resolveCalcLabel(
  idOrName: string,
  parseCalcMap: Record<string, string>
): string {
  if (!idOrName) return "N/A";
  const direct = parseCalcMap[idOrName];
  if (direct) return direct;
  // Try bare Calculation_ id inside a longer token
  const ids = extractCalculationIds(idOrName);
  for (const id of ids) {
    if (parseCalcMap[id]) return parseCalcMap[id];
  }
  const norm = normalizeName(idOrName);
  for (const [k, v] of Object.entries(parseCalcMap)) {
    if (normalizeName(k) === norm || normalizeName(v) === norm) return v || k;
  }
  // Prefer not to show raw Calculation_ as primary if we can strip prefixes
  if (/^Calculation_/i.test(idOrName)) return idOrName;
  return idOrName;
}

export class LakeviewDashboardAdapter {
  private parsed: ParsedDashboard;

  constructor(raw: unknown) {
    this.parsed = LakeviewDashboardAdapter.parseDashboard(raw);
  }

  static parseDashboard(raw: unknown): ParsedDashboard {
    const root = asRecord(raw) || {};
    const datasets = new Map<string, { name: string; displayName: string; query: string }>();

    for (const ds of asArray(root.datasets)) {
      const d = asRecord(ds);
      if (!d || typeof d.name !== "string") continue;
      datasets.set(d.name, {
        name: d.name,
        displayName: typeof d.displayName === "string" ? d.displayName : d.name,
        query: typeof d.query === "string" ? d.query : "",
      });
    }

    const widgets: NormalizedWidget[] = [];
    for (const page of asArray(root.pages)) {
      const p = asRecord(page);
      if (!p) continue;
      for (const item of asArray(p.layout)) {
        const layoutItem = asRecord(item);
        const widget = asRecord(layoutItem?.widget);
        if (!widget) continue;

        const spec = asRecord(widget.spec) || {};
        const widgetType =
          typeof spec.widgetType === "string"
            ? spec.widgetType
            : typeof widget.textbox_spec === "string"
              ? "textbox"
              : "";

        const frame = asRecord(spec.frame) || {};
        const title =
          (typeof frame.title === "string" && frame.title) ||
          (typeof widget.name === "string" ? widget.name : "") ||
          "Untitled";

        const encodings = asRecord(spec.encodings) || {};
        const fields: NormalizedField[] = [];
        for (const [key, enc] of Object.entries(encodings)) {
          if (key === "filters") continue;
          if (Array.isArray(enc)) {
            for (const itemEnc of enc) {
              const f = encodingToField(key, itemEnc);
              if (f) fields.push(f);
            }
          } else {
            const f = encodingToField(key, enc);
            if (f) fields.push(f);
          }
        }

        const queryFields: { name: string; expression: string }[] = [];
        let datasetName: string | undefined;
        for (const q of asArray(widget.queries)) {
          const qObj = asRecord(q);
          const query = asRecord(qObj?.query);
          if (!query) continue;
          if (typeof query.datasetName === "string" && !datasetName) {
            datasetName = query.datasetName;
          }
          for (const field of asArray(query.fields)) {
            const f = asRecord(field);
            if (!f || typeof f.name !== "string") continue;
            const expression = typeof f.expression === "string" ? f.expression : "";
            queryFields.push({ name: f.name, expression });
            // Enrich field list if encoding missed it
            if (!fields.some((ef) => ef.fieldName === f.name)) {
              fields.push({
                fieldName: f.name,
                displayName: f.name,
                scaleType: AGG_RE.test(expression) ? "quantitative" : "unknown",
                expression,
              });
            } else {
              const existing = fields.find((ef) => ef.fieldName === f.name);
              if (existing && !existing.expression) existing.expression = expression;
            }
          }
        }

        const dsMeta = datasetName ? datasets.get(datasetName) : undefined;

        widgets.push({
          id: typeof widget.name === "string" ? widget.name : title,
          name: typeof widget.name === "string" ? widget.name : title,
          title,
          widgetType,
          datasetName,
          datasetQuery: dsMeta?.query,
          fields,
          queryFields,
          raw: widget as Record<string, unknown>,
        });
      }
    }

    return { datasets, widgets };
  }

  getChartWidgets(): NormalizedWidget[] {
    return this.parsed.widgets.filter((w) => isChartWidgetType(w.widgetType));
  }

  getAllWidgets(): NormalizedWidget[] {
    return this.parsed.widgets;
  }

  getVisualType(widget: NormalizedWidget): string {
    const t = widget.widgetType || "";
    if (!t) return "N/A";
    return t.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  }

  getWidgetTitle(widget: NormalizedWidget): string {
    return widget.title || widget.name || "N/A";
  }

  getDimensions(widget: NormalizedWidget): string[] {
    const dims = widget.fields
      .filter((f) => f.scaleType === "categorical" || f.scaleType === "temporal")
      .map((f) => f.displayName || f.fieldName);
    // Heuristic: x categorical often dimension when scales unknown — still only from fields
    if (dims.length === 0) {
      const enc = asRecord(asRecord(widget.raw.spec)?.encodings);
      const x = encodingToField("x", enc?.x);
      if (x && x.scaleType !== "quantitative") {
        return [x.displayName || x.fieldName];
      }
    }
    return Array.from(new Set(dims));
  }

  getMeasures(widget: NormalizedWidget): string[] {
    const measures = widget.fields
      .filter(
        (f) =>
          f.scaleType === "quantitative" ||
          (f.expression && AGG_RE.test(f.expression))
      )
      .map((f) => f.displayName || f.fieldName);
    return Array.from(new Set(measures));
  }

  getAxes(widget: NormalizedWidget): { x: string[]; y: string[] } {
    const enc = asRecord(asRecord(widget.raw.spec)?.encodings) || {};
    const collect = (slot: unknown): string[] => {
      if (Array.isArray(slot)) {
        return slot
          .map((s) => encodingToField("axis", s))
          .filter(Boolean)
          .map((f) => f!.displayName || f!.fieldName);
      }
      const f = encodingToField("axis", slot);
      return f ? [f.displayName || f.fieldName] : [];
    };
    return { x: collect(enc.x), y: collect(enc.y) };
  }

  getAggregations(widget: NormalizedWidget): string[] {
    const found = new Set<string>();
    for (const qf of widget.queryFields) {
      const m = qf.expression.match(AGG_RE);
      if (m) found.add(m[1].toUpperCase());
    }
    for (const f of widget.fields) {
      if (f.expression) {
        const m = f.expression.match(AGG_RE);
        if (m) found.add(m[1].toUpperCase());
      }
    }
    return Array.from(found);
  }

  getFilters(widget: NormalizedWidget): string[] {
    const enc = asRecord(asRecord(widget.raw.spec)?.encodings) || {};
    const filters = enc.filters;
    const out: string[] = [];
    if (Array.isArray(filters)) {
      for (const item of filters) {
        const f = asRecord(item);
        if (!f) continue;
        const name =
          (typeof f.fieldName === "string" && f.fieldName) ||
          (typeof f.displayName === "string" && f.displayName) ||
          "";
        if (name) out.push(name);
      }
    } else if (filters && typeof filters === "object") {
      const f = asRecord(filters);
      const name =
        (typeof f?.fieldName === "string" && f.fieldName) ||
        (typeof f?.displayName === "string" && f.displayName) ||
        "";
      if (name) out.push(name);
    }
    return out;
  }

  getQuery(widget: NormalizedWidget): string {
    return widget.datasetQuery || "N/A";
  }

  getDataset(widget: NormalizedWidget): string {
    if (!widget.datasetName) return "N/A";
    const ds = this.parsed.datasets.get(widget.datasetName);
    return ds?.displayName || widget.datasetName;
  }

  getFieldNames(widget: NormalizedWidget): string[] {
    const names = new Set<string>();
    for (const f of widget.fields) {
      if (f.fieldName) names.add(f.fieldName);
      if (f.displayName) names.add(f.displayName);
      for (const id of extractCalculationIds(f.fieldName)) names.add(id);
      for (const id of extractCalculationIds(f.displayName)) names.add(id);
      if (f.expression) {
        for (const id of extractCalculationIds(f.expression)) names.add(id);
      }
    }
    for (const qf of widget.queryFields) {
      if (qf.name) names.add(qf.name);
      for (const id of extractCalculationIds(qf.name)) names.add(id);
      for (const id of extractCalculationIds(qf.expression)) names.add(id);
    }
    if (widget.datasetQuery) {
      for (const id of extractCalculationIds(widget.datasetQuery)) names.add(id);
    }
    return Array.from(names);
  }

  /** Normalized field-name keys for linkage. */
  getNormalizedFieldKeys(widget: NormalizedWidget): Set<string> {
    const keys = new Set<string>();
    for (const name of this.getFieldNames(widget)) {
      const n = normalizeName(name);
      if (n) keys.add(n);
      for (const id of extractCalculationIds(name)) {
        keys.add(normalizeName(id));
        keys.add(id); // keep raw id for exact Calculation_ lookup
      }
    }
    return keys;
  }

  matchWorksheets(tableauNames: string[]): MatchedPair[] {
    const charts = this.getChartWidgets();
    const usedWidgetIds = new Set<string>();
    const pairs: MatchedPair[] = [];

    for (const name of tableauNames) {
      const key = normalizeName(name);
      if (!key) continue;
      const widget = charts.find((w) => {
        if (usedWidgetIds.has(w.id)) return false;
        return normalizeName(w.title) === key || normalizeName(w.name) === key;
      });
      if (widget) {
        usedWidgetIds.add(widget.id);
        pairs.push({ tableauWorksheetName: name, widget });
      }
    }
    return pairs;
  }
}

/** Build Calculation_… / internal name → human caption map from PARSE/compiler rows. */
export function buildCalcLabelMap(
  conversions: Array<Record<string, unknown>>,
  parseCalcs?: Array<Record<string, unknown>>
): Record<string, string> {
  const map: Record<string, string> = {};

  const add = (key: unknown, label: unknown) => {
    if (typeof key !== "string" || !key) return;
    const caption =
      (typeof label === "string" && label.trim()) ||
      key;
    // Never prefer Calculation_ as the stored display if we have a better caption
    if (!map[key] || /^Calculation_/i.test(map[key])) {
      map[key] = caption;
    }
    map[normalizeName(key)] = caption;
    if (typeof label === "string" && label.trim()) {
      map[normalizeName(label)] = label.trim();
    }
  };

  for (const c of conversions || []) {
    const name = c.name;
    const caption = c.caption || c.name;
    add(name, caption);
    if (typeof name === "string") {
      for (const id of extractCalculationIds(name)) add(id, caption);
    }
    const internal = c.internal_name;
    if (typeof internal === "string") add(internal, caption);
  }

  for (const c of parseCalcs || []) {
    const name = c.name;
    const caption = c.caption || c.name;
    add(name, caption);
    if (typeof name === "string") {
      for (const id of extractCalculationIds(name)) add(id, caption);
    }
    const internal = c.internal_name || c.internalName;
    if (typeof internal === "string") add(internal, caption);
  }

  return map;
}
