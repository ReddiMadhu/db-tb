# Universal BI Object Model

This document outlines a vendor-neutral intermediate BI model designed to facilitate migrations from various platforms into Databricks Lakeview or other BI systems.

## Core Objects [Verified]

```mermaid
classDiagram
    class IntermediateDashboard {
        +String id
        +String name
        +String description
        +List~IntermediatePage~ pages
        +List~IntermediateDataset~ datasets
        +Object theme
    }

    class IntermediatePage {
        +String id
        +String name
        +List~IntermediateWidget~ widgets
        +IntermediateLayout layout
    }

    class IntermediateWidget {
        +String id
        +String name
        +String type
        +IntermediateVisualization visualization
        +String datasetRef
        +IntermediatePosition position
    }

    class IntermediateDataset {
        +String id
        +String name
        +String query
        +List~IntermediateParameter~ parameters
        +List~Object~ columns
    }

    class IntermediateVisualization {
        +String type
        +List~IntermediateEncoding~ encodings
        +Object formatting
        +Object interactions
    }

    class IntermediateFilter {
        +String id
        +String name
        +String type
        +String field
        +List~String~ values
        +List~String~ connections
    }

    class IntermediateParameter {
        +String id
        +String name
        +String dataType
        +String defaultValue
        +List~String~ allowedValues
    }

    class IntermediateLayout {
        +Int gridColumns
        +Int gridRows
        +List~IntermediatePosition~ positions
    }

    class IntermediatePosition {
        +Int x
        +Int y
        +Int width
        +Int height
    }

    class IntermediateEncoding {
        +String channel
        +String field
        +String aggregation
        +String scale
        +String axis
        +String format
    }

    IntermediateDashboard "1" *-- "many" IntermediatePage
    IntermediateDashboard "1" *-- "many" IntermediateDataset
    IntermediatePage "1" *-- "many" IntermediateWidget
    IntermediatePage "1" *-- "1" IntermediateLayout
    IntermediateWidget "1" *-- "1" IntermediateVisualization
    IntermediateWidget "1" *-- "1" IntermediatePosition
    IntermediateVisualization "1" *-- "many" IntermediateEncoding
```

## Mapping Tables [Inferred]

### Tableau (.twb XML) -> Intermediate
- Workbooks become `IntermediateDashboard`.
- Dashboards become `IntermediatePage`.
- Sheets in a dashboard become `IntermediateWidget`.
- Data Sources become `IntermediateDataset`.

### Power BI (.pbit JSON) -> Intermediate
- Report sections become `IntermediatePage`.
- VisualContainers become `IntermediateWidget`.
- M/DAX queries translated (via intermediate logic) to SQL `IntermediateDataset`.

### Looker (LookML) -> Intermediate
- Dashboards map to `IntermediateDashboard`.
- Elements map to `IntermediateWidget`.
- Explores/Views mapped to `IntermediateDataset` (SQL).

### MicroStrategy (REST API) -> Intermediate
- Documents/Dossiers to `IntermediateDashboard`.
- Chapters to `IntermediatePage`.
- Visualizations to `IntermediateWidget`.

### Qlik (QVF/JSON) -> Intermediate
- Sheets to `IntermediatePage`.
- Objects to `IntermediateWidget`.
- Load script logic to `IntermediateDataset`.

### SAP BO (REST API) -> Intermediate
- WebI reports to `IntermediatePage`.
- Blocks to `IntermediateWidget`.
- Data Providers to `IntermediateDataset`.

### Intermediate -> Databricks Lakeview (.lvdash.json)
- `IntermediateDashboard` serialized to `lvdash.json`.
- `IntermediateDataset` becomes Lakeview `datasets`.
- `IntermediatePage` becomes Lakeview `pages`.
- `IntermediateWidget` becomes Lakeview `widgets`.

## JSON Schema [Observed]

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "id": { "type": "string" },
    "name": { "type": "string" },
    "pages": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "id": { "type": "string" },
          "widgets": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "id": { "type": "string" },
                "type": { "type": "string" },
                "datasetRef": { "type": "string" }
              }
            }
          }
        }
      }
    },
    "datasets": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "id": { "type": "string" },
          "query": { "type": "string" }
        }
      }
    }
  }
}
```

## Entity Relationship Diagram [Verified]

```mermaid
erDiagram
    DASHBOARD ||--o{ PAGE : contains
    DASHBOARD ||--o{ DATASET : uses
    PAGE ||--o{ WIDGET : contains
    PAGE ||--|| LAYOUT : defines
    WIDGET ||--|| VISUALIZATION : renders
    WIDGET ||--|| POSITION : positioned_by
    WIDGET }o--|| DATASET : sources_from
    VISUALIZATION ||--o{ ENCODING : has
    DATASET ||--o{ PARAMETER : accepts
```
