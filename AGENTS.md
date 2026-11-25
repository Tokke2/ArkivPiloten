# AGENTS.md — Hårda regler och arbetsflöde för ArkivPiloten

Detta dokument sammanfattar projektets stående regler så att varje ny kodagent- eller chattomgång följer dem direkt utan att behöva leta i chattminne.

---

## 1. Release och autouppdatering (HÅRD REGEL)

- **Uppdatera alltid GitHub-releasen vid varje kodändring + markera som `Latest`:**
  - `.github/workflows/release.yml` körs vid varje kodpush (`branches: ["**"]`), bygger färskt paket via `python tools/build_release.py --out dist`, flyttar/skapar taggen `v$VERSION` till `$GITHUB_SHA`, laddar upp alla release-filer med `--clobber`, bäddar in `dist/BUILD-MANIFEST.json` i release-texten och kör alltid:
    ```bash
    gh release edit "$TAG" --latest --target "$GITHUB_SHA" --title "ArkivPiloten $VERSION" --notes-file ...
    ```
  - Ändra **aldrig** bort `--latest`, tagg-flytten eller manifest-inbäddningen.
- **Appen jämför filer/hashar och commit via `Latest`-releasen:**
  - `pdfsorter_system.py` (`check_for_update`, `_compare_manifest_to_local`, `_valid_build_manifest`) upptäcker uppdateringar även vid oförändrat versionsnummer genom att jämföra lokala filer/SHA-256-hashar (`UPDATE_CONTENT_FILES` och alla filer i fjärr-manifestet) samt release-commit mot `Latest`-releasen.
  - Höj eller ändra inte versionsnummer utan uttrycklig begäran, men håll alltid `APP_VERSION` / `VERSION` identisk i samtliga `pdfsorter*.py`-moduler (`pdfsorter.py`, `pdfsorter_data.py`, `pdfsorter_read.py`, `pdfsorter_system.py`, `pdfsorter_theme.py`, `pdfsorter_diag.py`).
  - Om en ny distribuerad fil läggs till i paketet måste den finnas konsekvent i `pdfsorter_system.py` (`UPDATE_FILES` / `UPDATE_CONTENT_FILES`), `tools/build_release.py` och `tools/install_latest.py` (`FILES`).
- **Verifiera efter push:**
  - Vänta in både `.github/workflows/release.yml` och `.github/workflows/tests.yml` (alla OS/Python-matriser) med `gh run watch` / `gh run list`.
  - Kontrollera live med `gh release list` och `gh release view` att releasen står som **`Latest`**, att taggen/target-commiten pekar på `HEAD` och att manifestet stämmer mot filerna.

---

## 2. Förslag, kravstyrning och chattkommandon (`REQ-K1`–`REQ-K6`)

- **`REQ-K4` (hård regel) — inget byggs utan order:**
  - Förslag i `PDFSORTER_FORSLAG.md` och `PDFSORTER_SPEC.md` med status `VÄNTAR` (eller `KOMMANDE`) får **aldrig** implementeras automatiskt. Vänta alltid på explicit order (t.ex. `kör <nummer>` eller `bygg <nummer>`).
  - Markera färdigbyggda förslag tydligt som **`KLAR (YYYY-MM-DD)`** i `PDFSORTER_FORSLAG.md`.
- **Cykelregel (`REQ-K2` + 10-meddelanderegel):**
  - Efter var **10:e chattmeddelande** (samt efter var 10:e koduppdateringscykel) ska **10 helt nya, ej återbrukade förbättringsförslag** visas i chatten och loggas i `PDFSORTER_FORSLAG.md` under nästa Omgång (`VÄNTAR`).
- **Styrande tangentord i chatt:**
  - `förslag` → ta fram upp till 25 nya förbättringsförslag brett över kod, design, minne, snabbhet, matchning och robusthet (`REQ-K1`/`REQ-K3`).
  - `lista` → visa grupperad checklista över `KOMMANDE`-krav (`REQ-N*`) och `VÄNTAR`-förslag (`REQ-K5`).
  - `forskning` → genomför omvärldskoll av liknande PDF-/dokumentappar och ge rekommendationer, utan att implementera något innan val (`REQ-K6`).

---

## 3. Arkitektur, matchningssäkerhet och beroenderegler

- **Körbart utan installation och modulär fallback:**
  - Appen måste kunna startas direkt med `python pdfsorter.py` eller `pythonw pdfsorter.pyw`.
  - `pdfsorter_system.py` och `pdfsorter_theme.py` är valfria vid körning: `pdfsorter.py` får inte krascha eller tappa grundfunktion om någon av dem saknas.
- **Hårda matchnings- och flyttgränser:**
  - Automatisk flytt (`auto`) får endast ske när kategorin nått minst 100 manuellt bekräftade filer (`AUTO_MOVE_MANUAL_CONFIRMATIONS`) **och** minst två olika sparade stödord som bara finns i den kategorin matchar exakt i dokumenttexten.
  - Inlärning, lösa poäng, OCR-brus, delord eller streckkods-/ID-träffar får aldrig ensamma utlösa `auto`-flytt.
  - `apply()` och `send_to_unmatched()` måste verifiera filens SHA-256-fingeravtryck före flytt så att ingen förändrad fil flyttas tyst.
- **Appmapp och rena commits:**
  - All körningsdata ligger i undermappar under `config_dir()` (`json/`, `icons/`, `logs/`, `cache/`, `backups/`, `updates/`, `temp/`).
  - Committa aldrig användarspecifik `settings.json`, temporära testfiler, renderade felsökningsbilder, `.venv` eller `dist/`-artefakter.
- **Plattformskrav (Windows, macOS, Linux / Python 3.10+):**
  - All ny kod och alla tester måste fungera på samtliga tre OS i CI-matrisen (t.ex. `PermissionError`-retry vid Windows-fillås, säker hantering av `os.sep` och `ZipInfo.orig_filename` i `_safe_extract()`, HiDPI-skalning och säker Tkinter-nedstängning).
- **Varumärke & ikoner:**
  - Håll `ArkivPiloten.png`, `ArkivPiloten.ico`, `brand/arkivpiloten-icon.svg`, `brand/arkivpiloten-logo.svg`, `brand/arkivpiloten-print.svg`, `pdfsorter_system.py` och `pdfsorter_theme.py` enhetliga (ren vektor i SVG utan `<image>` eller `<text>`).

---

## 4. Kvalitetskontroll innan arbetet förklaras klart

Kör alltid lokalt innan commit/push:

1. `git diff --check`
2. `python -m py_compile` på ändrade Python-filer
3. `ruff check .` (konfigurerad i `pyproject.toml`)
4. `pytest -q` (hela testsviten; inga regressionsfel, inga obefogade skräpfiler i arbetskopian)
5. `PDFSORTER_HOME=<tmp> python pdfsorter.py --ai-rapport` (kontrollera `FEL: 0`)

Efter push till GitHub: verifiera alltid att både **`release`**- och **`tests`**-arbetsflödena går igenom utan fel och att `Latest`-releasen pekar på senaste commit.
