from pathlib import Path
import inspect

import pdfsorter as P
from pdfsorter_data import DEFAULT_SETTINGS

ROOT = Path(__file__).resolve().parents[1]


def test_project_license_permits_private_and_commercial_use():
    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert license_text.startswith("MIT License")
    assert "without restriction" in license_text
    assert "sell copies" in " ".join(license_text.split())
    assert "private and commercial use are permitted" in readme
    assert "privat och kommersiell användning är tillåten" in readme


def test_donation_destinations_are_fixed_not_user_settings():
    assert P.App.DONATION_SWISH_NUMBER == "0721817177"
    assert P.App.DONATION_PAYPAL_URL == "https://paypal.me/Rickard3dPrint"
    assert P.App.DONATION_KOFI_URL == "https://ko-fi.com/tokke2"
    assert "swish_number" not in DEFAULT_SETTINGS

    source = inspect.getsource(P.App._visa_stod)
    assert 'self.settings.get("swish_number"' not in source
    assert "DONATION_SWISH_NUMBER" in source
    assert "DONATION_PAYPAL_URL" in source
    assert "DONATION_KOFI_URL" in source


def test_donation_view_uses_optional_amounts_without_tiers_or_priority_claims():
    source = inspect.getsource(P.App._visa_stod)

    assert "(25, 50, 100, 200)" in source
    assert "99999" in source
    assert "39 kr" not in source
    assert "99 kr" not in source
    assert "299 kr" not in source
    assert "most picked" not in source
    assert "prioriterad support" not in source
    assert "no feature is unlocked by donating" in P.App.STOD_TEXT["en"]["amount_note"]
