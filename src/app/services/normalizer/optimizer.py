from app.models.universal_model import IntermediateDashboard


def optimize_ubim(dashboard: IntermediateDashboard) -> IntermediateDashboard:
    """Stage 7 Optimizer: Deduplicates identical dataset queries, prunes unused datasets/fields."""
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

    # Remap widget dataset references if deduplicated
    for page in dashboard.pages:
        for widget in page.widgets:
            if widget.dataset_name in ds_remap:
                widget.dataset_name = ds_remap[widget.dataset_name]
            for enc in widget.encodings:
                if enc.dataset_name in ds_remap:
                    enc.dataset_name = ds_remap[enc.dataset_name]

    return dashboard
