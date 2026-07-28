"""Guards for the HACS custom integration packaging.

These run without Home Assistant installed: they compare files as text and
validate JSON, rather than importing the integration (which needs `homeassistant`).
"""

import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
PKG = ROOT / "ddo_tracker"
INTEGRATION = ROOT / "custom_components" / "ddo_book_tracker"


def test_vendored_core_matches_library():
    # The integration ships a self-contained copy of the core logic (HACS only
    # installs custom_components/). Keep the copies byte-identical so a fix in
    # one never silently diverges from the other.
    for name in ("client.py", "models.py", "catalog.py"):
        assert (INTEGRATION / name).read_text() == (PKG / name).read_text(), (
            f"{name} differs between ddo_tracker/ and the integration; "
            "re-copy it so the two stay in sync."
        )


def test_manifest_is_valid():
    manifest = json.loads((INTEGRATION / "manifest.json").read_text())
    for key in (
        "domain",
        "name",
        "version",
        "config_flow",
        "documentation",
        "codeowners",
        "iot_class",
        "requirements",
    ):
        assert key in manifest, f"manifest.json missing '{key}'"
    assert manifest["domain"] == "ddo_book_tracker"
    assert manifest["config_flow"] is True
    assert manifest["iot_class"] == "cloud_polling"
    assert isinstance(manifest["requirements"], list)


def test_hacs_json_valid():
    hacs = json.loads((ROOT / "hacs.json").read_text())
    assert "name" in hacs


def test_translations_match_strings():
    strings = json.loads((INTEGRATION / "strings.json").read_text())
    en = json.loads((INTEGRATION / "translations" / "en.json").read_text())
    assert strings == en


def test_all_integration_modules_compile():
    import py_compile

    for path in INTEGRATION.glob("*.py"):
        py_compile.compile(str(path), doraise=True)
