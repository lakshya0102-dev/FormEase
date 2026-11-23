import json
from pathlib import Path


def test_vercel_routes_public_traffic_only_to_next_frontend():
    repository_root = Path(__file__).resolve().parents[2]
    config = json.loads((repository_root / "vercel.json").read_text())

    assert set(config["services"]) == {"frontend"}
    assert config["services"]["frontend"]["root"] == "frontend"
    assert config["rewrites"] == [
        {
            "source": "/(.*)",
            "destination": {"service": "frontend"},
        }
    ]
