from tools import verify_release as V


SAMPLE_BODY = """Paket byggt från `822b3a126faa` på `arena/x`.

<!-- ARKIVPILOTEN_BUILD_MANIFEST_BEGIN
{
  "commit": "822b3a126faa5f818429729f72a21d93e538137f",
  "tag": "v1.4.14",
  "version": "1.4.14"
}
ARKIVPILOTEN_BUILD_MANIFEST_END -->

### Har du 1.0.0?
"""


def test_release_tag_prefixes_version_with_v():
    assert V.release_tag("1.4.14") == "v1.4.14"


def test_read_app_version_parses_pdfsorter_without_import(tmp_path):
    (tmp_path / "pdfsorter.py").write_text(
        '"""x"""\nAPP_VERSION = "9.9.9"\n', encoding="utf-8")

    assert V.read_app_version(tmp_path) == "9.9.9"


def test_extract_build_manifest_returns_manifest_dict():
    manifest = V.extract_build_manifest(SAMPLE_BODY)

    assert manifest["commit"] == "822b3a126faa5f818429729f72a21d93e538137f"
    assert manifest["tag"] == "v1.4.14"


def test_manifest_commit_returns_empty_string_when_missing():
    assert V.manifest_commit("inga markörer här") == ""
    assert V.manifest_commit("") == ""
    assert V.extract_build_manifest(
        "<!-- ARKIVPILOTEN_BUILD_MANIFEST_BEGIN\n{trasig\n"
        "ARKIVPILOTEN_BUILD_MANIFEST_END -->") == {}


def test_select_run_for_sha_matches_full_and_short_sha():
    runs = [
        {"databaseId": 2, "headSha": "aaaaaaa1111111"},
        {"databaseId": 1, "headSha": "822b3a126faa5f818429729f72a21d93e538137f"},
    ]

    assert V.select_run_for_sha(
        runs, "822b3a126faa5f818429729f72a21d93e538137f")["databaseId"] == 1
    assert V.select_run_for_sha(runs, "822b3a126faa")["databaseId"] == 1
    assert V.select_run_for_sha(runs, "bbbbbbb") is None
    assert V.select_run_for_sha([], "822b3a126faa") is None
    assert V.select_run_for_sha(runs, "") is None
