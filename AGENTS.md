# AGENTS.md — Hårda regler och arbetsflöde för ArkivPiloten

Detta dokument sammanfattar projektets stående regler (anpassade efter ArkivPiloten) så att varje ny chatt- eller kodagentomgång följer dem direkt utan att förlita sig på chattminne.

---

## 1. Git, grenar, merge och regelsparande (HÅRDA REGLER)

- **Endast en aktiv branch — arbeta aldrig mot `main` (hård regel):**
  - Endast en branch ska finnas i repot (`arena/317ae491-arkivpiloten`), och allt arbete samt alla pushar sker **endast** mot den aktiva grenen.
  - Arbeta **aldrig** mot `main` — särskilt inte vid appuppdateringar (uppdateraren hämtar alltid via GitHub Releases, aldrig från `main` eller annan gren).
- **Aldrig merga (hård regel):**
  - Merga aldrig grenar eller pull requests (`git merge`, `gh pr merge`).
- **Skriv alltid nya regler till GitHub (hård regel):**
  - När användaren skriver **`- hård regel`** eller **`regel`** i chatten ska den regeln alltid läggas in här i `AGENTS.md` på GitHub (commit + push till den aktiva grenen, följt av release- och CI-kontroll).
- **Anpassa regler efter varje app:**
  - Generella regler från användarens standardlista tillämpas utifrån ArkivPilotens faktiska arkitektur; delar från andra appar (t.ex. projektskapare eller användarprofiler under Inställningar) införs inte utan uppdrag.

---

## 2. Release och autouppdatering (HÅRD REGEL)

- **Uppdatera alltid GitHub-releasen vid varje kodändring + markera som `Latest` (hård regel):**
  - `.github/workflows/release.yml` körs vid varje kodpush till den aktiva grenen, bygger färskt paket via `python tools/build_release.py --out dist`, flyttar/skapar taggen `v$VERSION` till `$GITHUB_SHA`, laddar upp alla release-filer med `--clobber`, bäddar in `dist/BUILD-MANIFEST.json` i release-texten och kör alltid:
    ```bash
    gh release edit "$TAG" --latest --target "$GITHUB_SHA" --title "ArkivPiloten $VERSION" --notes-file ...
    ```
  - Ta aldrig bort `--latest`, tagg-flytten eller manifest-inbäddningen.
- **Säker uppdatering med filjämförelse & automatisk backupstädning:**
  - `pdfsorter_system.py` (`check_for_update`, `_compare_manifest_to_local`, `_valid_build_manifest`, `_safe_extract`) jämför lokala filer/SHA-256-hashar och release-commit mot `Latest`-releasen även när versionsnumret är oförändrat, verifierar `SHA256SUMS.txt` + `BUILD-MANIFEST.json` + kompilering/versioner före skrivning och rullar tillbaka atomärt vid fel.
  - När en uppdatering har startat om och verifierats (`mark_update_verified()`) tas uppdateringens säkerhetskopia bort automatiskt (`_remove_verified_backup_dir()`).
  - Håll `APP_VERSION` / `VERSION` identisk i alla `pdfsorter*.py`-moduler (`pdfsorter.py`, `pdfsorter_data.py`, `pdfsorter_read.py`, `pdfsorter_system.py`, `pdfsorter_theme.py`, `pdfsorter_diag.py`).
  - Ändras `UPDATE_FILES` / `UPDATE_CONTENT_FILES` i `pdfsorter_system.py` ska `tools/build_release.py` och `tools/install_latest.py` (`FILES`) uppdateras samtidigt.
- **Verifiera efter push:**
  - Vänta in både `.github/workflows/release.yml` och `.github/workflows/tests.yml` (alla OS/Python-matriser) med `gh run watch` / `gh run list`.
  - Bekräfta med `gh release list`, `gh release view` och `gh api .../branches` att endast den aktiva grenen finns, att releasen står som **`Latest`** på `HEAD` och att alla filhashar i manifestet stämmer.

---

## 3. Förslag, kravstyrning och chattkommandon (`REQ-K1`–`REQ-K6`)

- **`REQ-K4` (hård regel) — inget byggs utan order:**
  - Förslag i `PDFSORTER_FORSLAG.md` och `PDFSORTER_SPEC.md` med status `VÄNTAR` eller `KOMMANDE` får **aldrig** implementeras automatiskt. Vänta alltid på explicit order (t.ex. `kör <nummer>` eller `bygg <nummer>`).
  - Markera färdigbyggda förslag tydligt som **`KLAR (YYYY-MM-DD)`** i `PDFSORTER_FORSLAG.md`.
- **Cykelregel (`REQ-K2` + 10-meddelanderegel):**
  - Efter var **10:e chattmeddelande** (samt efter var 10:e koduppdateringscykel) ska **10 helt nya, ej återbrukade förbättringsförslag** visas i chatten och loggas i `PDFSORTER_FORSLAG.md` under nästa Omgång (`VÄNTAR`).
- **Styrande tangentord i chatt:**
  - `förslag` → ta fram upp till 25 nya förbättringsförslag (som konkurrenter saknar och användare efterfrågar) brett över kod, design, minne, snabbhet, matchning och robusthet (`REQ-K1`/`REQ-K3`).
  - `lista` → visa grupperad checklista över `KOMMANDE`-krav (`REQ-N*`) och `VÄNTAR`-förslag (`REQ-K5`).
  - `forskning` → genomför omvärldskoll av liknande PDF-/dokumentappar och ge rekommendationer, utan att implementera något innan val (`REQ-K6`).

---

## 4. Loggning, startbeteende, UI, minne och säkerhet

- **Loggarkivering (7 dagar) & aktiv fellogg:**
  - Gårdagens app-loggar arkiveras automatiskt och arkiverade loggar äldre än 7 dagar raderas automatiskt (`archive_old_logs()`, `purge_archived_logs(7)`).
  - Det ska finnas en komplett app-logg samt en aktiv fellogg (`errors.jsonl` / felloggsrapportering) med alla aktiva fel; när ett fel åtgärdats rensas det bort ur den aktiva felloggen (automatiskt vid hälsokoll samt manuellt via GUI/CLI `mark_error_code_resolved`).
- **Konsolfri drift & minimerad start:**
  - Inget terminalfönster får visas varken vid start (`pdfsorter.pyw`) eller vid bakgrundsskanning/OCR (`CREATE_NO_WINDOW`).
  - Appen startar alltid minimerad till systemfältet (med taskbar-reserv).
- **Skärmanpassning, skärpa, design & tabeller:**
  - Skarpa typsnitt, hög/dynamisk per-skärms-DPI (`#237`), anpassad fönsterlayout för olika skärmar med minimal scrollning och enhetlig, skarp varumärkesgrafik överallt (`ArkivPiloten.png`, `ArkivPiloten.ico`, rena redigerbara vektor-SVG:er inklusive tryckvektor `brand/arkivpiloten-print.svg`, `pdfsorter_system.py`, `pdfsorter_theme.py`).
  - Tabeller med flera kolumner stöder anpassning/omordning och sparade bredder (och kolumnsortering där det stöds).
- **Minne, snabbhet, energisnålhet & kärnregler:**
  - Begränsade cacher, stängda PDF-handtag, minimal idle-belastning.
  - Körbart utan installation (`python pdfsorter.py` / `pythonw pdfsorter.pyw`); `pdfsorter_system.py` och `pdfsorter_theme.py` är valfria vid körning.
  - Automatisk flytt (`auto`) endast efter ≥ 100 manuellt bekräftade filer i kategorin **och** ≥ 2 exklusiva exakta stödord i dokumenttexten, med SHA-256-kontroll före flytt.
  - Användardata sparas endast under `config_dir()`; committa aldrig användarspecifik `settings.json`, temporära bilder/loggar, `.venv` eller `dist/`.
  - Alla tester och kodändringar måste fungera på Windows, macOS och Linux (Python 3.10+).

---

## 5. Kvalitetskontroll innan arbetet förklaras klart

Kör alltid lokalt innan commit/push:

1. `git diff --check`
2. `python -m py_compile` på ändrade Python-filer
3. `ruff check .` (enligt `pyproject.toml`)
4. `pytest -q` (hela testsviten)
5. `PDFSORTER_HOME=<tmp> python pdfsorter.py --ai-rapport` (`FEL: 0`)

Efter push till GitHub: verifiera att endast en branch finns kvar, att både **`release`** och **`tests`** går igenom 100 % grönt och att **`Latest`**-releasen pekar på senaste commit.
