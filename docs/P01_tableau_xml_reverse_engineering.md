# PHASE 1 — TABLEAU REVERSE ENGINEERING

This document provides an exhaustive, implementation-level technical specification of the Tableau Workbook format (`.twb` and `.twbx`). It is designed for engineers building parsers, migration tools, or reverse-engineering systems to translate Tableau metadata into other BI platforms.

---

## 1. TWB File Format

The `.twb` (Tableau Workbook) file is a standard XML document. It defines the entire structure of the workbook, including connections, datasources, metadata, calculated fields, worksheets, dashboards, stories, and formatting rules.

### Top-Level Structure

A standard `.twb` file has the following skeleton:

```xml
<?xml version='1.0' encoding='utf-8' ?>
<!-- build 20212.21.0712.0907                               -->
<workbook original-version='18.1' source-build='2021.2.1 (20212.21.0712.0907)' source-platform='win' version='18.1' xmlns:user='http://www.tableausoftware.com/xml/user'>
  <document-format-change-manifest>
    <!-- Feature flags and version manifestations -->
  </document-format-change-manifest>
  <preferences>
    <!-- Custom color palettes -->
  </preferences>
  <datasources>
    <!-- Data connections, logical/physical tables, fields -->
  </datasources>
  <worksheets>
    <!-- Visualization definitions -->
  </worksheets>
  <dashboards>
    <!-- Layout and zone definitions -->
  </dashboards>
  <windows>
    <!-- UI state, window positions, active tabs -->
  </windows>
</workbook>
```

### Attributes of `<workbook>`
- `original-version`: The version of Tableau used to originally create the file.
- `source-build`: The specific build string (e.g., `2021.2.1`).
- `source-platform`: `win` or `mac`.
- `version`: The current XML schema version (e.g., `18.1` corresponds to Tableau 2020.2+).
- `xmlns:user`: Namespace for user-defined attributes.

---

## 2. TWBX Package Format

A `.twbx` (Tableau Packaged Workbook) is a ZIP archive containing the `.twb` file and all necessary local assets.

### Archive Structure
When unzipped, a `.twbx` typically contains:
- `WorkbookName.twb`: The core XML file.
- `Data/`: Directory containing local data extracts.
  - `Extracts/`: Contains `.hyper` (Hyper Data Engine) or legacy `.tde` files.
  - `Connections/`: May contain local `.csv`, `.xlsx`, or `.mdb` files.
- `Image/`: Directory containing custom images, background images, and custom shapes.

### Programmatic Extraction
To programmatically read a `.twbx`:
1. Open the file as a standard ZIP archive.
2. Search for the entry ending in `.twb` in the root directory.
3. Extract and parse the `.twb` XML.
4. If the XML references local files (e.g., `filename='Data/Extracts/data.hyper'`), extract these paths relative to the ZIP root.

---

## 3. Datasource XML (`<datasource>`)

The `<datasources>` node contains one or more `<datasource>` definitions. A datasource can be an external connection, an extract, or a parameter collection (often identified as `<datasource hasconnection='false' inline='true' name='Parameters'>`).

### Connection Information

```xml
<datasource caption='SalesData' inline='true' name='federated.1a2b3c' version='18.1'>
  <connection class='federated'>
    <named-connections>
      <named-connection caption='PostgreSQL' name='postgres.4d5e6f'>
        <connection class='postgres' dbname='sales_db' port='5432' server='db.example.com' username='admin' />
      </named-connection>
    </named-connections>
    <!-- Relation Definitions -->
  </connection>
</datasource>
```
- `class` attribute on `<connection>` dictates the driver (e.g., `sqlserver`, `postgres`, `databricks`, `excel-direct`, `textscan`, `hyper`).

### Logical Layer vs Physical Layer (Tableau 2020.2+)
Tableau replaced the old `<relation>` join trees with a new Object Model consisting of logical tables and physical tables.

#### Object Model Structure
```xml
<connection class='federated'>
  <!-- ... named connections ... -->
  <relation connection='postgres.4d5e6f' name='orders' table='[public].[orders]' type='table' />
</connection>
<object-graph>
  <objects>
    <object caption='Orders' id='orders_1'>
      <properties context=''>
        <relation connection='postgres.4d5e6f' name='orders' table='[public].[orders]' type='table' />
      </properties>
    </object>
  </objects>
  <relationships>
    <relationship>
      <expression op='='>
        <expression op='[orders_1].[customer_id]' />
        <expression op='[customers_1].[id]' />
      </expression>
      <first-end-point object-id='orders_1' />
      <second-end-point object-id='customers_1' />
    </relationship>
  </relationships>
</object-graph>
```

#### Legacy Join Tree (Pre-2020.2 or Physical Joins)
```xml
<relation join='inner' type='join'>
  <clause type='join'>
    <expression op='='>
      <expression op='[Orders].[CustomerID]' />
      <expression op='[Customers].[ID]' />
    </expression>
  </clause>
  <relation connection='sqlserver.1' name='Orders' table='[dbo].[Orders]' type='table' />
  <relation connection='sqlserver.1' name='Customers' table='[dbo].[Customers]' type='table' />
</relation>
```

### Metadata Records & Columns
```xml
<metadata-records>
  <metadata-record class='column'>
    <remote-name>Sales</remote-name>
    <remote-type>131</remote-type> <!-- numeric/float -->
    <local-name>[Sales]</local-name>
    <parent-name>[Orders]</parent-name>
    <remote-alias>Sales</remote-alias>
    <ordinal>1</ordinal>
    <local-type>real</local-type>
    <aggregation>Sum</aggregation>
    <contains-null>true</contains-null>
  </metadata-record>
</metadata-records>

<aliases>
  <alias key='[Sales]' value='Total Sales Revenue' />
</aliases>

<column datatype='real' name='[Sales]' role='measure' type='quantitative' />
```
- `role`: `dimension` or `measure`.
- `type`: `quantitative`, `ordinal`, or `nominal`.

---

## 4. Calculated Fields

Calculated fields are defined as `<column>` tags with a `<calculation>` child inside the `<datasource>`.

```xml
<column caption='Profit Margin' datatype='real' name='[Calculation_12345]' role='measure' type='quantitative'>
  <calculation class='tableau' formula='SUM([Profit]) / SUM([Sales])' />
</column>
```

### Level of Detail (LOD) Expressions
Tableau represents LODs natively in the formula text:
```xml
<calculation class='tableau' formula='{ FIXED [Region], [Category] : SUM([Sales]) }' />
```

### Table Calculations
Table calculations are standard expressions but rely on specific Tableau functions like `WINDOW_SUM`, `RUNNING_TOTAL`, `INDEX()`, etc.
```xml
<calculation class='tableau' formula='WINDOW_SUM(SUM([Sales]), -2, 0)' />
```
Direction and partitioning for table calculations are defined at the worksheet level within `<sort>` and `<groupfilter>` tags, not in the datasource definition.

---

## 5. Parameters

Parameters are stored in a special pseudo-datasource.

```xml
<datasource hasconnection='false' inline='true' name='Parameters' version='18.1'>
  <aliases enabled='yes' />
  <column caption='Top N Parameter' datatype='integer' name='[Parameter 1]' param-domain-type='range' role='measure' type='quantitative' value='10'>
    <calculation class='tableau' formula='10' />
    <range granularity='5' max='50' min='5' />
  </column>
  <column caption='Sort By' datatype='string' name='[Parameter 2]' param-domain-type='list' role='dimension' type='nominal' value='&quot;Sales&quot;'>
    <calculation class='tableau' formula='&quot;Sales&quot;' />
    <aliases>
      <alias key='&quot;Profit&quot;' value='Sort by Profit' />
      <alias key='&quot;Sales&quot;' value='Sort by Sales' />
    </aliases>
    <members>
      <member alias='Sort by Sales' value='&quot;Sales&quot;' />
      <member alias='Sort by Profit' value='&quot;Profit&quot;' />
    </members>
  </column>
</datasource>
```
Attributes:
- `datatype`: `string`, `integer`, `real`, `date`, `datetime`, `boolean`.
- `param-domain-type`: `all`, `list`, `range`.
- `value`: Current selected value.

---

## 6. Worksheets (`<worksheet>`)

A worksheet represents a single view or chart.

```xml
<worksheet name='Sales Trend'>
  <table>
    <view>
      <datasources>
        <datasource caption='SalesData' name='federated.1a2b3c' />
      </datasources>
      <datasource-dependencies datasource='federated.1a2b3c'>
        <column datatype='date' name='[Order Date]' role='dimension' type='ordinal' />
        <column datatype='real' name='[Sales]' role='measure' type='quantitative' />
        <column-instance column='[Order Date]' derivation='Year' name='[yr:Order Date:ok]' pivot='key' type='ordinal' />
        <column-instance column='[Sales]' derivation='Sum' name='[sum:Sales:qk]' pivot='key' type='quantitative' />
      </datasource-dependencies>
      <filter class='categorical' column='[federated.1a2b3c].[Region]'>
        <groupfilter function='member' level='[Region]' member='&quot;West&quot;' user:ui-domain='database' user:ui-enumeration='inclusive' user:ui-marker='enumerate' />
      </filter>
    </view>
    <style>
      <style-rule element='mark'>
        <format attr='mark-labels-show' value='true' />
      </style-rule>
    </style>
    <panes>
      <pane selection-relaxation-option='selection-relaxation-allow'>
        <view>
          <breakdown value='auto' />
        </view>
        <mark class='Line' />
        <encodings>
          <color column='[federated.1a2b3c].[Region]' />
          <text column='[federated.1a2b3c].[sum:Sales:qk]' />
        </encodings>
      </pane>
    </panes>
    <rows>[federated.1a2b3c].[sum:Sales:qk]</rows>
    <cols>[federated.1a2b3c].[yr:Order Date:ok]</cols>
  </table>
</worksheet>
```
- `<datasource-dependencies>` maps physical columns to specific derivation instances (e.g., `[sum:Sales:qk]` represents the SUM of Sales, Quantitative).
- `<rows>` and `<cols>` map directly to the Rows and Columns shelves.
- `<panes>` define the Mark type (`class='Line'`, `Bar`, `Area`, `Pie`, etc.) and Encodings (Color, Size, Label/Text, Tooltip).

---

## 7. Dashboards (`<dashboard>`)

Dashboards combine multiple worksheets using a nested container hierarchy.

```xml
<dashboard name='Executive Summary'>
  <style />
  <size maxheight='800' maxwidth='1200' minheight='800' minwidth='1200' />
  <zones>
    <zone h='100000' id='4' type='layout-basic' w='100000' x='0' y='0'>
      <zone h='98000' id='1' param='vert' type='layout-flow' w='98000' x='1000' y='1000'>
        <zone h='50000' id='2' name='Sales Trend' type='title' w='98000' x='1000' y='1000' />
        <zone h='48000' id='3' name='Sales Trend' type='layout-basic' w='98000' x='1000' y='51000'>
          <!-- Worksheet reference -->
          <zone type='sheet' name='Sales Trend' />
        </zone>
      </zone>
    </zone>
  </zones>
  <devicelayouts>
    <devicelayout auto-generated='true' name='Phone'>
      <size maxheight='700' minheight='700' sizing-mode='vscroll' width='375' />
      <zones>
        <!-- Device specific overrides -->
      </zones>
    </devicelayout>
  </devicelayouts>
</dashboard>
```
- Coordinates (`x`, `y`, `w`, `h`) are percentages of the dashboard size, scaled by 100,000. So `w='50000'` means 50% width.
- `type='layout-flow'` implies a linear container (`param='vert'` or `param='horz'`).
- `type='layout-basic'` allows absolute positioning.
- Common zone types: `sheet`, `title`, `text`, `bitmap`, `filter`, `paramctrl`, `empty`.

---

## 8. Stories (`<story>`)

Stories are sequence of dashboard or worksheet views (Story Points).

```xml
<story name='Sales Narrative'>
  <size maxheight='964' maxwidth='1016' minheight='964' minwidth='1016' />
  <story-points>
    <story-point caption='Initial Sales Spike' captured-sheet='Sales Trend' id='1'>
      <captured-view>
        <!-- State overrides (e.g., specific filter values applied only in this story point) -->
      </captured-view>
    </story-point>
    <story-point caption='Regional Breakdown' captured-sheet='Regional View' id='2' />
  </story-points>
</story>
```

---

## 9. Formatting & Themes

Formatting is applied via `<style>` blocks at the workbook, dashboard, or worksheet level.

```xml
<preferences>
  <color-palette custom='true' name='Corporate Colors' type='regular'>
    <color>#003366</color>
    <color>#ff9900</color>
  </color-palette>
</preferences>

<style>
  <style-rule element='worksheet'>
    <format attr='font-family' value='Tableau Book' />
    <format attr='font-size' value='10' />
    <format attr='color' value='#333333' />
  </style-rule>
  <style-rule element='axis'>
    <format attr='title-font-weight' value='bold' />
  </style-rule>
</style>
```
- `<format>` tags use a generic `attr` and `value` structure. Number formatting is stored using standard patterns: `<format attr='numbers' value='&quot;$&quot;#,##0.00' />`.

---

## 10. Actions

Actions define interactivity (filtering, highlighting, navigation).

```xml
<dashboard>
  <actions>
    <action caption='Filter by Region' id='1'>
      <activation auto-clear='true' type='on-select' />
      <source dashboard='Executive Summary' type='sheet' worksheet='Map View' />
      <command command='tsc:tsl-filter'>
        <param name='special-fields' value='all' />
        <param name='target' value='Executive Summary' />
      </command>
    </action>
    <action caption='URL Action' id='2'>
      <activation type='on-select' />
      <source dashboard='Executive Summary' type='sheet' worksheet='Customer List' />
      <command command='url'>
        <param name='url' value='https://crm.example.com/customer/<[Customer ID]>' />
      </command>
    </action>
  </actions>
</dashboard>
```
- `command='tsc:tsl-filter'`: Filter action.
- `command='tsc:tsl-highlight'`: Highlight action.
- `command='url'`: URL action.

---

## 11. Maps

Maps involve coordinate mapping and layer definitions.

```xml
<mapsources>
  <mapsource name='Tableau Map'>
    <connection class='ext-map' />
  </mapsource>
</mapsources>
<worksheet>
  <table>
    <view>
      <map>
        <format attr='map-style' value='light' />
        <format attr='map-layers' value='base,land,water' />
      </map>
    </view>
    <panes>
      <pane>
        <mark class='Map' />
      </pane>
    </panes>
    <rows>[federated.1a2b3c].[avg:Latitude (generated):qk]</rows>
    <cols>[federated.1a2b3c].[avg:Longitude (generated):qk]</cols>
  </table>
</worksheet>
```
Tableau automatically generates `Latitude (generated)` and `Longitude (generated)` for fields assigned geographic roles (e.g., `<column name='[State]' role='dimension' semantic-role='[State].[Name]' type='nominal' />`).

---

## 12. Images, Extensions, Tooltips

### Images
Images in dashboards are basic zones with a base64 encoded payload in a `<formatted-text>` tag, or external references.
```xml
<zone type='bitmap' param='Image/logo.png' />
```

### Extensions
Extensions use dashboard zones referencing a `.trex` manifest file.
```xml
<zone type='extension' extension-url='https://extensions.tableau.com/myapp.trex' />
```

### Tooltips
Tooltips use XML encoded HTML/Rich-Text. Viz-in-Tooltip embeds sheet references.
```xml
<tooltip>
  <format attr='tooltip-parameters' value='&lt;Sheet name=&quot;Tooltip Trend&quot; maxwidth=&quot;300&quot; maxheight=&quot;200&quot; filter=&quot;&lt;All Values&gt;&quot;&gt;' />
  <formatted-text>
    <run>Sales for </run>
    <run bold='true'><![CDATA[<[Region]>]]></run>
    <run>: </run>
    <run><![CDATA[<[sum:Sales:qk]>]]></run>
  </formatted-text>
</tooltip>
```

---

*This document covers the exhaustive structure required for migrating, editing, or programmatically parsing Tableau workbooks based on real-world XML patterns.*
