# -*- coding: utf-8 -*-
"""Export/import av regler: validering, säker sammanslagning, menyvägar."""
import pdfsorter as P
import pdfsorter_data as D


def _rules(tmp_path, categories):
    return D.Rules({"categories": categories}, path=tmp_path / "rules.json")


# -- validering ------------------------------------------------------------
def test_validate_rejects_non_dict_and_empty_files():
    cats, error = P.validate_rules_transfer(["inte", "dict"])
    assert cats == [] and error

    cats, error = P.validate_rules_transfer({})
    assert cats == [] and "inga kategorier" in error

    cats, error = P.validate_rules_transfer({"categories": [{"namn": "saknar namn"}]})
    assert cats == [] and error


def test_validate_normalizes_keywords_and_drops_nameless(tmp_path):
    data = {"schema_version": 1,
            "categories": [{"name": "Bank", "keywords": ["lön", {"text": "OCR", "weight": 3}]},
                           {"name": "  "}]}

    cats, error = P.validate_rules_transfer(data)

    assert error == ""
    assert [c["name"] for c in cats] == ["Bank"]
    assert cats[0]["keywords"][1]["weight"] == 3.0


# -- sammanslagning --------------------------------------------------------
def test_merge_creates_new_category_and_preserves_weights(tmp_path):
    rules = _rules(tmp_path, [])

    counts = rules.merge_transfer_categories(
        [{"name": "Bank", "folder": "Banken",
          "keywords": [{"text": "ocr", "weight": 3, "whole_word": False,
                        "hits": 42, "source": "user"}]}])

    assert counts == {"new_categories": 1, "new_keywords": 1,
                      "updated_categories": 0}
    cat = rules.get("bank")
    assert cat["folder"] == "Banken"
    word = cat["keywords"][0]
    assert (word["weight"], word["whole_word"], word["source"]) == (3.0, False, "user")
    assert word["hits"] == 0  # har aldrig matchat på den här datorn


def test_merge_keeps_local_learning_and_folder_names(tmp_path):
    rules = _rules(tmp_path, [
        {"name": "Bank", "folder": "MinBank",
         "keywords": [{"text": "lön", "weight": 2.5, "hits": 9}],
         "subfolder": "gammal", "min_keywords": 4}])

    counts = rules.merge_transfer_categories(
        [{"name": "BANK", "folder": "AnnanMapp",
          "keywords": [{"text": "lön", "weight": 1.0, "hits": 100},
                       {"text": "giro", "weight": 2.0}],
          "default_keyword": "giro",
          "subfolder": "ny", "subfolder_path": "Kvitton",
          "subfolder_keyword_map": {"giro": "Kvitton"},
          "subfolder_templates": [{"folder": "Kvitton"}],
          "min_keywords": 2}])

    assert counts == {"new_categories": 0, "new_keywords": 1,
                      "updated_categories": 1}
    cat = rules.get("Bank")
    assert cat["folder"] == "MinBank"  # importen döper aldrig om lokalt
    lon = next(kw for kw in cat["keywords"] if kw["text"] == "lön")
    assert (lon["weight"], lon["hits"]) == (2.5, 9)
    assert cat["default_keyword"] == "giro"  # tomt lokalt -> fylls på
    assert cat["subfolder_keyword_map"] == {"giro": "Kvitton"}
    assert cat["subfolder"] == "gammal"  # satt lokalt -> behålls
    assert cat["subfolder_path"] == "Kvitton"  # tomt lokalt -> fylls på
    assert cat["subfolder_templates"] == [{"folder": "Kvitton"}]
    assert cat["min_keywords"] == 4  # lokalt värde vinner


def test_merge_ignores_garbage_entries(tmp_path):
    rules = _rules(tmp_path, [])

    counts = rules.merge_transfer_categories(
        [None, "x", {"name": "  "}, {"name": "Ok", "keywords": [None, 7]}])

    assert counts["new_categories"] == 1
    assert rules.get("Ok")["keywords"] == []


# -- menyvägar -------------------------------------------------------------
def test_export_and_import_are_reachable_from_the_menu():
    poster = {post["id"]: post for meny in P.meny_spec()
              for post in meny["poster"] if post.get("id")}

    assert poster["exportera_regler"]["atgard"] == "_export"
    assert poster["importera_regler"]["atgard"] == "_import"
    assert poster["exportera_regler"]["snabb"] == "Ctrl+E"
    assert poster["importera_regler"]["snabb"] == "Ctrl+I"
