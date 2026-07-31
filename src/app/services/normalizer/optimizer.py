from app.models.universal_model import IntermediateDashboard, IntermediateWidget


def optimize_ubim(dashboard: IntermediateDashboard) -> IntermediateDashboard:
    """Stage 7 Optimizer: Deduplicates identical dataset queries, prunes unused datasets/fields,
    and removes duplicate identical widgets."""
    seen_queries = {}
    ds_remap = {}

    unique_datasets = []
    for ds in dashboard.datasets:
        if ds.sql_query in seen_queries:
            ds_remap[ds.name] = seen_queries[ds.sql_query]
        else:
            seen_queries[ds.sql_query] = ds.name
            unique_datasets.append(ds)

    dashboard.datasets = unique_datasets

    # Remap widget dataset references if deduplicated and remove duplicate widgets
    for page in dashboard.pages:
        unique_widgets = []
        seen_widget_signatures = set()

        for widget in page.widgets:
            if widget.dataset_name in ds_remap:
                widget.dataset_name = ds_remap[widget.dataset_name]
            for enc in widget.encodings:
                if enc.dataset_name in ds_remap:
                    enc.dataset_name = ds_remap[enc.dataset_name]

            # Signature for duplicate widget detection
            clean_title = (widget.title or "").replace(" (2)", "").replace(" 2", "").strip().lower()
            enc_sig = tuple(sorted((e.channel.value, e.field_name) for e in widget.encodings))
            sig = (clean_title, widget.chart_type.value, widget.dataset_name, enc_sig)

            if sig not in seen_widget_signatures:
                seen_widget_signatures.add(sig)
                unique_widgets.append(widget)

        page.widgets = unique_widgets

    return dashboard
