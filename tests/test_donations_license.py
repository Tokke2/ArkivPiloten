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


def test_donation_view_has_fixed_qr_and_payment_buttons_only():
    source = inspect.getsource(P.App._visa_stod)

    assert "swish_payload(self.DONATION_SWISH_NUMBER)" in source
    assert P.swish_payload(P.App.DONATION_SWISH_NUMBER) == (
        "https://app.swish.nu/1/p/sw/?sw=46721817177")
    assert "amt=" not in P.swish_payload(P.App.DONATION_SWISH_NUMBER)
    assert P.swish_payload("1234567890") == (
        "https://app.swish.nu/1/p/sw/?sw=1234567890")
    assert P.swish_payload("0721817177", amount=25) == (
        "https://app.swish.nu/1/p/sw/?sw=46721817177&amt=25")
    assert "PayPal" in P.App.STOD_TEXT["sv"]["paypal"]
    assert "Ko-fi" in P.App.STOD_TEXT["sv"]["kofi"]
    assert "amount" not in source.lower()
    assert "ttk.Entry" not in source
    assert "no feature is unlocked by donating" not in str(P.App.STOD_TEXT)


def test_donation_dialog_is_reachable_from_the_help_menu():
    help_menu = next(menu for menu in P.meny_spec()
                     if menu["titel"] == "Hjälp")
    donation_item = next(item for item in help_menu["poster"]
                         if item.get("id") == "stod")

    assert donation_item["text"] == "Stöd projektet 💖"
    assert donation_item["atgard"] == "_visa_stod"
    assert callable(getattr(P.App, donation_item["atgard"]))


def test_donation_page_is_not_shipped_separately():
    source = (ROOT / "pdfsorter_system.py").read_text(encoding="utf-8")
    installer = (ROOT / "tools" / "install_latest.py").read_text(encoding="utf-8")

    assert not (ROOT / "Stöd ArkivPiloten.html").exists()
    assert not (ROOT / "swish_qr.png").exists()
    assert "Stöd ArkivPiloten.html" not in source
    assert "Stöd ArkivPiloten.html" not in installer
    assert "swish_qr.png" not in source
    assert "swish_qr.png" not in installer
    assert '"LICENSE"' in source
    assert '"LICENSE"' in installer
