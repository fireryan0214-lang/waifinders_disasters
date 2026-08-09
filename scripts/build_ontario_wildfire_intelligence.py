"""Ontario live wildfire decision-support output using official AFFES map layers."""
import json
import math
from datetime import datetime, timezone

import requests

from live_incident_exposure import ROOT, clamp, haversine_km

OUT = ROOT / "outputs" / "wildfire" / "sentinel" / "ontario_sentinel_intelligence.json"
BASE = "https://ws.lioservices.lrc.gov.on.ca/arcgis1/rest/services/MNRF/Ontario_Fires_Map/MapServer"

def fetch(layer):
    r = requests.get(f"{BASE}/{layer}/query", params={"where":"1=1","outFields":"*","returnGeometry":"true","f":"geojson","outSR":4326}, headers={"User-Agent":"WAIFINDERS-Sentinel/0.1"}, timeout=45)
    r.raise_for_status(); return r.json().get("features", [])

def tier(score):
    return "EMERGENCY_RESPONSE" if score >= .75 else "MITIGATION_REQUIRED" if score >= .5 else "MONITOR" if score >= .25 else "NORMAL_OPERATION"

def main():
    fires, weather = fetch(32), fetch(30)
    # PM readings contain the daily Canadian FWI components.  Retain only the
    # latest observation per station with a usable FWI value.
    stations = {}
    for feature in weather:
        p = feature["properties"]; key = p.get("WEATHER_STATION_CODE")
        if key and p.get("FWI") is not None and (key not in stations or p.get("DFOSS_WEATHER_DATE", 0) > stations[key]["properties"].get("DFOSS_WEATHER_DATE", 0)):
            stations[key] = feature
    scored = []
    for feature in fires:
        p = feature["properties"]; lon, lat = feature["geometry"]["coordinates"][:2]
        nearest = min(stations.values(), key=lambda station: haversine_km(lat, lon, station["geometry"]["coordinates"][1], station["geometry"]["coordinates"][0]), default=None)
        station_p = nearest["properties"] if nearest else {}
        distance = haversine_km(lat, lon, nearest["geometry"]["coordinates"][1], nearest["geometry"]["coordinates"][0]) if nearest else None
        condition = {"Not Under Control":1, "Being Held":.65, "Under Control":.4, "Being Observed":.3}.get(p.get("CONDITION_DESCRIPTION"), .35)
        size = clamp(math.log1p(float(p.get("CURRENT_SIZE") or 0))/math.log(5001))
        fwi = clamp(float(station_p.get("FWI") or 0)/30)
        score = clamp(.42*condition + .23*size + .25*fwi + .10*.95)
        scored.append({"fire_id":p.get("FIRE_NAME"),"district":p.get("DISTRICT_NAME"),"lat":lat,"lon":lon,"condition":p.get("CONDITION_DESCRIPTION"),"size_hectares":p.get("CURRENT_SIZE"),"warn_score":round(score,4),"warn_tier":tier(score),"nearest_station":{"code":station_p.get("WEATHER_STATION_CODE"),"distance_km":round(distance,1) if distance is not None else None,"ffmc":station_p.get("FFMC"),"fwi":station_p.get("FWI"),"isi":station_p.get("ISI"),"bui":station_p.get("BUI")} if nearest else None,"source_url":f"{BASE}/32"})
    peak = max((f["warn_score"] for f in scored),default=0)
    payload={"generated_utc":datetime.now(timezone.utc).isoformat(),"mode":"LIVE_ONTARIO_WILDFIRE_DECISION_SUPPORT","fires":sorted(scored,key=lambda f:-f["warn_score"]),"fire_weather":{"fwi":{"fwi_normalized":round(max((f["nearest_station"]["fwi"] or 0 for f in scored if f["nearest_station"]),default=0)/30,4),"score":round(peak,4),"warn_tier":tier(peak)}},"infrastructure":{"status":"UNAVAILABLE","blocker":"No verified Ontario customer/public infrastructure layer loaded."},"formula":"0.42 official fire condition + 0.23 log-normalized size + 0.25 nearest-station FWI + 0.10 official-source confidence","claim_boundary":"Experimental decision support only; not an Ontario fire warning. Verify Ontario AFFES sources and require trained human approval before action."}
    OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(payload,indent=2)); print(f"Ontario fires scored: {len(scored)}; peak tier: {payload['fire_weather']['fwi']['warn_tier']}")
if __name__=="__main__": main()
