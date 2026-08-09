# Perplexity research brief: WAIFINDERS hazard registry

Find the **current authoritative, downloadable GIS source** for each registry
layer below. Return only government, intergovernmental, or named scientific
agency sources. Do not use blogs, map screenshots, commercial summaries, or
unverifiable aggregators.

For each layer, provide: canonical landing page; direct current download URL;
format; geographic coverage; date/version; license/terms; update cadence;
field dictionary; and a one-sentence limitation. Confirm the download is still
available today before returning it.

Layers:

1. U.S. active/Quaternary fault line geometry — USGS Quaternary Fault and Fold
   Database.
2. Global subduction-zone geometry relevant to tsunami generation — USGS or
   another named scientific authority.
3. Global historical tsunami source events and observed runup locations —
   NOAA/NCEI HazEL or its documented successor.
4. Global historical tropical-cyclone tracks — NOAA/NCEI IBTrACS, preferably
   a current line shapefile or GeoJSON-ready source.
5. U.S. hurricane and tsunami community risk screening — FEMA National Risk
   Index or its current authoritative successor.
6. For each country or region outside the U.S. represented in the customer
   portfolio, identify the national geological survey, tsunami warning centre,
   and meteorological agency with an official GIS/open-data endpoint.

Output a machine-readable JSON array compatible with
`inputs/hazard_registry_sources.json`: `source_id`, `name`, `authority`,
`hazard_type`, `url`, `download_url`, `format`, `coverage`, `version_or_date`,
`update_cadence`, `license_note`, `field_mapping`, and `limitations`.

Do not label a historical or probabilistic layer as a warning. Clearly separate
fault proximity, historical tsunami/runup evidence, tropical-cyclone history,
and official live alerts.
