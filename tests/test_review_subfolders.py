import pdfsorter as P


def test_review_subfolder_choices_list_existing_folders_to_two_levels(tmp_path):
    base = tmp_path / "Archive" / "2026"
    (base / "Invoices").mkdir(parents=True)
    (base / "Transactions" / "Payments").mkdir(parents=True)
    (base / "Transactions" / "Deposits").mkdir(parents=True)
    (base / "not-a-folder.pdf").write_text("pdf", encoding="utf-8")

    assert P._existing_subfolder_choices(base) == [
        "Invoices",
        "Transactions",
        "Transactions/Deposits",
        "Transactions/Payments",
    ]


def test_review_subfolder_choices_ignore_missing_base(tmp_path):
    assert P._existing_subfolder_choices(None) == []
    assert P._existing_subfolder_choices(tmp_path / "missing") == []


def test_sibling_year_choices_follow_all_years_own_first(tmp_path):
    root = tmp_path / "Bank"
    (root / "2025" / "Utbetalningar").mkdir(parents=True)
    (root / "2024" / "Transaktioner").mkdir(parents=True)
    (root / "2024" / "Utbetalningar").mkdir(parents=True)
    (root / "2026" / "Kvitton" / "Resor").mkdir(parents=True)

    choices = P._sibling_year_subfolder_choices(root, root / "2025")

    assert choices == ["Utbetalningar", "Kvitton", "Kvitton/Resor",
                       "Transaktioner"]


def test_sibling_year_choices_mirror_category_subfolder(tmp_path):
    root = tmp_path / "Bank"
    (root / "2025" / "Kvitton").mkdir(parents=True)
    (root / "2024" / "Kvitton" / "Resor").mkdir(parents=True)

    choices = P._sibling_year_subfolder_choices(root, root / "2025" / "Kvitton")

    assert choices == ["Resor"]


def test_sibling_year_choices_include_utan_datum(tmp_path):
    root = tmp_path / "Bank"
    (root / "2025").mkdir(parents=True)
    (root / "Utan datum" / "Okänt").mkdir(parents=True)

    assert P._sibling_year_subfolder_choices(root, root / "2025") == ["Okänt"]


def test_sibling_year_choices_ignore_non_year_dirs_and_bad_paths(tmp_path):
    root = tmp_path / "Bank"
    (root / "2025").mkdir(parents=True)
    (root / "GammalMapp" / "BordeInteSynas").mkdir(parents=True)

    assert P._sibling_year_subfolder_choices(root, root / "2025") == []
    # Basen är roten (årsmappar avstängda): rotens egna mappar listas.
    assert P._sibling_year_subfolder_choices(root, root) == [
        "2025", "GammalMapp", "GammalMapp/BordeInteSynas"]
    assert P._sibling_year_subfolder_choices(None, root / "2025") == []
    assert P._sibling_year_subfolder_choices(root, None) == []
    assert P._sibling_year_subfolder_choices(root, tmp_path / "utanför") == []
    assert P._sibling_year_subfolder_choices(
        tmp_path / "saknas", tmp_path / "saknas" / "2025") == []


def _refresh_stub(resolver, base, typed=""):
    from types import SimpleNamespace

    seen = {}

    class Combo:
        def configure(self, **kwargs):
            seen.update(kwargs)

    stub = SimpleNamespace(
        subfolder_combo=Combo(),
        subfolder_choices_resolver=resolver,
        var_subfolder=SimpleNamespace(get=lambda: typed),
        _category=lambda: "Bank",
        _subfolder_base=lambda: base,
    )
    P.ReviewDialog._refresh_subfolder_options(stub)
    return seen.get("values")


def test_refresh_uses_choices_resolver_and_keeps_typed_value():
    values = _refresh_stub(lambda _cat: ["A", "B"], None, typed="Ny mapp")

    assert values == ["Ny mapp", "A", "B"]


def test_refresh_falls_back_to_base_listing(tmp_path):
    base = tmp_path / "2025"
    (base / "Lokal").mkdir(parents=True)

    assert _refresh_stub(None, base) == ["Lokal"]

    def broken(_cat):
        raise RuntimeError("trasig resolver")

    assert _refresh_stub(broken, base) == ["Lokal"]
