import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent.parent/'scripts'))
from build_ontario_wildfire_intelligence import tier
def test_ontario_tier_boundaries():
    assert tier(0)=="NORMAL_OPERATION" and tier(.8)=="EMERGENCY_RESPONSE"
