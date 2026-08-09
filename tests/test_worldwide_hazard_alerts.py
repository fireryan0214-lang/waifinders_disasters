import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from build_worldwide_hazard_alerts import infrastructure_near


def test_infrastructure_radius_is_bounded(monkeypatch):
    class Response:
        def raise_for_status(self): pass
        def json(self): return {"elements": []}
    monkeypatch.setattr("build_worldwide_hazard_alerts.requests.post", lambda *args, **kwargs: Response())
    result = infrastructure_near({"lat": 0, "lon": 0, "match_radius_km": 1000})
    assert result["radius_km"] == 100
