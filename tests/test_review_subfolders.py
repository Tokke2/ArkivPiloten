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
