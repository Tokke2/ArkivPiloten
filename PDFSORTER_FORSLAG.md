# ArkivPiloten — Förslagslogg
> Alla förslag är **VÄNTAR** tills du säger `kör <nummer>` eller `bygg <nummer>`.  
> Inget implementeras automatiskt (REQ-K4). Status: **VÄNTAR = ej påbörjad**.

Aktuell release på GitHub: **v1.0.0** (låst tills du säger annat — inga nya taggar skapas).

---

## Omgång 9 (2026-10-19) — 25 nya förbättringar: kod, design, minne, snabbhet, matchning, robusthet

| # | Titel | Klass | Beskrivning (1–2 meningar + nytta) |
|---|---|---|---|
| 202 | Live-förhandsvisning av målsökväg | Design | I granskningsrutan visas exakt målsökväg `Pilkington/2025/fil.pdf` live när du väljer kategori. Slipper gissa år/månad — färre fel, tryggare klick. |
| 203 | QR-/streckkod som starkt ID | Matchning | Skanna QR och Code128/EAN i PDF (via pyzbar) och extrahera org.nr/fakturanr som `kod`/`orgnr` med vikt 3.0. Fångar moderna fakturor där ID:t bara ligger i koden. |
| 204 | E-postbilaga-import (.eml/.msg) | Ny funktion | Bevaka inkorgen även för e-postfiler: plocka ut PDF-bilagor, läs avsändardomän + bilagenamn och sortera direkt. Sparar manuellt sparande från Outlook/Thunderbird. |
| 205 | Årsrimlighet + fallback med varning | Robusthet | Om dokumentdatum är framtid eller <2000: flagga gult och använd filens `mtime` i stället för fel år. Förhindrar att 2035-fil hamnar i fel årsmapp. |
| 206 | Mappmallar per kategori | Ny funktion | Varje kategori kan ha egen subfolder-mall: `Pilkington/{år}/Fakturor`, `Avtal/{år}-{månad}`. Mer ordning utan att ändra global mall. |
| 207 | Regeltestare — klistra text → se vinnare | Kod / Felsökning | Ny ruta: klistra in fritext/mening → kör `score_text` torrt och visa vinnare + poäng per kategori + varför. Perfekt för att trimma stödord utan att skapa filer. |
| 208 | Jämför två PDF:er sida-vid-sida | Design | Markera 2 filer i Historik/Kö → ”Jämför” öppnar diff-vy med text sida-vid-sida + hash. Snabb dubblettkontroll innan ersätt/behåll-båda. |
| 209 | Shell-kontextmeny: ”Sortera med ArkivPiloten” | System | Högerklick på PDF i Utforskaren → snabb sortering via headless `--input` utan att öppna huvudfönstret. Sparar 5 klick per fil. |
| 210 | Batch-ångra med progress | Design / Robusthet | Markera 20+ rader i Historik → Ångra alla med en bekräftelse + progressbar + rapport (lyckade/missade/låsta). Säkrare massåterställning. |
| 211 | Export till Excel/CSV med filter | Ny funktion | Historik → Exportera med kolumnväljare + datumspann + kategori-filter → `.xlsx/.csv`. Underlättar revision och månadsavstämning. |
| 212 | Hälsopil per kategori (auto/ask-ratio) | Matchning / Design | På Matchningar-fliken: grön/gul/röd pil per kategori baserat på senaste 30 dagars auto-vs-ask. Klick ger direkt förslag: lägg till ord / höj vikt. |
| 213 | Live UI-zoom Ctrl + / Ctrl − | Design / Tillgänglighet | Zooma hela gränssnittet 90–150 % live (utöver HiDPI-auto). Hjälper på små skärmar och för synsvaga — sparas i `settings[ui_zoom]`. |
| 214 | Offline OCR-språkhanterare | OCR / Robusthet | Ny vy visar installerade `*.traineddata` (swe/eng/deu/fin) + ”Hämta språk” som laddar från tessdata GitHub till rätt mapp utan winget. Fungerar offline efteråt. |
| 215 | Spegling till sekundär disk/USB vid avslut | Robusthet | Vid avslut: kopiera nya filer i Utmappen till backup-mapp (valfri). Tyst, verifierad med hash — ingen fil förloras om primär disk dör. |
| 216 | Dölj skräpprefix i visning | Design | Historik/Kö visar rensat namn (`scan_001_faktura.pdf` → `faktura.pdf`) men behåller filnamn på disk. Lättare att skumma långa listor. |
| 217 | Notishistorik (sökbar) | Felsökning | Alla systemnotiser + tray-bubblor loggas i egen flik med tid/kategori/sök. Missar aldrig ”fil väntar på granskning”-bubblan. |
| 218 | p95-prestanda per steg i Diagnostik | Snabbhet / Kod | Diagnostik visar median/p95 för läs/OCR/matcha/flytt över senaste 100 filer. Ser direkt vilken motor som är flaskhals. |
| 219 | Säker radering (överskriv källa) | Robusthet / GDPR | Val vid radering efter kopiering: skriv över källfilen (1-pass) innan unlink. För känsliga PDF:er som inte ska gå att återskapa. |
| 220 | Favoritkategorier med snabbval 1–5 | Design / Snabbhet | Stjärnmärk kategori → alltid överst + `Ctrl+1..5` väljer direkt i granskningsdialogen. 80 % av filerna hör till 2–3 kategorier — stor tidsvinst. |
| 221 | XMP Dublin Core-taggning | Avläsning | Utöver `Keywords/Subject` skriv även `dc:title/dc:creator/xmp:CreateDate`. Gör filerna sökbara i Spotlight, Windows Search och Adobe Bridge. |
| 222 | Nattläge på schema | Design | Växla tema automatiskt efter klockan (t.ex. mörkt 19–07) eller följ OS (utökar L4). Sparas som `theme_schedule`. Mindre ögonstress kvällstid. |
| 223 | Importera regler från konkurrent | Kod / Migration | Läs CSV/JSON från t.ex. Paperless-ngx / FileCenter → konvertera till `rules.json` med förhandsvisning + krockrapport. Sänker tröskeln att byta. |
| 224 | Tyst torka: auto-rensa cache/backups | Minne / Ordning | Städa `cache/`, `updates/staging`, `backups/` äldre än N dagar (standard 60) — med förhandsvisning ”vad rensas” innan. Ingen diskläcka över tid. |
| 225 | Smart datum från filnamn före OCR | Snabbhet / Matchning | Tolka datum i filnamn (`2025-08-14_faktura.pdf`, `140825`) innan tung OCR. Ger korrekt årsmapp snabbare och utan att läsa filen. |
| 226 | Första-starten wizard (3 steg) | Design / Enkelhet | Ny användare möts av wizard: 1) välj In/Ut-mapp 2) testa en exempelfil live 3) klar. Ersätter tomt läge där inget händer — 2 min till första sortering. |

### Redan i kön (ur spec Bilaga A + äldre — oförändrade)
VÄNTAR-förslag 1–175, 176–201 och F1–F7 ligger kvar i `PDFSORTER_SPEC.md` Bilaga A.  
Skriv `lista` för komplett checklista, `forskning` för omvärldskoll.

### Hur du väljer
Skriv t.ex. `kör 203` eller `bygg 202+207` — då flyttas de till KOMMANDE (REQ-N*) och implementeras först efter din explicita order (REQ-K4).  
Allt förblir **VÄNTAR** tills du säger till. Version stannar på **v1.0.0** tills du beordrar annat.

---
*Genererad 2026-10-19 från kodgranskning (7731 rader huvudmodul, polling-watcher, TextCache 800/24 MB, mypy/CI saknas, native watcher saknas, 200+ VÄNTAR i kön).*
