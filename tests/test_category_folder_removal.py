import pdfsorter as P


class _Tree:
    def selection(self):
        return ("selected",)

    def item(self, _row, _option):
        return ("Invoices/Received",)


class _Rules:
    def __init__(self, category):
        self.category = category
        self.saved = 0

    def get(self, _name):
        return self.category

    def save(self):
        self.saved += 1


class _Label:
    def configure(self, **kwargs):
        self.text = kwargs["text"]


class _Messages:
    @staticmethod
    def askyesno(*_args, **_kwargs):
        return True

    @staticmethod
    def showinfo(*_args, **_kwargs):
        pass

    @staticmethod
    def showerror(*_args, **_kwargs):
        raise AssertionError("Unexpected removal error")


def test_remove_folder_preserves_files_cleans_mapping_and_rescans_pdfs(tmp_path):
    output = tmp_path / "archive"
    created = output / "Acme" / "2025" / "Invoices" / "Received"
    nested = created / "nested"
    nested.mkdir(parents=True)
    pdf = nested / "invoice.pdf"
    pdf.write_bytes(b"pdf-content")
    other = created / "notes.txt"
    other.write_text("keep me", encoding="utf-8")
    (created.parent / "invoice.pdf").write_bytes(b"existing file")

    category = {
        "name": "Acme", "folder": "Acme",
        "subfolder_keyword_map": {
            "invoice": "Invoices/Received",
            "receipt": "Invoices/Received/Old",
            "other": "Other",
        },
    }
    app = object.__new__(P.App)
    app.settings = {"output_dir": str(output)}
    app.rules = _Rules(category)
    app._selected_cat = lambda: "Acme"
    app.subfolder_map_tree = _Tree()
    app.lbl_subfolder_map_status = _Label()
    app.messagebox = _Messages()
    app.root = object()
    app._rescanning = False
    app._category_subfolder_mapping_base = lambda _cat: output / "Acme" / "2026"
    app._refresh_subfolder_map = lambda: None
    app._start_rescan_files = lambda files, cat: setattr(
        app, "rescan_request", (files, cat))

    P.App._cat_map_remove_folder(app)

    assert not created.exists()
    assert (created.parent / "invoice.pdf").read_bytes() == b"existing file"
    assert (created.parent / "invoice (2).pdf").read_bytes() == b"pdf-content"
    assert (created.parent / "notes.txt").read_text(encoding="utf-8") == "keep me"
    files, cat_name = app.rescan_request
    assert files == [created.parent / "invoice (2).pdf"]
    assert cat_name == "Acme"
    assert category["subfolder_keyword_map"] == {"other": "Other"}
    assert app.rules.saved == 1
    assert "PDF-filer skannas om" in app.lbl_subfolder_map_status.text


def test_remove_folder_keeps_files_in_each_year_instance_and_collects_all_pdfs(tmp_path):
    output = tmp_path / "archive"
    first = output / "Acme" / "2024" / "Invoices" / "Received"
    second = output / "Acme" / "2025" / "Invoices" / "Received"
    first.mkdir(parents=True)
    second.mkdir(parents=True)
    (first / "a.pdf").write_bytes(b"year 1")
    (second / "b.pdf").write_bytes(b"year 2")
    app = object.__new__(P.App)
    app.settings = {"output_dir": str(output)}
    app._category_subfolder_mapping_base = lambda _cat: output / "Acme" / "2026"

    files = P.App._remove_category_mapping_folder(
        app, {"folder": "Acme"}, "Invoices/Received")

    assert not first.exists() and not second.exists()
    assert (first.parent / "a.pdf").read_bytes() == b"year 1"
    assert (second.parent / "b.pdf").read_bytes() == b"year 2"
    assert set(files) == {first.parent / "a.pdf", second.parent / "b.pdf"}
