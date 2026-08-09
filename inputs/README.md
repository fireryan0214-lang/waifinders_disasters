# Customer asset upload

Copy `assets.template.csv` to `assets.csv`, then add one row for every asset to monitor.

Required fields: `asset_id`, `name`, `asset_type`, `lat`, `lon`, `criticality`, and `population_served`.

`asset_type` may be `facility`, `bridge`, `substation`, `shelter`, `route`, `hospital`, `water`, or `wastewater`. `criticality` must be `low`, `medium`, `high`, or `critical`.

`flood_gauge_id` is optional. Add a USGS site number to enable that asset's live river-gauge monitoring.

Run `python scripts/live_incident_exposure.py` after replacing the template with the customer inventory, then `python scripts/build_sentinel_live_operations.py` to render Sentinel.

Do not put credentials, personal health information, or evacuation lists in this file.
