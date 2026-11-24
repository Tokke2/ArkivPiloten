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
## Omgång 10 (2026-10-19) — 10 nya förslag: uppdatering, Regeltestare, robusthet

| # | Titel | Klass | Beskrivning (1–2 meningar + nytta) |
|---|---|---|---|
| 227 | Uppdateringshistorik med 1-klicks återställning | Robusthet | Ny vy (Hjälp → Uppdateringar) listar alla `updates/last_update.json` + `backups/update_*`: tid, från→till, filer. Knapp ”Återställ denna” kopierar tillbaka backupen atomärt och loggar — trygg ångra vid felaktig release. |
| 228 | Tray-badge ”↑” när uppdatering finns | Design | När `check_for_update` hittar ny version visas gul ↑-badge på tray-ikonen (som köbrickan) + tooltip ”Ny version X finns”. Syns även när fönstret är gömt — ingen missad uppdatering. |
| 229 | Tyst-fönster för auto-omstart | Robusthet | `silent_restart` sker bara inom ”tyst fönster” (t.ex. 02–04, ställbart) annars skjuts omstart till nästa fönster + tray-notis ”Omstart planerad 03:00”. Undviker att avbryta pågående granskning mitt i dagen. |
| 230 | Spara Regeltest som regressionstest | Kod / Kvalitet | I Regeltestaren: knapp ”Spara som testfall” → skriver `tests/regression_*.json` med inklistrad text + förväntad vinnare + threshold. Nästa `--check` kör alla sparade fall — din trim blir permanent skyddad. |
| 231 | Batch-test i Regeltestaren | Snabbhet | Klistra flera texter (avgränsade med `---` eller tom rad) → kör alla i ett svep och visa tabell: rad 1→ Pilkington 2.3 (auto), rad 2→ fråga (Pilkington/KundAB nära). Ser mönster direkt vid 20 filtyper. |
| 232 | Konfidens-heatmap i Regeltest-inmatningen | Design / Matchning | Markerad text färgas live efter zonvikt: brevhuvud/sender = mörkblå, sidfot = blå, löptext = grå, mottagare = ljusgrå/röd. Du ser omedelbart varför ”Pilkington i mottagarblocket” bara ger 0.30 i vikt. |
| 233 | Quick-fix direkt från Regeltestaren | Enkelhet | När testet visar ”fråga p.g.a. inget bevis” → knapp ”Lägg till ‘556033-9086’ som stödord till Pilkington (vikt 1.0, helt ord)” som skapar regeln direkt via `Rules.add_keywords` + sparar + visar ny poäng live utan att lämna dialogen. |
| 234 | Stor-fil-vakt för jätte-PDF:er | Minne / Robusthet | Innan `read_pdf`: om >500 sidor eller >200 MB → avbryt med tydligt fel ”För stor fil”, lägg i `_StoraFiler` och tipsa om att dela. Hindrar Tesseract-minnesläcka som fryser hela watchern på en enda A0-ritning. |
| 235 | OCR-kö för missad Tesseract | Robusthet | Filer som fick `error: skannad PDF utan OCR` köas i `json/ocr_retry.json`. När Tesseract installeras (via dialogen) körs kön automatiskt om + notis ”12 filer i kö kunde nu läsas”. Ingen fil glöms efter tilläggsinstall. |
| 236 | Globalt kortkommando Ctrl+Skift+R | Enkelhet | Öppnar Regeltestaren omedelbart oavsett flik — även när fönstret är gömt i tray (via `root.bind_all` + tray-menu). Power-user når verktyget på <1s utan mus. |


---
*Omgång 10 genererad 2026-10-19 efter leverans av 207 + autosök 2×/dygn tyst med tyst omstart. Fokus: göra uppdatering synlig/ångerbar och göra Regeltestaren till permanent verktygslåda.*

## Omgång 11 (2026-11-24) — 25 nya skrivbordsförslag: HiDPI, prestanda, minne, OCR, UX och robusthet

| # | Titel | Klass | Status | Beskrivning (1–2 meningar + nytta) |
|---|---|---|---|---|
| 237 | Dynamisk per-skärms-DPI vid fönsterflytt | Design / HiDPI | **KLAR (2026-11-24)** | Lyssna på skärmbyte (`WM_DPICHANGED` / flytt mellan monitorer med olika skalning) och uppdatera Tk-skalning, teckensnitt, radhöjder och ikoner live utan omstart. Ger fortsatt skarpt gränssnitt när fönstret flyttas mellan laptop- och 4K-skärm. |
| 238 | Förrenderings-pipeline för nästa fil i granskningskön | Snabbhet / Design | VÄNTAR | Rendera sida 1 av nästa 1–2 köade PDF-filer i en tyst bakgrundstråd medan användaren granskar aktuell fil och rensa bufferten direkt när kön går vidare. Förhandsvisningen visas omedelbart utan väntetid vid snabb granskning. |
| 239 | Panorerbar zoom (50–300 %) i sidförhandsvisningen | Design / Avläsning | VÄNTAR | Lägg till zoomreglage, `Ctrl` + mushjul och klick-och-dra-panorering direkt på förhandsvisningsduken med vektoromrendering från PyMuPDF i vald upplösning. Låter användaren läsa finstilta org.nr och belopp utan extern PDF-läsare. |
| 240 | Stödordsträffar markerade direkt på sidbild och textutdrag | Design / Matchning | **KLAR (2026-11-24)** | Färgmarkera matchade stödord och starka ID-träffar både i granskningsrutans textutdrag och som tunna markeringar på förhandsvisningsbilden via PyMuPDF `search_for()`. Visar på sekunden varför appen föreslog en kategori. |
| 241 | Begränsad LRU-cache för förhandsvisningsblad | Minne / Snabbhet | VÄNTAR | Håll nyligen renderade sidor i en liten minnesbegränsad LRU (som töms när granskningsdialogen stängs) vid bläddring mellan sida 1–3. Sidbyte och rotation sker direkt utan upprepad PyMuPDF-rendering. |
| 242 | Förkontroll av regelkrockar före batchsortering | Matchning / Felsökning | VÄNTAR | Kör en snabb torr-förhandskoll som flaggar filer där två eller fler kategorier får lika poäng innan flytten startar. Gör att tvetydiga stödord kan justeras på förhand i stället för att fylla granskningskön. |
| 243 | Direktlänk från matchat ord i Granska till stödordsregeln | Enkelhet / Design | **KLAR (2026-11-24)** | Klicka på ett matchat stödord i granskningsdialogen för att hoppa direkt till just den raden under Kategorier (ändra vikt, helt ord eller ta bort). Sparar många klick när ett för brett ord ger fel gissningar. |
| 244 | Persistent mappsignaturindex för snabbare NAS-uppstart | Snabbhet | VÄNTAR | Spara `(mappväg, mtime_ns, antal_pdf)` på disk i `cache/` så att uppstart och rekursiv bevakning på långsamma SMB/NAS-enheter direkt ser oförändrade mappgrenar. Kortar genomsökningen märkbart i stora nätverksarkiv. |
| 245 | Anpassningsbar kolumnordning i Granska och Historik | Design | **KLAR (2026-11-24)** | Låt användaren dra kolumnrubriker och justera bredd i `Granska` och `Historik` samt spara layouten i `settings.json` på samma sätt som stödordstabellen. Gör långa tabeller bekväma på både smala och breda skärmar. |
| 246 | Automatisk gråskale- och breddbegränsning före Tesseract-OCR | Minne / OCR | VÄNTAR | Kapa extremt stora skannade sidor (t.ex. > 3 500 px bredd) ned till optimal OCR-upplösning i gråskala (`L`-läge) innan `pytesseract` anropas. Minskar OCR-minnestoppar kraftigt på A3-/foto-skanningar och kortar OCR-tiden. |
| 247 | Förhandsdetektering av molnsynk-platshållare (OneDrive/Dropbox) | Robusthet / System | VÄNTAR | Kontrollera Windows filattribut (`FILE_ATTRIBUTE_OFFLINE` / `RECALL_ON_DATA_ACCESS`) och öppna lås före PDF-läsning och visa statusen tydligt i kön. Förhindrar falska läsfel medan en molnsynkad fil laddas ned lokalt. |
| 248 | Förhandsdiff i Avancerat (JSON) innan spara | Design / Robusthet | VÄNTAR | Visa en tydlig rad-för-rad-jämförelse (tillagda, ändrade och borttagna nycklar/kategorier) innan manuella ändringar i `rules.json` eller `settings.json` skrivs till disk. Minskar risken för oavsiktliga regelbortfall vid manuell JSON-redigering. |
| 249 | Snabbgranskning med utökade tangentbordsgenvägar (`Alt+Pilar` / `Ctrl+Enter`) | Enkelhet / Design | **KLAR (2026-11-24)** | Lägg till kortkommandon i granskningsdialogen för sidbyte (`Alt+Vänster/Höger`), 90°-rotation (`R`), skjut upp (`U`) och bekräfta+nästa (`Ctrl+Enter`) med en diskret genvägsrad i sidfoten. Gör att större granskningsköer kan hanteras helt utan mus. |
| 250 | Realtidsmätare för trådar, ködjup och cache-träffar i Diagnostik | Felsökning / Prestanda | VÄNTAR | Visa aktiva arbetstrådar, pågående PDF, ködjup, `TextCache`/`_ZONES_CACHE`-träffprocent och ungefärlig process-RAM i ett översiktskort. Underlättar felsökning direkt om en tung fil bromsar sorteringen. |
| 251 | Strömmande textnormalisering i styckeintervall för jättedokument | Minne / Snabbhet | VÄNTAR | Bearbeta texter över 500 KB i sid- eller styckeblock vid zondetektering och stödordssökning i stället för att allokera flera helängdskopior samtidigt. Kapar toppminnet vid långa årsredovisningar och avtalsbuntar. |
| 252 | Återupptagningsbar sammanfattning efter avbruten batch | Design / Robusthet | VÄNTAR | När användaren klickar *Avbryt sortering* visas en kompakt summering (sorterade, köade, återstående filer) med knapp för att fortsätta batchen senare. Ger trygg kontroll vid stora engångssorteringar. |
| 253 | Atomär målplatskontroll före batch-ångra i Historik | Robusthet / Design | VÄNTAR | Kontrollera innan flera markerade historikhändelser flyttas tillbaka att ursprungsmapparna är skrivbara och flagga eventuella namnkrockar i förväg med en tydlig kvittenslista. Förebygger halvfärdiga återställningar. |
| 254 | Dubbla worker-köer som skiljer snabb textläsning från tung OCR | Snabbhet / Minne | VÄNTAR | Kör rena text-PDF:er och tunga Tesseract-OCR-PDF:er i separata prioriterade worker-spår så en lång skanning aldrig blockerar tio snabba digitala fakturor. Ger jämnare svarstid i både batch och bevakning. |
| 255 | Skarpa SVG-baserade mikroikoner skalade efter `pixel_scale` | Design / HiDPI | **KLAR (2026-11-24)** | Rendera små enhetliga status-, mapp-, OCR- och varningsikoner ur vektor-SVG vid aktuell `pixel_scale` för tabeller, kort och knappar. Ersätter teckenglyfer som ser olika ut mellan Windows-typsnitt och skärmskalningar. |
| 256 | Inbyggd tema-anpassad rapportläsare för MD- och CSV-rapporter | Design / Enkelhet | VÄNTAR | Öppna exporterade matchnings- och arkivrapporter i en inbyggd sökbar läsdialog som följer appens tema och textstorlek, med knapp för urklipp eller extern öppning. Snabbare granskning utan att lämna ArkivPiloten. |
| 257 | Tyst backoff-kö innan varning för tillfälligt låst fil | Robusthet | VÄNTAR | Lägg PDF-filer som är låsta av skannerprogram eller läsare i en lokal väntlista med tysta omförsök efter 10 s, 30 s och 2 min innan modalt låsfönster visas. Minskar avbrott när dokument skrivs färdigt på skrivbordet. |
| 258 | Öppna i Utforskaren med markerad fil (`explorer /select,`) | Enkelhet | VÄNTAR | Lägg till menyval och knapp i `Historik`, `Granska` och `Arkivsökning` för att visa och markera exakt PDF-fil i filhanteraren samt kopiera den fulla sökvägen. Kortar steget från träff till rätt dokument i mappen. |
| 259 | Förhandskontroll av ledigt diskutrymme före sortering | Robusthet | VÄNTAR | Mät ledigt utrymme på arkivmappens enhet innan en större sortering startar och visa en tydlig varning om mindre än 500 MB (eller 2× batchens datamängd) återstår. Fångar nästan full lokal disk eller USB-enhet innan flyttar påbörjas. |
| 260 | Städverktyg för tomma kvarlämnade årsmappar i arkivet | Ordning / System | **KLAR (2026-11-24)** | Erbjud ett valfritt steg efter flytt, ångra eller borttagning (samt manuell knapp) som listar och tar bort tomma under-/årsmappar under `output_dir`. Håller arkivträdet rent utan manuell städning i Utforskaren. |
| 261 | Skärmsäker arbetsytas-klippning (`SPI_GETWORKAREA`) för alla fönster | Design / HiDPI | VÄNTAR | Validera sparade och beräknade fönsterkoordinater mot aktuell dators synliga arbetsyta (exklusive aktivitetsfältet och bortkopplade extraskärmar) innan `geometry()` sätts. Säkerställer att fönster och dialoger alltid öppnas helt synliga. |

---
*Omgång 11 genererad 2026-11-24 med 25 skrivbordsspecifika förslag; 7 implementerade 2026-11-24 (`#237`, `#240`, `#243`, `#245`, `#249`, `#255`, `#260`).*

Omgång 9: 202–226 | Omgång 10: 227–236 | Omgång 11: 237–261 (7 KLAR, 18 VÄNTAR) | Övriga i kön: 1–236 + resterande i Omgång 11.
