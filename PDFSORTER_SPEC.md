> **Namnbyte 2026-10-06:** appen heter nu **ArkivPiloten** (tidigare
> "PDF Sorter"). Alla användarytor, titlar, tray, autostart, genvägar,
> ikonfiler (ArkivPiloten.ico/png), desktop.ini och bat-filen bär det
> nya namnet; ws-mappen heter ArkivPiloten. Historiska kravtexter
> nedan behåller sina originalord.
>
> **Leverans 1.2.0 (2026-10-16) — säkrare matchning, full installation,
> en ikon överallt. Namnet ArkivPiloten behålls (användarbeslut).**
> (a) Säkrare matchning: `_auto_blocker()` samlar alla beviskrav och
> prövar även en ny vinnare innan lärd klassificerare/historik får byta
> den; lärd profil ensam flyttar aldrig en fil (visas som förslag);
> Normal+ kräver avsändarzon/starkt ID/flersidigt bevis - bara löptext
> räcker aldrig; hårt golv på 12 lästa tecken utan bevisat ID;
> SHA-256-fingeravtryck av analyserade byte kontrolleras i `apply()`/
> `send_to_unmatched()` före flytt. Buggfix: `json_dir` saknades i
> huvudfilens importer, så lärda klassificeraren aldrig kunde starta.
> (b) Installation: bat-filen uppgraderar pip, installerar HELA
> requirements.txt (PyMuPDF, pypdf, pdfminer.six, Pillow, pystray,
> pytesseract - pinnade) med retry + importkontroll, installerar
> Tesseract (winget, swe+eng, bästa försök) och kör `--status` före
> start. Appens PIP_PAKET utökat till samma fulla stack.
> (c) Ikon: ny master-ikon `ArkivPiloten.png` (512px, PDF -> pil ->
> tre färgade mappar) är enda källan överallt - fönster/tray via
> `make_icon_image()` (kodritad reserv med samma motiv), genvägar/
> autostart/Utforskaren via `ArkivPiloten.ico` (16-256px), README
> och donationssidan.
>
> **Leverans 1.3.0 (2026-10-16) — allt i appmappen, autostart alla OS,
> paket-/Python-uppdateringar, Git-autouppdatering.**
> (a) Allt i undermappar: config_dir() = PDFSORTER_HOME, annars appmappen
> när den är skrivbar, annars användarens data-mapp (read-only
> /Applications, /opt eller låst USB) - och gamla OS-platsen är enbart
> migrationskälla. history.journal -> json/, genererad ikon ->
> icons/, Tesseract-installeraren -> temp/, bat-filens TEMP/TMP/
> PIP_CACHE_DIR/install.log -> temp/, cache/pip resp. logs/ i appmappen.
> (b) Autostart: Linux arkivpiloten.desktop (gamla pdfsorter.desktop
> städas), macOS-plist loggar till logs/autostart.log, Windows får
> Startup-mapp som reserv om registret nekar; autostart_status() för
> --status/diagnostik; självläkande synk vid start som förut.
> 2026-10-20: install.sh (macOS/Linux, venv + genväg + valfri autostart),
> verkliga .app-paket på macOS, shell-/plist-escaping verifierad med
> automatiska tester (tests/), och startskedet ärvs från OS-posten i
> stället för att raderas när settings säger av.
> (c) Paket/Python: --install-packages (+ update_python_packages())
> installerar hela requirements.txt med importkontroll; bat-filen
> har winget-reserv för Python. Senaste Python via python.org som förut.
> (d) Git-uppdatering: check_for_update() (api.github.com, versionsjämf.),
> perform_update() laddar zip till temp/, packar upp i updates/staging
> (zip-slip-skydd), validerar compile() + version, säkerhetskopierar
> till backups/update_<tid>/, ersätter bara UPDATE_FILES atomiskt och
> loggar updates/last_update.json. CLI --check-update/--update,
> GUI-knapp i Hjälp-fliken + automatisk sökning vid start
> (check_updates/auto_update i inställningarna).
>
> **Ej publicerad än — inställningsfliken går att rulla (2026-10-21).**
> Rapporterat: "ser inte att jag kan ställa in autostart av appen".
> Kryssrutan fanns - "Starta automatiskt med datorn" i kortet "Start och
> systemfält" - men det kortet är det SJÄTTE på fliken Inställningar, och
> fliken var en vanlig Frame utan rullning. Allt under fönsterkanten gick
> alltså inte att nå, varken autostarten eller uppdateringsvalen.
> (a) `_scrollable_tab()` lägger flikens innehåll i en canvas med
> rullningslist som bara visas när innehållet är högre än fönstret.
> (b) Mushjulet rullar fliken via en enda bindning på rotfönstret;
> `_widget_scrolls_itself()` ser till att en lista, ett textfält eller en
> rullgardin aldrig flyttar hela fliken i stället. Bindningen läggs till
> en gång (`_bind_tab_wheel`) - annars rullar det dubbelt - och kopplas
> tillbaka av `_reinstall_tab_wheel()` efter en dialog, eftersom
> granskningsdialogens `unbind_all` tar bort även flikens bindning.
> (c) 15 tester i tests/test_scrollable_settings.py, bl.a. AST-kontroll
> av att korten byggs i den rullbara ramen och att autostart-kortet
> ligger där. Ingen Tk behövs, så de går i CI på alla tre OS.
> Versionen är INTE höjd och ingen release är publicerad - det görs först
> på begäran.
>
> **Ej publicerad än — menyrad utöver flikarna (2026-10-22).**
> Önskemål: "gör en menyrad också, inte enbart flikar". Flikarna kräver att
> man letar; menyraden ger samma funktioner på ett ställe och visar
> genvägarna direkt i etiketten.
> (a) Fyra menyer: **Arkiv** (lägg till/ta bort inmapp, Sortera nu, Bevaka
> mapparna som kryssruta, Öppna utmappen, Öppna loggmappen, Avsluta),
> **Inställningar** (autostart, ikon i systemfältet, minimera till
> systemfältet, krysset, Ljust/Mörkt tema, Alla inställningar…),
> **Visa** (genväg till varje flik, Skapa genväg, Spara appikonen) och
> **Hjälp** (Användarhjälp, Kopiera AI-rapport, diagnostik, Sök
> uppdateringar, Om).
> (b) Innehållet är data: `meny_spec()` returnerar posterna, så testet kan
> granska dem utan Tk och upptäcka en post som pekar på en metod som inte
> finns. `_meny_atgard()` gör om en post till en klickfunktion; saknas
> metoden loggas det i stället för att krascha.
> (c) Genvägar: Ctrl på Windows/Linux, Command på macOS. `accelerator` i en
> Tk-meny är bara en etikett - därför binder `_bind_meny_snabb()` varje
> tangent på rotfönstret (inte `bind_all`, så en dialog behåller sina
> tangenter). Utan Shift binds gemener, med Shift versaler, eftersom Tk
> annars inte matchar tangenten på alla plattformar.
> (d) En bock i menyn sparas direkt (`_meny_kryss`): `tray_enabled`,
> `minimize_to_tray` och `close_to_tray`, och systemfältsikonen slås
> på/av utan omstart. Bevakningens kryssruta följer den verkliga
> bevakningen via `_sync_meny()`.
> (e) En trasig menyrad får aldrig hindra appen från att starta
> (undantaget loggas med `session_error("meny", …)`).
> (f) 28 tester i tests/test_menubar.py, inklusive ett test som bygger hela
> menyraden med Tk-attrapper och klickar igenom varje post. Ingen Tk
> behövs, så de går i CI på alla tre OS. Versionen är INTE höjd och ingen
> release är publicerad.
>
> **Ej publicerad än — tyst versionsvakt och tyst omstart (2026-10-26).**
> Önskemål: "autosök efter ny version (tyst) 2 ggr per dygn" och "tyst
> omstart vid uppdatering av version".
> (a) Sökningen är inte längre knuten till starten: en vakt väcks varje
> minut och söker när det är dags. Tiden sparas i `last_update_check`
> (ISO) tillsammans med `last_update_check_ok`, så antalet gäller över
> omstarter — en app som startas tio gånger om dagen frågar GitHub två
> gånger. Inställningen `update_checks_per_day` (standard 2) ger
> intervallet 86400/N sekunder; minst en gång per dygn, högst var 15:e
> minut. Misslyckas sökningen (nätet svek) görs ett nytt försök efter
> 30 minuter i stället för att vänta ett halvt dygn.
> (b) Allt är tyst: ingen dialog, ingen statusruta — bara rader i
> sessionsloggen, och raden i inställningskortet "Uppdateringar" som
> visar "Tyst sökning 2 ggr/dygn · senast i går 21:14 · nästa om 3 t".
> (c) `uppdateringsplan()` avgör utan Tk vad ett svar från GitHub leder
> till (fel / aktuell / osäker / erbjudande / fråga / installera) och om
> omstarten ska ske tyst. En automatisk sökning öppnar aldrig en dialog:
> är autouppdateringen avstängd blir en ny version en notis i
> systemfältet + en loggrad i stället, och en misslyckad tyst
> installation hamnar i loggen. Dialogen finns bara när användaren själv
> trycker på Sök.
> (d) Tyst omstart: `_restart_app()` startar den nya processen och
> stänger den gamla. Instanslåset släpps FÖRE start — annars nekar den
> nya instansen och ber den döende processen visa fönstret. Låg fönstret
> i systemfältet startas det med `--tray` (inget fönster som hoppar
> upp), och `--resume-watch` slår på bevakningen igen, så en pågående
> bevakning inte tystnar i natten. Misslyckas starten återtas låset och
> fönstret är kvar — appen fortsätter i den gamla versionen.
> (e) Omstarten väntar om appen är upptagen: sortering pågår,
> granskningsrutan är öppen eller filer väntar i granskningskön. Den
> försöker igen varje minut och faller tillbaka på nästa vanliga start.
> Inställningen `silent_restart` (på som standard) styr om omstarten sker
> utan fråga.
> (f) 34 tester i tests/test_update_schedule.py: schemat, sparningen över
> omstart, beslutsmatrisen, omstarts-kommandot per OS, hela flödet med
> attrapper (tyst installation utan en enda dialog), att en upptagen app
> väntar, och att låset släpps före start. Versionen är INTE höjd och
> ingen release är publicerad.
>
> **Ej publicerad än — tangentbordsnavigering i hela appen (2026-10-26).**
> Önskemål: mindre beroende av musen och snabbare förflyttning mellan flikar
> och kontrollområden.
> (a) `Ctrl+Tab` / `Ctrl+Shift+Tab` byter flik framåt/bakåt och slår runt
> vid första/sista fliken. `Ctrl+1…7` väljer fliken efter dess nuvarande
> ordning (Sortera, Matchningar, Inställningar, Granska, Historik, JSON,
> Hjälp); ogiltiga index gör inget.
> (b) `F6` och `Shift+F6` cyklar mellan flikväljaren, första synliga och
> aktiverade fokusmålet i den valda fliken, och statusraden. Statusraden
> är därmed också tangentbordsfokuserbar.
> (c) `Escape` stänger fokuserad dialog, men stänger aldrig huvudfönstret.
> Dialogens egen Escape-funktion får företräde (t.ex. återställning av
> sökfält eller Hoppa över i granskningen).
> (d) 9 tester i `tests/test_keyboard_navigation.py` täcker bindningar,
> flikväxling, Escape-säkerhet, fokuscykeln och att dolda/inaktiva kontroller
> hoppas över. Ingen Tk-session behövs. Versionen är INTE höjd och ingen
> release är publicerad.
>
> **Ej publicerad än — konsolfri start av GUI (2026-10-27).**
> Önskemål: inget konsolfönster när appens GUI startar, även om Windows
> startar `pdfsorter.py` med `python.exe` i stället för via `.pyw`.
> (a) En vanlig GUI-start (utan CLI-argument, eller enbart `--tray` /
> `--resume-watch`) lämnar tidigt över till `pythonw.exe`; om den saknas
> startas samma interpreter med `CREATE_NO_WINDOW`. Handoff-markören
> förhindrar startloop. CLI-kommandon som `--check` påverkas inte.
> (b) Ett misslyckat processanrop faller tillbaka till nuvarande process,
> så ett startfel aldrig hindrar GUI:t från att öppnas.
> (c) 6 tester i `tests/test_console_free_gui.py` täcker pythonw,
> reservstart, CLI-undantag, loopskydd, felreserv och att överlämningen
> sker innan GUI-initialisering. Versionen är INTE höjd och ingen release
> är publicerad.
>
> **Ej publicerad än — smart cacherensning dagligen (2026-10-27).**
> Önskemål: kunna rensa cache med smartfilter och låta det rensa automatiskt
> en gång per dygn.
> (a) Inställningar → **Cache och lagring** har ett påslag för automatisk
> rensning (på som standard), status över senaste körningen och knappen
> **Rensa cache nu**. Manuellt kör samma filter även om schemat är av.
> (b) `DiskTextCache.cleanup()` tar bara filer med cache-nyckelns SHA-1-namn;
> andra filer och undermappar lämnas orörda. Oanvända poster äldre än 30
> dagar tas bort. Därefter trimmas äldsta använda poster vid 1 500 filer
> eller 512 MiB. En lyckad cacheträff uppdaterar aktivitets-mtime; skadad
> JSON tas bort när den upptäcks. Cachen innehåller bara återskapbar PDF-text.
> (c) `last_cache_cleanup` sparas och vaktas med 24-timmarsintervall. Vakten
> går vid start och därefter varje timme, så appen som står öppen rensar
> ändå dagligen. Själva städningen körs i bakgrundstråd och låses mot läsning/
> skrivning i cacheklassen.
> (d) 11 tester i `tests/test_cache_cleanup.py` täcker ålder, LRU-tak,
> storlekstak, skydd av andra cachefiler, aktivitetsuppdatering, korrupt post,
> 24-timmarsgränsen, schematick och GUI-/inställningskoppling. Versionen är INTE höjd
> och ingen release är publicerad.
>
> **Ej publicerad än — stäng och minimera till systemfältet (2026-10-28).**
> Önskemål: både krysset och minimera-knappen ska gömma appen vid klockan.
> (a) `close_to_tray`, `minimize_to_tray` och `tray_enabled` är på som
> standard. Befintliga inställningar migreras en gång till detta beteende
> (`tray_minimize_migrated_v1`); användaren kan därefter ändra valen separat.
> (b) Utan tillgänglig systemfältsikon minimeras fönstret till aktivitetsfältet
> i stället, och stängning följer sin befintliga säkra reservväg. Med en öppen
> granskningsdialog stannar huvudfönstret i aktivitetsfältet tills dialogen
> är stängd, så att den inte blir frikopplad från sitt huvudfönster.
> (c) 12 tester i `tests/test_window_behavior.py` täcker standardvärden,
> migrering, val efter migrering, tray-krav och dialogskydd. Versionen är
> INTE höjd och ingen release är publicerad.
>
> **Ej publicerad än — starta med operativsystemet, minimerad (2026-10-28).**
> Önskemål: starta automatiskt vid inloggning och göm fönstret i systemfältet.
> (a) `autostart` och `start_minimized` är på som standard. En ny
> engångsmigrering (`autostart_minimized_migrated_v1`) aktiverar båda på
> befintliga installationer och synkar autostarten till operativsystemet.
> Autostart kan senare stängas av under Inställningar. OS-startposten använder
> `--tray`; `start_minimized` styr dessutom en vanlig manuell start.
> (b) `tray_enabled` slås på i migreringen. Om systemfältet inte finns eller
> ikonen inte kan startas visas huvudfönstret i stället; ingen app blir
> osynlig. Windows- och macOS/Linux-installationsflöden aktiverar autostart
> som standard, med ett uttryckligt avval på Windows och `--no-autostart`.
> (c) `App.__init__` synkar OS-posten vid start och uppdaterar kryssrutan
> efter resultatet. 12 tester i `tests/test_window_behavior.py` täcker
> standard, migrering, att användarval efter migrering bevaras och
> persistent settings. Versionen är INTE höjd och ingen release är publicerad.
>
> **Korrigering (2026-10-28) — manuell start synlig och sortering får inte gömmas.**
> Loggen visade att en vanlig start (utan `--tray`) ändå gömdes av den
> sparade `start_minimized=true`-inställningen. Samtidigt kunde minimering
> under en batchsortering gömma `ConflictDialog`; bakgrundstråden väntade då
> 120 sekunder per dubblett och appen såg ut att ha låst sig.
> (a) Nya och befintliga inställningar får `start_minimized=false` en gång;
> vanlig manuell start visar fönstret. OS-autostartens `--tray` fortsätter
> starta gömt enligt tidigare önskemål. Användaren kan ändra manuell start
> under Inställningar.
> (b) Minimering och gömning avvisas medan batchsortering körs; fönstret
> återställs så att dubblettdialoger går att se och svara på. Idle-minimering
> och stäng-till-systemfältet behålls.
> (c) Tester täcker migreringen, batchminimering och dialogskydd.
> Versionsnumret höjs inte och releasen uppdateras med samma versionsnummer.
>
> **Korrigering (2026-10-30) — mushjul och uppdatering från systemfältet.**
> (a) När kategorirullgardinen är öppen gör mushjulet ingenting; när den är
> stängd rullar hjulet granskningsdialogen som vanligt. Skrivning i fältet
> **Befintlig** fortsätter filtrera kategorier och rulla till första träffen.
> (b) Högerklick på systemfältsikonen → **Sök efter uppdateringar…** visar
> huvudfönstret och startar samma manuella, verifierade GitHub Releases-flöde
> som knappen i appen. Resultatdialoger är kopplade till huvudfönstret.
> Tester täcker hjulets öppna/stängda läge och tray-menyn. Versionsnumret
> behålls.
>
> **Leverans 1.4.13 (2026-10-21) — AI-rapport: alla fel på 0 sekunder.**
> Loggningen räckte inte för felsökning: undantag i en Tk-callback skrevs
> bara till `stderr`, som inte finns när appen startar med `pythonw`, och
> felen låg utspridda i sessionsloggar, `errors.log` och `krasch.log` -
> diagnostikpaketet läste dessutom hela filerna.
> (a) Ny modul `pdfsorter_diag.py`: felringbuffert i minnet (250 poster),
> `report_callback_exception`-krok för Tk (knappar, `after`, bindningar),
> vidarebefordran från appens `sys.excepthook`/`threading.excepthook` och
> `crash_report`, så ALLT hamnar på ett ställe.
> (b) `build_ai_report()`: ett kompakt block med miljö, unika fel med
> fingeravtryck (`TclError` från minne/logg/errors.log blir EN rad med
> antal), varningar, senaste händelserna och vilka filer som lästes.
> Fingeravtrycket normaliserar bort siffror, hex, tidsstämplar, sökvägar,
> modulprefix och radnummer, så samma fel får samma nyckel mellan
> versioner och mellan loggkällor.
> (c) Noll sekunder: filer ≤ 8 MB läses hela, större läses bara i svansen
> (200 kB). `--djup` läser hela filer upp till 64 MB. Rapporten säger
> alltid om en fil bara lästes delvis ("kör --djup"), så "inga fel" aldrig
> kan feltolkas. Mätt: 23 MB loggar → rapport på 0,08 s (0,45 s med
> Pythonstart), `--djup` 24,5 MB på 0,31 s.
> (d) Ytor: `--ai-rapport` (+ `--djup`) i CLI, *Kopiera AI-rapport (alla
> fel)* i Hjälp-fliken (kopierar till urklipp och skriver
> `logs/ai-rapport-senaste.txt` atomiskt), sammanfattning i
> `--diagnostik`, och `_svans` i supportpaketet läser bara svansen.
> (e) Avidentifiering: hemkatalog, användarnamn och `%USERPROFILE%` byts
> mot `~`/`<användare>` - rapporten kan klistras in var som helst.
> 24 nya tester i tests/test_diagnostics.py (168 totalt), inklusive
> Tk-kroken, hopslagning över tre källor, trunkeringsärlighet, tidsgräns
> på 5 MB-logg och att `UPDATE_FILES` och uppgraderingsverktyget alltid
> listar samma filer (nu inkl. `pdfsorter_diag.py`).
>
> **Leverans 1.4.12 (2026-10-21) — minimering med öppen dialog.**
> Rapporterat: minimerade man medan matchningsdialogen var öppen gick
> fönstret inte att få fram igen, och loggen fylldes av
> `TclError: cannot invoke "toplevel" command: application has been
> destroyed`.
> (a) `_minimize_action` tar nu `modal_open`: är granskningsdialogen
> öppen går minimeringen ALLTID till aktivitetsfältet, även med
> `minimize_to_tray` påslaget. Att withdrawa huvudfönstret lämnade en
> Toplevel med `grab_set` utan förälder.
> (b) `hide_window` vägrar withdrawa medan dialogen är öppen (minimerar
> i stället), och `show_window` tar fram dialogen igen när fönstret
> återställs.
> (c) Kön (`_process_queue`) kontrollerar `winfo_exists()` FÖRE VARJE
> dialog, inte bara en gång före loopen, och fångar `TclError` från
> dialogbygget. `_closing` stoppar kön helt; `_close_open_review()`
> stänger dialogen innan `root.destroy()` - tidigare skapade kön tre nya
> Toplevel-fönster i en död tolk.
> (d) Loggarkiveringen rör aldrig dagens loggning: pågående sessionsfil
> (`_SESSION_PATH`), filnamnets datum och filens mtime kontrolleras mot
> dagens datum innan `days`-gränsen. En pågående session med gammal
> mtime kunde annars gzippas medan appen fortfarande skrev i filen.
> 11 nya tester i tests/test_dialog_safety.py (124 totalt) - Tk-fria
> stand-ins, så de går i CI på alla tre OS.
>
> **Leverans 1.4.11 (2026-10-21) — uppdatering enbart från Releases.**
> Reserven mot main-grenen är borttagen. Skälet: en gren rör sig och kan
> inte verifieras mot en publicerad kontrollsumma, och den band appen
> till main. Nu finns bara `/releases/latest`:
> (a) `check_for_update` läser enbart GitHub Releases; svarar API:t inte
> returneras `ok=False` med felet, inget erbjuds och nästa försök görs
> vid nästa start. Den returnerar aldrig `source: branch`.
> (b) `UPDATE_BRANCH`, `UPDATE_RAW_BASE` och `UPDATE_ZIP_URL` är borttagna
> ur `__all__` och koden; `perform_update` kräver att releasen har ett
> paket och en kontrollsumma, annars avbryts allt utan att något hämtas.
> (c) GUI/CLI säger "GitHub Releases" rakt av (ingen main-gren kvar som
> alternativ). (d) Test: `test_no_branch_fallback` fångar varje URL och
> kräver att **endast** `UPDATE_RELEASES_LATEST` anropas, samt att inget
> går till codeload eller raw.githubusercontent. Releaser utan bifogat
> paket kan fortfarande använda GitHubs **tagg-arkiv** med summan ur
> release-texten - det är en fryst tagg, inte en gren.
>
> **Leverans 1.4.10 (2026-10-21) — .sh kör även med LANG=C.**
> Skriptet använde variabelnamnet `HÄR`. Bash tillåter Å/Ä/Ö i
> variabelnamn bara i en UTF-8-locale; med LC_ALL=C tolkas `HÄR=...` som
> ett kommando och skriptet dör på `set -u` ("H: unbound variable") innan
> något hämtas. Namnet är nu `APP_DIR`, och ett test kör `bash -n` med
> LC_ALL=C samt kontrollerar att alla variabelnamn är ASCII och att
> .bat-filen har enbart CRLF. Verifierat skarpt med LC_ALL=C: skriptet i
> Hämtade filer hittade appen på Skrivbordet och uppgraderade 1.1.0 till
> 1.4.10.
>
> **Leverans 1.4.9 (2026-10-21) — launchern hittar appen själv.**
> 1.4.8 krävde att uppgradera-arkivpiloten.bat låg i appmappen, men den
> hämtas ju till Hämtade filer - då hade den gett upp med "hittar ingen
> appmapp". Nu: (a) ges en sökväg som inte är en appmapp letar
> install_latest.py vidare i stället för att avbryta - Skrivbord,
> Dokument, Hämtade filer, ~/Applications, /opt,
> %LOCALAPPDATA%\Programs, OneDrive (inkl. Dokument) och två nivåer ned.
> (b) .bat-filen tar en appmapp som dragits till filen som första argument
> och tar bort ett avslutande `\` ur sökvägen, annars blir `\"` ett
> citattecken i argv och sökvägen fel. (.sh gör samma sak om första
> argumentet är en mapp.) (c) Feltexten säger nu hur man anger mappen.
> 20 tester, och de rör aldrig nätet: autouse-fixturen pekar om
> reservvägen (tagg-arkivet) till en fil som inte finns, så ett trasigt
> paket alltid är ett fel. Skarpt verifierat: en 1.1.0-mapp i
> Hämtade filer hittades på Skrivbordet och uppgraderades till 1.4.9.
>
> **Leverans 1.4.8 (2026-10-21) — vägen från 1.0.0/1.1.0 till
> autouppdatering.** 1.0.0 och 1.1.0 letade uppdateringar i main-grenen
> (`contents/pdfsorter.py?ref=main`) i stället för i Releases. main står
> kvar på 1.1.0, så de installationerna ser aldrig någon release och
> svarar alltid "du har senaste versionen". Det går inte att laga från
> servern utan att röra main - i stället finns nu en engångsuppgradering:
> (a) tools/install_latest.py hämtar `/releases/latest/download/`-
> filerna, kräver SHA256SUMS.txt, kompilerar alla .py FÖRE något skrivs,
> tar backup till backups/upgrade_<tid>/ och byter filerna atomiskt.
> Bara de kända programfilerna skrivs (vitlista, zip-slip-skydd), så
> json/, logs/, backups/ och egna filer är orörda. Går release-filerna
> inte att hämta används tagg-arkivet med summan ur release-texten -
> men en fil med FEL summa avbryter allt, utan reserv.
> (b) uppgradera-arkivpiloten.bat och .sh är dubbelklickbara: de hittar
> Python (py/python/venv), hämtar skriptet och kör det mot sin egen
> mapp. Båda följer med i zip:en och laddas dessutom upp som
> release-filer, så adressen
> `.../releases/latest/download/uppgradera-arkivpiloten.bat` alltid
> pekar på senaste versionen.
> (c) 19 tester (tests/test_upgrade_tool.py) kör hela flödet mot en
> lokal release på file://: summa, zip-slip, okända filer, användardata,
> backup, torrkörning och trasig kod. Verifierat skarpt: en 1.1.0-mapp
> uppgraderades till 1.4.7 via tagg-arkivet och rapporterar därefter
> "Senaste på GitHub: 1.4.7 (GitHub Releases)".
>
> **Leverans 1.4.7 (2026-10-20) — verifierad matching och sökning.**
> (a) Ände-till-ände-tester: tests/test_matching_pdf.py bygger riktiga
> PDF:er, kör läsaren och decide() - samma kedja som appen. PyMuPDF
> tillagd i requirements-dev så att testerna även går i CI.
> tests/test_dialog_flow.py kör granskningsdialogens riktiga metoder mot
> en Tk-fri stand-in: skriv p -> i -> l -> PIL, Enter väljer, Escape
> återställer, okänt namn blir ny mapp. Inget Tkinter krävs.
> (b) Fynd från testerna, rättade: mottagarblocket vinner nu över
> sidhuvudet - en kund som står i sidhuvudets band ("Kund: X" högt upp
> på fakturan) räknades förut som avsändarbevis med vikten 1,20 i
> stället för 0,30. Undantag: står samma text också överst som
> avsändare gäller avsändaren.
> (c) "·" och "•" accepteras som avskiljare i organisationsnummer och
> giro (typsnitt och OCR ger dem ibland i stället för bindestreck).
> Domäner är däremot inte flexibla: "Pilkington se bilaga" får inte
> matcha "pilkington.se".
> (d) Enter stänger en öppen träfflista innan listan återställs, så att
> de filtrerade raderna inte ligger kvar efter valet.
>
> **Leverans 1.4.6 (2026-10-20) — minimering och krysset är skilda saker.**
> Minimera-knappen göms inte längre automatiskt i systemfältet: fönstret
> stannar i aktivitetsfältet som vanliga program, och krysset fortsätter
> att gå till systemfältet enligt close_to_tray. Vill man att även
> minimering ska gå till systemfältet finns inställningen
> minimize_to_tray (av som standard) med egen kryssruta under Start och
> systemfält. _on_unmap kontrollerar att fönstret verkligen är minimerat
> (state iconic) så att byte av virtuellt skrivbord eller en withdraw
> inte misstolkas, och en vakt flagga hindrar dubbla hide-anrop.
> Inställningspanelen fick dessutom en ledig rad: temaväljaren låg
> tidigare ovanpå två kryssrutor i samma grid-rad.
>
> **Leverans 1.4.5 (2026-10-20) — bara riktiga bevis räknas, alla
> skrivsätt av samma nummer matchar, och fel lärs bort.**
> (a) Starka bevis: bara riktiga identifierare räknas. Årtal ("2025"),
> datum ("2024-01", "24.10.2025"), belopp ("1.234") och versionsnummer
> ("v1.4.4") klassades förut som projektkod eller domän och kunde
> därmed kringgå poängtröskel, krav på antal stödord och textlängd i
> _auto_blocker. Koder måste nu innehålla minst en bokstav och en
> siffra, domäner kräver en riktig toppdomän av bokstäver, och ett
> tiosiffrigt nummer med fel kontrollsiffra är inte längre ett starkt
> bevis.
> (b) Identifierare matchar oavsett skrivsätt: "556033-9086",
> "556033 9086", "5560339086" och "556033–9086" träffar samma regel,
> liksom VAT-nummer med eller utan mellanslag och SE-prefix. Mönstret
> byggs ur numrets delar med valfria skiljetecken; vanliga ord matchas
> exakt som förut.
> (c) Negativ inlärning: när en automatisk gissning rättas i
> granskningsdialogen registreras avvisandet på de stödord som ledde
> fel. Ordet väger 20 % mindre per avvisande (golv noll, halveringstid
> ett år), den lärda modellen får negativa bevis för den felaktiga
> kategorin, och historiken sparar corrected_from. Modellens säkerhet
> får dessutom en liten rankningsbonus (0,2) när den har minst fem
> filer per kategori - men aldrig över ett bevisat avsändar-ID och
> aldrig över beviskraven.
> (d) Tester: tests/test_matching.py (17 st) för starka bevis,
> identifierarformat, avvisanderäkning och negativ inlärning.
>
> **Leverans 1.4.4 (2026-10-20) — rullgardinen skriver-söker som en
> riktig dropdown.** Kategori/mapp: "p" visar mapparna som BÖRJAR på p
> (inte alla som innehåller p), "pil" smalnar av till PIL. Sökordet
> byggs upp tecken för tecken även när rullgardinen redan är öppen
> (p+i+l), i stället för att varje tangent söktes för sig - samma
> teckenbuffert gäller alla comboboxar och listor i appen. Tecknen
> hamnar rätt även när fältet är förvalt: första tangenten ersätter
> namnet i stället för att hamna efter det. En hjälprad under fältet
> visar antal träffar och vad Enter gör. Mushjulet byter fortfarande
> aldrig kategori.
>
> **Leverans 1.4.3 (2026-10-20) — multi-OS-installation + verifierad
> autouppdatering från Releases.**
> (a) install.sh för macOS/Linux (venv, genväg, valfri autostart,
> --uninstall), riktig .app i ~/Applications på macOS, .bat-filen frågar
> om autostart.
> (b) Autostart: Windows-register med Startup-mapp som reserv, macOS
> LaunchAgent via plistlib + launchctl, Linux XDG; klassning
> (correct/startup_folder/stale_console/stale_path/duplicate), verifiering
> efter skrivning, rollback av backup och effective_autostart() som ÄRVER
> en fungerande OS-post i stället för att radera den vid start.
> (c) Uppdatering: GitHub Releases är primär kanal (api releases/latest),
> paketet ArkivPiloten.zip verifieras mot SHA256SUMS.txt innan uppackning,
> zip-slip via Path.relative_to, compile()+versionskontroll, backup och
> fullständig rollback om något går fel, updates/last_update.json.
> auto_update är på som standard men installerar ENDAST när
> kontrollsumma finns. Saknar releasen bifogade filer används GitHubs
> tagg-arkiv som paket, med SHA-256 ur release-texten.
> .github/workflows/release.yml publicerar/uppdaterar releasen vid varje
> push till main och varje v*-tagg.
> (d) Tester: tests/ (pytest) för autostart per OS, datamapp, startfil,
> genvägar, CLI-autostart, uppdateraren och kategorisökningen; CI på
> Linux/macOS/Windows.
> (e) Granskningsdialogen: Kategori/mapp är en sökbar rullgardin
> (filtrerar medan man skriver, början-på-namnet först, accentokänsligt,
> Enter väljer entydig träff) och mushjulet över fältet byter aldrig
> kategori - det rullar fönstret.
>
> **Leverans 1.3.1 (2026-10-16) — kvalitetsrunda.** pyflakes-granskning
> hittade samma buggklass som json_dir-fyndet: `search_tesseract`
> användes i GUI:t men importerades aldrig (Sök datorn-knappen),
> `shutil` saknades i systemmodulen (auto_install_tesseract dog direkt
> på Windows) och `Dict` saknades i typing-importen. Alla fixade,
> plus död kod (`bycat`) borttagen. Nytt `--check`-självtest i
> huvudprogrammet (versionslikhet, hela importytan mot systemmodulen,
> matchningsregressioner, ikon, autostart-status) som fångar klassen
> permanent - det hittade direkt även saknade `DEFAULT_SETTINGS`.
> End-to-end verifierat via CLI: faktura med org.nr -> Pilkington/<år>,
> brev som bara nämner leverantören i löptext lämnas kvar.

> **Leverans 1.1.0 (2026-10-16) — beställarens val 1, 6, 7 (ej zip), 9, 10.**
> (1) Tvåspråkigt gränssnitt: `ui_language` sv/en, 102 översatta
> widgettexter appliceras efter bygget (okända strängar står kvar på
> svenska). (6) PDF-taggning: kategori skrivs som keywords/subject vid
> varje sortering (`tag_pdf_metadata`, standard på) - arkivet blir
> sökbart i Utforskaren/Acrobat. (7) Årsarkiv-export som ÖPPEN
> mappstruktur per år + sökbar index.html + checksums.sha256, från
> Historik-fliken eller `--export-archive MAPP` (kopierar, flyttar
> aldrig). (9) Org.nr-uppslag via nätet för okända avsändare
> (`orgnr_lookup`, standard AV): Luhn-validerat nummer slås upp och
> föreslås i granskningsdialogen; `--lookup-orgnr` för CLI.
> (10) Schemalagd sortering: `schedule_enabled`/`schedule_time`,
> tick var 30 s i GUI:t, en körning/dag (`schedule_last_run`).
> Verifierat: --check ALLT OK, taggning E2E (keywords "ArkivPiloten;
> Pilkington"), export med index/checksummor, uppslag degraderar
> tyst offline.

# PDF Sorter — Specifikation

**Program:** PDF Sorter `1.0.0`
**Uppdaterad:** 2026-08-26
**Språk i appen:** Svenska (gränssnitt och hjälptext). Kodkommentarer i huvudsak svenska.

---

## Innehåll

1. [Översikt](#del-1--översikt)
   - Syfte · Kärnidé · Arkitektur · Dataflöde · Modul för modul · Matchningslogik · Datamodell · Beroenden · Kommandorad · Enkelinstans & felsökning
2. [Kravspecifikation (REQ)](#del-2--kravspecifikation-req)
   - A Struktur · B Läsning/OCR · C Matchning · D Filflytt · E Data · F GUI · G System · H Tema · I Prestanda · J CLI · K Framtid · L Tillägg · M Prioriteringssammanfattning

---

# Del 1 — Översikt

## 1. Syfte

PDF Sorter är ett skrivbordsprogram som läser PDF-filer i en eller flera
**inmappar**, avgör vilket företag/projekt varje fil hör till och flyttar
den till rätt undermapp i en **utmapp** (t.ex. `Utmapp/Pilkington/`).
Allt sker lokalt på datorn — inga nätverksanrop, ingen molntjänst.

## 2. Kärnidé

> Appen är **försiktig av design.** En fil flyttas automatiskt bara när
> bevisen är starka. Är appen osäker frågar den i stället — det är alltid
> billigare att svara på en fråga än att leta rätt på en felsorterad fil.

Varje gång användaren svarar lär sig appen. Efter tio–femton svar känner
den igen de vanligaste leverantörerna och sköter resten på egen hand.

## 3. Arkitektur — fem samverkande moduler

Appen består av **fem filer** som måste ligga i samma mapp.

| Fil | Roll | Obligatorisk? |
|-----|------|---------------|
| `pdfsorter.py` | Matchningsmotor, jobbmotor, mappbevakning, grafiskt gränssnitt, kommandorad | ✅ Ja |
| `pdfsorter_data.py` | Lagring (JSON), regler, historik, enkelinstanslås, filflytt | ✅ Ja |
| `pdfsorter_read.py` | Textextraktion, OCR, de tio ordförslagen, dokumentsdatum | ✅ Ja |
| `pdfsorter_system.py` | Ikon, autostart, skrivbordsgenväg, systemfält, hjälptext, kraschrapport | 🚫 Valfri |
| `pdfsorter_theme.py` | Färger, typsnitt och ttk-stilar | 🚫 Valfri |

> Saknas `system`- eller `theme`-modulen startar appen ändå, men utan ikon
> i systemfältet/autostart respektive med Tkinters gråa standardutseende.
> Saknas `data`- eller `read`-modulen kan appen inte starta alls.

**Beroenderiktning** (ingen cirkulär import):

```
pdfsorter.py  ──►  pdfsorter_read.py   (text, ordförslag)
      │             pdfsorter_data.py   (regler, lagring, flytt)
      │             pdfsorter_system.py (ikon, systemfält, hjälp)
      │             pdfsorter_theme.py  (utseende)
      ▼
pdfsorter_data.py   ──►  pdfsorter_read.normalize  (normalisering)
pdfsorter_system.py ──►  (konfigureras via configure(), ingen import tillbaka)
pdfsorter_theme.py  ──►  (helt fristående)
```

## 4. Dataflöde (workflow)

```
[Inmapp] ──►  FolderWatcher (poll var 5 s)
                ├─ is_stable()  = filen ändrats ej på 3 s
                ├─ pdf_looks_complete()  = börjar %PDF- och slutar %%EOF
                └─ on_file(path)
                      │
                      ▼
              SortEngine.analyze(path)
                      │  read_pdf → TextCache → extract()
                      │  decide() → score_text()
                      ▼
        ┌───────────────┬──────────────────┬──────────────┐
        │ status=auto   │ status=ask       │ status=error │
        │ flytta direkt │ → granskningskön │ logga + lämna│
        │               │   → ReviewDialog │              │
        └──────┬────────┴────────┬─────────┴──────────────┘
               ▼                ▼
      place_file()        användaren bockar i stödord
      Utmapp/Kategori     → learn() + apply()
      [/År...]            → rescan_after_learn()
```

**Tre beslutsstatusar** (definieras i `decide()`):

| Status | Betydelse | Vad som händer |
|--------|-----------|----------------|
| `auto` | Bevisen räcker | Flyttas med en gång |
| `ask`  | Otydligt / för svaga bevis | Läggs i kön, öppnas i granskningsrutan |
| `error`| Filen kunde inte läsas | Loggas som fel, lämnas orörd |

## 5. Modul för modul

### 5.1 `pdfsorter_read.py` — läsa och tolka PDF

- **Motorer (i prioritetsordning):** `pymupdf` → `pypdf` → `pdfminer`. Den
  som ger mest/längst text vinner.
- **`extract()`** läser brödtext, sidhuvud, sidfot, anteckningar, ifyllda
  formulärfält och — via OCR — logotypbilder i brevhuvudet. Kastar aldrig
  undantag; fel hamnar i `Extraction.error`.
- **Zoneindelning** skiljer *avsändare* från *mottagare* (se §6.2).
- **`suggest_keywords()`** är helt deterministisk och lokal (ingen AI/nät).
  Producerar upp till `keywords_per_file` (10) kandidatord.
- **`find_document_date()`** väljer dokumentets datum för årsmappar.
- **`Extraction`** är datakontraktet: `.text`, `.combined`, `.page_header`,
  `.page_footer`, `.used_ocr`, `.ocr_logo`, `.doc_date`, `.date_source`,
  `.date_candidates`, `.error`.

### 5.2 `pdfsorter_data.py` — lagring och filflytt

- **`config_dir()`** (kan överstyras med `PDFSORTER_HOME`):
  - Windows: `%APPDATA%\PDFSorter`
  - macOS: `~/Library/Application Support/PDFSorter`
  - Linux: `~/.config/pdfsorter`
- **Tre JSON-filer**, alla skrivna **atomiskt** (temp-fil + `os.replace`):
  `rules.json`, `settings.json`, `history.json`.
- **`Rules`** representerar `rules.json`: `categories[]` med
  `name`, `folder`, `keywords[]`, `enabled`, `subfolder`, `min_keywords`,
  `created`, `files_sorted`. Stödord: `{text, weight, whole_word, hits,
  added, source}`.
- **`InstanceLock`** säkerställer bara en körande instans (PID+starttid,
  koll på om processen lever). Startas appen en andra gång visas det
  befintliga fönstret i stället.
- **`place_file()`** flyttar/kopierar, skapar mappar, löser namnkrock
  (`faktura (2).pdf`) och skriver aldrig över.
- **`safe_folder_name()`** sanerar mappnamn för Windows/macOS/Linux.

### 5.3 `pdfsorter_system.py` — systemintegration

- **Ikon** ritas i kod (ingen bildfil): ett PDF-blad som förgrenas till tre
  färgade mappar. Under 32 px används ett förenklat motiv. Grön prick = bevakning på.
- **Autostart** via Windows-registret, macOS LaunchAgent eller XDG-autostart.
- **Skrivbordsgenväg** (Windows + Linux).
- **`TrayIcon`**: systemfältsikon med snabbmeny (Visa fönster, Sortera nu,
  Bevakning, Granska, Öppna utmappen, Avsluta). Körs i egen tråd, och all
  Tk-interaktion går via `App._post`.
- **`HELP_CONTENT`** = hela användarhjälpen (fliken Hjälp).
- **`crash_report()`** loggar till `krasch.log` och visar en dialog.

### 5.4 `pdfsorter_theme.py` — utseende

- **`COLORS`**: ljus, sval grundton med blå accent (`#2563c7`).
- **`Theme`** bygger ttk-stilar: kort, knappar (Accent/Danger/Link),
  flikar, tabeller, fält, kryss/radio, rullningslister, statusrad.
- **`Theme.card()`**, **`Theme.zebra()`**, **`Theme.fit_columns()`** är de
  byggstenar GUI:t använder.

### 5.5 `pdfsorter.py` — matchningsmotor, jobbmotor och GUI

**Matchningsmotorn** (funktionell, inget Tk här):
- `keyword_strength()` → `orgnr` / `vat` / `giro` / `domain` / `kod`.
- `_STRONG_PATTERNS` + **Luhn-kontroll** av organisationsnummer (ett
  tiosiffrigt nummer med fel checksiffra är inte ett org.nr).
- `_kw_pattern()` — "helt ord"-logik som tillåter `IF26-2024` men inte `IF260`.
- `TextZones.build()` + `locate()` — förfilter via mängduppslagning, sedan
  zonning.
- `score_text()` → `CategoryScore` per poängsatt kategori.
- `decide()` → `Decision(auto/ask/error)`.

**Jobbmotorn:**
- `SortEngine` (trådsäker): `analyze`, `apply`, `send_to_unmatched`, `learn`.
- `FolderWatcher` / `MultiFolderWatcher` — polling som fungerar på
  nätverksenheter och alla OS.
- `TextCache` — minnescache nycklad på (sökväg, storlek, mtime). Sparar
  dyr OCR-text mellan omskanningar.

**GUI (Tkinter):** sju flikar — Sortera, Matchningar, Inställningar,
Granska, Historik, JSON, Hjälp. Kärnan är `ReviewDialog` med 10 föreslagna
stödord att bocka i.

## 6. Matchningslogik i detalj

### 6.1 Stödordets styrka

| Typ | Vikt | Kräver Luhn? |
|-----|------|--------------|
| organisationsnummer | 3.0 | Ja |
| VAT-nummer | 3.0 | Nej |
| domän | 2.6 | Nej |
| bankgiro/plusgiro | 2.2 | Nej |
| projekt-/objektkod | stark | Nej |

### 6.2 Var i dokumentet ordet står (zonvikter)

| Zon | Vikt | Betydelse |
|-----|------|-----------|
| `sender` | 1.60 | allra översta raden — nästan alltid avsändaren |
| `filename` | 1.30 | någon har döpt filen medvetet |
| `header` | 1.25 | brevhuvudet |
| `pagehead` | 1.20 | återkommande sidhuvud |
| `identity` | 1.15 | rad med org.nr / VAT / bankgiro |
| `pagefoot` | 1.15 | sidfot (org.nr, bankgiro) |
| `body` | 1.00 | brödtext, tabeller |
| `recipient` | 0.30 | mottagarblocket — det är *kunden*, inte avsändaren |

Detta är nyckeln till att en faktura **till** Pilkington inte hamnar i
Pilkingtons mapp.

### 6.3 Strikthetsnivåer

| Nivå | Lägsta poäng | Marginal | Antal ord | Starkt krävs | Läs (tecken) | Ankare krävs |
|------|-------------|----------|-----------|--------------|--------------|--------------|
| **Lös** | 1.0 | 0.01 | 1 | nej | 0 | nej |
| **Normal** | 1.0 | 0.5 | **2** | nej | 0 | nej |
| **Strikt** | 2.0 | 1.0 | 2 | nej | 40 | ja |
| **Mycket strikt** | 3.0 | 2.0 | 2 | ja | 60 | ja |
| **Egen** | — | — | — | — | — | — |

Ett **bevisat avsändar-ID** (org.nr/domän/bankgiro i brevhuvud, sidfot,
org.nr-rad eller filnamn) går alltid före räknereglerna — ett sådant bevis
identifierar företaget lika säkert ensamt som tillsammans med tio vanliga ord.

## 7. Datamodell (JSON, `schema_version = 1`)

### `rules.json`
```json
{
  "schema_version": 1,
  "updated": "2026-08-26T12:00:00+02:00",
  "categories": [
    {
      "name": "Pilkington",
      "folder": "Pilkington",
      "enabled": true,
      "subfolder": "{år}",
      "min_keywords": 0,
      "created": "...",
      "files_sorted": 27,
      "keywords": [
        {"text": "pilkington", "weight": 1.0, "whole_word": true,
         "hits": 27, "added": "...", "source": "dialog"},
        {"text": "556033-9086", "weight": 1.0, "whole_word": true,
         "hits": 18, "added": "...", "source": "dialog"}
      ]
    }
  ]
}
```

### `settings.json`
`DEFAULT_SETTINGS` innehåller mappar, strikthet, OCR, bevakningstakt,
systray/autostart, samt datum- och undermappsinställningar.

### `history.json`
`events[]` med per flyttad fil: `time, action, source, target, category,
score, runner_up, matched, used_ocr, decided_by, learned, date,
date_source, subfolder`. Tak: **2000** poster.

## 8. Valfria beroenden

```
pip install pymupdf pypdf pystray pillow pytesseract
```
OCR kräver dessutom systemprogrammet **Tesseract**. Alla är valfria — appen
startar ändå och talar om i statusraden vad som saknas.

## 9. Kommandorad

```
python pdfsorter.py --status
python pdfsorter.py -i INMAPP -o UTMAPP --no-ask
python pdfsorter.py -i INMAPP -o UTMAPP --dry-run --verbose
python pdfsorter.py --watch
python pdfsorter.py --install-autostart
python pdfsorter.py --make-shortcut
python pdfsorter.py --save-icon FIL
```

## 10. Enkelinstans & felsökning

- Bara **en** app åt gången (`InstanceLock`). En andra start visar det
  befintliga fönstret i stället för att köra en kopia — två appar skriver
  över varandras regler.
- Kraschar appen skrivs felet till `krasch.log` och visas i en dialog.
- Felsöka en enskild fil: `python pdfsorter_read.py "filen.pdf"`.

---

# Del 2 — Kravspecifikation (REQ)

Syftet med den här delen är att vara en **kontrakts- och kvalitetsgrund**
för utveckling och godkännande av PDF Sorter. Varje krav har ett unikt ID
för uppföljning, en **prioritet** och en lista av **acceptanskriterier**
(AC) som måste vara uppfyllda för att kravet ska anses godkänt.

## Prioritetsskala

| Märke | Betydelse |
|-------|-----------|
| **M** (Måste) | Kärnfunktion. Utan detta är programmet inte färdigt. |
| **B** (Bör) | Viktig men kan levereras i ett senare steg. |
| **K** (Kan) | Trevligt att ha; valfri förbättring. |

## Förkortningar

- PDF = inläst dokumentfil (`.pdf`)
- Inmapp = mapp som bevakas
- Utmapp = mapp där undermappar/kategorier skapas
- Kategori = en mapp i utmappen (t.ex. "Pilkington")
- Stödord = ett ord/fras/nummer som avgör kategorin
- Ask-kön = granskningskön med osäkra filer

---

## A. Applikationsstruktur & paketering

### REQ-A1 (M) — Fem filer i samma mapp
Appen består av fem Python-filer som måste ligga i samma mapp:
`pdfsorter.py`, `pdfsorter_data.py`, `pdfsorter_read.py`,
`pdfsorter_system.py`, `pdfsorter_theme.py`.
**AC-A1:**
- AC-1.1 Samtliga fem filer hittas och importeras utan fel.
- AC-1.2 Bara `pdfsorter.py` körs direkt; övriga är moduler.

### REQ-A2 (M) — Tåliga, valfria hjälpmoduler
`pdfsorter_system.py` och `pdfsorter_theme.py` **får saknas** utan att
appen kraschar.
**AC-A2:**
- AC-2.1 Saknas `pdfsorter_system.py` startar appen, visar en
  statusradstext ("pdfsorter_system.py saknas") och exekverar sorteringen.
- AC-2.2 Saknas `pdfsorter_theme.py` startar appen med Tkinters gråa
  standardutseende och alla `self.C[...]`-färguppslag fungerar ändå.
- AC-2.3 Saknas `pdfsorter_read.py` **eller** `pdfsorter_data.py` skrivs
  ett begripligt felmeddelande (till stderr och i en dialog) och appen
  avslutar med kod 2.

### REQ-A3 (M) — Enkelinstans
Bara en körande app får äga `rules.json`. En andra start måste visa det
befintliga fönstret i stället för att köra en kopia.
**AC-A3:**
- AC-3.1 `InstanceLock.acquire()` returnerar `False` om en annan *levande*
  process håller låset, och `True` annars.
- AC-3.2 Lämnas en låsfil kvar efter en krasch (avliden PID) ska låset
  kunna övertas.
- AC-3.3 En andra start anropar `request_show()`; den första instansen
  konsumerar begäran och visar sitt fönster.
- AC-3.4 `release()` tar bort låsfilen endast om den fortfarande är vår.

### REQ-A4 (M) — Konfigurationskatalog
Där JSON-filerna ligger ska följa operativsystemets konvention och kunna
överstyras.
**AC-A4:**
- AC-4.1 Windows: `%APPDATA%\PDFSorter`; macOS:
  `~/Library/Application Support/PDFSorter`; Linux: `~/.config/pdfsorter`.
- AC-4.2 `PDFSORTER_HOME` överordnas alltid miljövariabeln.
- AC-4.3 Katalogen skapas automatiskt vid behov.

---

## B. PDF-läsning & OCR

### REQ-A5 (B) — 100 % portabel app (ANVÄNDARORDER 2026-10-05)
"Allt rörande appen ska sparas i appmappen ... ska funka överallt, även
på usb." `config_dir()` = 1) `PDFSORTER_HOME` om satt, 2) **appmappen**
(där modulerna ligger) om skrivbar - regler, inställningar, historik,
`logs/`, `backups/`, ikon m.m. följer med pdfsorter.py, 3) fallback till
OS-platsen om appmappen är skrivskyddad (read-only USB/programkatalog).
**AC-A5:**
- AC-5.1 Appmappens två undermappar rymmer allt (ANVÄNDARORDER
  2026-10-06: "loggning i samma mapp, allt sparas i appmappen, logs,
  json"): `logs/` = all loggning (sessionsloggar, krasch.log), `json/` =
  alla datafiler (settings, rules, history+journal, ignored_files,
  learned_model, lås, show-request, rapporter). Skrivtest avgör
  portabilitet utan att krascha.
- AC-5.1b `json_dir()` flyttar en gång kvarlämnade datafiler från
  appmappens rot (tidigare portabla layouten) till `json/`;
  `migrate_to_portable()` läser även gamla OS-platsens `json/`-layout.
- AC-5.2 `migrate_to_portable()` kopierar (flyttar ALDRIG) befintlig
  data från gamla OS-platsen vid första portabla start; loggas.
- AC-5.3 Launcher (.pyw) och `--diag` använder samma regel så att allt
  pekar på samma ställe. Verifierat: USB-simulering (tom appmapp),
  skrivskyddad mapp (fallback), migrering med rules.json.
- AC-5.4 **EN enda startfil med tydligt namn (ANVÄNDARORDER 2026-10-06:
  "inga bat-filer, endast en ... alltid installera senaste python,
  tydligt namn"):** `PDF Sorter - Installera senaste Python och
  starta.bat`. Den 1) söker Python (py-launcher → PATH utan
  Store-stubben → per-user/Program Files-kataloger, högsta versionen
  väljs), 2) jämför mot senaste stabila från python.org och installerar
  UPPGRADERAR alltid vid behov (tyst, per user, inget admin: `/quiet
  InstallAllUsers=0 PrependPath=1 Include_pip=1`), 3) `pip install -r
  requirements.txt` tyst, 4) start via `pythonw.exe pdfsorter.pyw`
  (konsolfritt). Äldre `starta_pdfsorter.bat` borttagen - exakt en
  bat-fil finns. Felvägar: tydligt meddelande + manuell länk.

### REQ-B1 (M) — Textextraktion från flera motorer
Text ska kunna läsas ur en PDF via åtminstone en av `pymupdf` / `pypdf` /
`pdfminer`, med fallback i prioritetsordning.
**AC-B1:**
- AC-1.1 En textbaserad PDF ger utläst text via den starkaste tillgängliga
  motorn.
- AC-1.2 `extract()` kastar **aldrig** ett undantag — fel hamnar i
  `Extraction.error`.
- AC-1.3 Sidhuvud och sidfot fångas upp och exponeras via
  `page_header` / `page_footer`.
- AC-1.4 Anteckningar och ifyllda formulärfält inkluderas när motorn är
  PyMuPDF.
- AC-1.5 Utan tillgänglig läsbar text sätts `.error` och inget krockas.

### REQ-B2 (M) — OCR för inskannade PDF:er
När textlagret är för tunt ska appen kunna OCR:a de första sidorna.
**AC-B2:**
- AC-2.1 Vid `< MIN_TEXT_CHARS` (120) tecken och OCR tillgänglig ska
  sidorna renderas och OCR:as (`tesseract`, `--psm`).
- AC-2.2 `used_ocr=True` sätts när OCR användes, `ocr_logo=True` när bara
  logotypen OCR:ades.
- AC-2.3 OCR startar endast om `ocr_enabled` är sant och Tesseract finns.
- AC-2.4 OCR kräver `pytesseract` + `PIL`, och renderar via PyMuPDF eller
  `pdftoppm`.

### REQ-B3 (M) — OCR/avkodning av logotyp i hybrid-PDF
En PDF med textlager men där avsändaren bara ligger i en logotypbild ska
kunna få logotypen OCR:ad.
**AC-B3:**
- AC-3.1 `header_images()` hittar bilder i sidans övre 33 % med minsta
  area/bredd.
- AC-3.2 `ocr_header_logo()` OCR:ar dessa och lägger ny text *först* i
  dokumentet, så att den väger som brevhuvud.
- AC-3.3 Ny text som redan finns i textlagret läggs inte till två gånger.

### REQ-B4 (B) — Bättre OCR och avläsning av PDF (förbättring)
Höj avläsningsnoggrannheten för inskannade och svåra PDF:er, med målet att
**väsentligt** förbättra utfallet (jämförelseaktivt mål: ~10× bättre
"avläsning", dvs. markant färre feltolkningar än nuvarande raka
`image_to_string`).
**AC-B4:**
- AC-4.1 OCR-förbehandling sker före textextraktion: grånivå/kontrast,
  binarisering, ev. upplösningshöjning och skevhetskorrigering
  (deskew) för skannade sidor.
- AC-4.2 Texten läses med bättre `--psm`-lägen och `--oem`-val; gärna
  med både svenska och engelska språkfiler (`swe+eng`).
- AC-4.3 En ny "Bättre OCR"-inställning (knapp/kryssruta) gör det möjligt
  att välja högre kvalitet när det är kritiskt att det blir rätt.
- AC-4.4 Acceptansmått: över en fast referensmängd av inskannade PDF:er
  ska korrekt identifierade nyckelord (org.nr, firmanamn, datum) öka i
  andel jämfört med en referenskörning.
- AC-4.5 Förbättrad OCR får inte göra vanliga textbaserade PDF:er
  långsammare eller sämre — textlagret ska alltid prioriteras först.

> **Anmärkning (målformulering).** "1000% bättre avläsning" tolkas som
> ett *effektmål* för noggrannheten och läses in som REQ-B4 med
> acceptansen i AC-4.4. Ett realistiskt, mätbart kriterium ska tas fram
> med en referenskorpus och ett referensantal (baslinje) innan arbetet
> påbörjas.

### REQ-B5 (M) — Dokumentsdatum för årsmappar
Datumet i dokumentet ska väljas enligt regler som undviker fel datum.
**AC-B5:**
- AC-5.1 Prioritet: (1) rad med datumetikett ("Fakturadatum:"), (2) datum i
  brevhuvud/sidhuvud, (3) filnamn, (4) äldsta rimliga datum i texten.
- AC-5.2 Rader som innehåller förfallodatum (`forfaller`, `due date`,
  "sista betalningsdag" osv.) utesluts alltid.
- AC-5.3 Omöjliga datum (t.ex. 30 februari) och orimliga år ska filtreras.

---

## C. Matchningsmotor

### REQ-B6 (B) — Läsningshärdning & förbättring (leverans 2026-08-26,
"50000 % bättre, får ej låsa sig")
**AC-B6:**
- AC-6.1 Hängningsskydd: tesseract-anrop med 60 s timeout där det stöds,
  90 s per sida i OCR-poolen, pdftoppm-tak 60 s; `_run_ocr` returnerar
  `("", -1.0)` utan pytesseract/bilder i stället för att krascha
  uppackningen i `extract()`. Alla OCR-anrop går via `_tess_call`
  (även logotyp-OCR:n, som tidigare saknade timeout).
- AC-6.2 Bättre avläsning: avstavningar över radbrytning läks ihop i
  `_clean`; extra OCR-pass på 1,5× uppskalad bild i läget "high".
  **Buggfix 2026-10-05 (bevisad med äkta Tesseract i test):**
  `autocontrast(cutoff=1)` i `_preprocess` klippte bort textpixlarna på
  högkontrastskanningar (text <1 % av ytan) så OCR:n såg ingenting.
  Kontraststeget sträcker nu endast bilder med verkligt låg kontrast
  (extrema-skillnad <120), utan cutoff. E2E: ritad skannad faktura →
  OCR konfidens 95 → text upplåst → auto-sorterad.
- AC-6.3 Bättre matchning: org.nr med blanksteg ("556033 9086") räknas som
  orgnr (Luhn gäller) i både läs- och matchningsmodulen; E2E-verifierat.
- AC-6.4 **Leverans 2026-08-26, rond 3 (kod/design):** `Extraction` äger
  sitt cacheformat (`to_cache_dict`/`from_cache_dict`); OCR-konfidens är ett
  förstaklassfält (`ocr_conf`); metadata som redan finns i brödtexten
  dubbelräknas inte i `combined`; `reading_health()` matar `--status`/
  `--diag`; `__repr__` på Extraction/Candidate för felsökning.
- AC-6.5 **Leverans 2026-08-26, rond 4 (matchning/snabbhet/minne):**
  företagsnamn utan bolagsändelse fångas vid identitetsrad (titelfalls-
  heuristik, 1–4 ord, inga siffror); tokenräknare ersätter upprepad
  normalize+findall per kandidat (en normalisering per anrop); deskew endast
  i "Bättre OCR"-läget; OCR-brusord i STOPWORDS.

### REQ-G5 (B) — Självläkande autostart (leverans 2026-08-26, "bättre autostart")
`sync_autostart(want)` körs vid varje appstart: OS-post saknas men settings
säger på → skapa; post finns men settings säger av → ta bort; rätt → gör
inget. Autostarten tystnar inte efter OS-uppdatering eller flyttad mapp.
**AC-G5:**
- AC-5.1 Synk på alla tre OS (win/mac/linux) via befintliga skrivare.
- AC-5.2 Idempotent: upprepad synk ger "synk" utan sidoeffekter.
- AC-5.3 Fel i synken får aldrig hindra appstart (try/except i App).

### REQ-G6 (B) — Systemmodulens hängningsskydd & felsökning
(leverans 2026-08-26, "50000 % bättre, får ej låsa sig")
**AC-G6:**
- AC-6.1 `TrayIcon.stop()` använder 2 s vakthundstråd — en hängande
  tray-backend blockerar aldrig avslut.
- AC-6.2 `set_autostart` prövar skrivningen två gånger vid transienta
  I/O-fel (`_retry_io`).
- AC-6.3 `--diag` skriver felsökningsöversikt: autostart på/aktuell,
  journalsstorlek, ikonfil, loggmapp, tray-tillgänglighet.
- AC-6.4 **Leverans 2026-08-26.**

- AC-6.6 **Avläsningsrundan 2026-09-17 (förslag 21+22 levererade):**
  pdfminer-vägen räknar sidor riktigt (PDFPage-bläddring) och fick samma
  `HARD_PAGE_CAP` som pymupdf; pypdf-vägen fick taket (en 5000-sidig fil
  lästes annars fullt ut). PIL-bildläckor i `ocr_header_logo`/
  `ocr_embedded_images` tätade (både original och förbehandlad kopia
  stängs). `embedded_images` öppnar dokumentet en gång i stället för två.
  Skevhetsrättning slopad för logotyper/stämplar (snabbhet). Nytt minnes-
  tak `_OCR_MAX_WIDTH=5200` i `_preprocess`. Språkvalet samlat i
  `_resolve_langs` (en funktion i stället för tre kopior).
  Verifierat: 18 tester inkl. pdfminer/pypdf-sidräkning, breddtak,
  bildstängning med fejkad OCR-kedja och hel `extract()`-pipeline.

### REQ-G7 (B) — Systemmodulen, lager 2 (leverans 2026-08-26)
**AC-G7:**
- AC-7.1 Ikon-memo (`_ICON_CACHE`): renderas en gång per (storlek, aktiv),
  kopior delas ut — tray-refresh och dialoger ritas inte om i onödan.
- AC-7.2 Ikonen har tunn ljus kontrastkant så att den syns mot mörka
  aktivitetsfält/titelrader (design, ljust som mörkt läge).
- AC-7.3 Kraschdialogen stänger sig själv efter 2 minuter (hängningsskydd
  för schemalagda starter).
- AC-7.4 Starthjälpfiler (.pyw/.sh/.command) är självläkande: saboterat eller
  föråldrat innehåll på samma plats skrivs om; oförändrade rörs inte.
- AC-7.5 Fristående körningar respekterar `PDFSORTER_HOME` (samma regel som
  datamodulen); `--diag` visar även senaste flytt (läs-/matchningshälsa).
- AC-7.6 `pdfsorter.pyw` är en robust, flyttbar startfil (mall `LAUNCHER_PYW`
  i systemmodulen, byte-identisk med filen): hittar `pdfsorter.py` bredvid
  sig själv (ingen hårdkodad sökväg — hela mappen kan flyttas), sätter
  arbetskatalog och `sys.argv[0]`, vidarebefordrar kommandoradsargument
  (`.pyw --tray` fungerar), sätter Windows `AppUserModelID` före första
  fönstret (egen ikon i aktivitetsfältet i stället för Pythons fjäder),
  omdirigerar stdout/stderr under pythonw och fångar startfel i dialog
  (självstängande efter 2 min) + logg. Startfel utan systemmodul skrivs
  till `krasch.log`.
- AC-7.7 Ikonhantering "överallt": `set_app_user_model_id()` anropas i
  `main()` före alla fönster (täcker även autostart via `pythonw --tray`);
  `brand_window(root)` sätter `iconphoto(True, …)` + Windows `iconbitmap
  (default=…)` så att ALLA toplevels och dialoger — huvudfönster,
  "kör redan"-ruta och kraschdialog — får appikonen i titelrad och
  aktivitetsfält. `ensure_icon_file()` validerar ikonfilen med Pillow och
  ritar om trasiga/avkapade filer (memoiserat per körning).



- AC-7.8 **Systemrundan 2026-09-17:** (a) Autostartfiler (.plist/.desktop,
  både autostart och skrivbordsgenväg) skrivs ATOMISKT via `_atomic_text`
  (mkstemp → fdopen → fsync → os.replace) - en krasch mitt i kan aldrig
  lämna en halv OS-post. (b) PowerShell-escaping (`_ps_quote`) i
  genvägsskaparen: apostrofer i sökvägar (t.ex. O'Brien) spränger inte
  längre kommandot. (c) macOS-klassificeringen av autostartposten kunde
  aldrig bli "correct" (plist innehåller argumenten i varsin <string>,
  aldrig hela kommandoraden) - jämför nu beståndsdelarna; annars hade
  varje synk skrivit om posten i onödan. (d) Tray-trådens undantag
  loggas till sessionsloggen i stället för att sväljas tyst.
  (e) `close_session()` stänger sessionsloggen vid avslut (anropas i
  `_on_close`); `_SESSION_LOCK` är numera RLock så att stängningen kan
  skriva en sista rad utan deadlock. Verifierat: 22 tester inkl.
  simulerad plist-klassificering, atomärhet, tray-kraschloggning och
  sessionsomstart.
- AC-7.9 **Multi-OS/design-rundan 2026-09-24:** (a) `set_process_dpi_aware()`
  anropas först i `main()` (Windows-kedja: Per-monitor → systemnivå →
  klassisk `SetProcessDPIAware`, aldrig kastande; no-op utanför Windows) -
  utan detta skalade Windows fönstret på HiDPI-skärmar och typsnitt/färger
  blev suddiga; nu ser temamodulens `ui_scale` rätt pixeltäthet.
  (b) `open_externally()` fick Linux-fallback-kedja (xdg-open → gio) och
  loggar i sessionsloggen när inget öppningsprogram finns i stället för
  att svälja felet tyst. (c) Startsynken av autostart loggar nu sitt
  resultat (`autostart: Startsynk: …`) så att en tyst trasig autostart
  syns vid felsökning. (d) Samtliga tre paletter (ljus/mörk/högkontrast)
  verifierade utan kontrastfel via `audit_palette()`. Verifierat:
  modulernas självtest (data/read/system), fallback-kedja med stubbad
  Popen, matchningsregression (flersidig + decide) och e2e --status.

### REQ-B7 (B) — Tolka bilderna & matcha på alla blad
(ANVÄNDARORDER 2026-08-26)
**AC-B7:**
- AC-7.1 `embedded_images()`/`ocr_embedded_images()`: största inbäddade
  bilderna (hela sidan, ej bara brevhuvud) OCR:as och läggs till som
  brödtext; tak 6 bilder/3 sidor så att det aldrig spårar.
- AC-7.2 Sidhuvud/sidfot samlas deduplicerat från ALLA sidor (inte bara
  sida 1–3), så avsändarens upprepade sidfotsrad väger på varje blad.
- AC-7.3 Utan pymupdf/OCR: tyst reserv (""), ingen krasch.
- AC-7.4 **Leverans 2026-08-26.**
- AC-7.5 **Leverans 2026-08-26, rond 3:** tray-ikonen visar köantalet som
  bricka (badge, cachad per värde, cachetak 32); `help_as_text()` memo-cachad;
  `--diag` och kraschloggen bär versionsbanner för alla fem modulerna +
  Python-version (support/felsökning).

### REQ-C7 (B) — Ignoreringsregler: ord & filnamnsmönster
(ANVÄNDARORDER 2026-08-26: "markera filer som innehåller ord, eller heter
som ignoreras") Filer som innehåller något av `ignore_words` eller vars
namn möter något av `ignore_filename_globs` hoppas över helt, även inuti
skanningsmappar; de lämnas orörda och loggas med ⊘.
**AC-C7:**
- AC-7.1 Nycklarna finns i settings; GUI-kort "Ignorera filer" med
  Lägg till ord/mönster och Ta bort; CLI respekterar dem i analyze.
- AC-7.2 Ny beslutsstatus "ignored" påverkar inte kö/historik negativt.
- AC-7.3 **Leverans 2026-08-26** (E2E: innehållsord + glob verifierade).
- AC-7.4 **Individuell filignorering (ANVÄNDARORDER 2026-09-24):**
  I granskningsrutan finns knappen "Ignorera filen" — markerar just
  DENNA fil permanent. Filen känns igen på INNEHÅLLET (sha256 +
  storlek som snabbfilter), så markeringen gäller även efter omdöpning
  eller flytt, medan en annan fil med samma namn men annat innehåll
  påverkas inte. Registret ligger i `ignored_files.json` (atomiskt,
  tak 5000 poster, mtime-cachat index) och kontrolleras i
  `SortEngine.analyze()` FÖRE läsningen, så en markerad fil OCR:as
  aldrig. GUI-kortet visar listan med "Sluta ignorera markerad".
  Verifierat: enhetstester (igenkänning/omdöpning/namnkrock/avmarkering)
  + E2E där markerad fil lämnas orörd medan syskonfilen sorteras.
  **Korrektur 2026-09-28 (loggfångad bugg):** klick på "Ignorera filen"
  för en fil som redan var markerad gav felmeddelandet "kunde inte
  ignoreras" och lämnade kvar posten i kön. Nu är "redan markerad" ett
  lyckat utfall: posten tas ur kön och loggas "(var redan markerad)".

### REQ-C8 (B) — Matchningsrundan 2026-10-05 ("10000000% matchning")
- AC-8.1 **Namn+kropp-samstämmighet:** stödord i filnamnet som även
  finns i själva brödtexten får +0,1 - namnet bekräftas av innehållet.
- AC-8.2 **Historikprior vid exakt oavgjort:** när två kategorier har
  exakt samma poäng och inget bevis-ID eller lärd modell avgör, vinner
  den med fler tidigare sorterade filer (`files_sorted`); lika historik
  = fråga som förr (oförändrad säkerhet). Verifierat med enhetstester.

### REQ-C1 (M) — Stödordets typ (styrka)
Ord/nr som känns igen som starka identifierare.
**AC-C1:**
- AC-1.1 Erkänner: `orgnr`, `vat`, `giro`, `domain`, `kod`.
- AC-1.2 Organisationsnummer kräver giltig Luhn-kontrollsiffra; annars
  behandlas som referensnummer.
- AC-1.3 Projektkoder (`IF26`, `AB-1200`, `K4711`) räknas som starka
  även mitt i löptext.

### REQ-C2 (M) — "Helt ord"-matchning
Ett stödord ska inte matcha mitt inne i ett längre annat ord, men ändå
tillåta vanliga dokumentbeteckningar.
**AC-C2:**
- AC-2.1 `glas` matchar inte `glasögonfodral`.
- AC-2.2 `IF26` matchar `IF26-2024`, `IF26_bilaga`, `IF26/A`, men inte
  `IF260` eller `IF26A`.
- AC-2.3 Små/stora bokstäver spelar ingen roll (normalisering).

### REQ-C3 (M) — Zonviktning (avsändare vs mottagare)
Träff i olika delar av dokumentet ska väga olika.
**AC-C3:**
- AC-3.1 Zonvikter i fallande ordning: sender(1.60), filename(1.30),
  header(1.25), pagehead(1.20), identity(1.15), pagefoot(1.15), body(1.00),
  recipient(0.30).
- AC-3.2 En faktura **till** Pilkington (namn bara i mottagarblocket) får
  betydligt lägre poäng än en **från** Pilkington (namn i brevhuvudet).
- AC-3.3 Alla träffar i mottagarblocket → `ask` (inte `auto`).
- AC-3.4 En kategori med ett **bevisat avsändar-ID** (starkt stödord på
  avsändarens plats: sender/header/identity/pagehead/pagefoot/filename)
  får en liten precision-boost (0.5 poäng per sådant bevis) så att den
  rankas tydligt över en kategori som bara matchade svag löptext.
  Boost-faktorn får bara påverka rangordning, aldrig vända en `ask`→`auto`.

### REQ-C4 (M) — Beslut (auto / ask / error)
`decide()` följer en försiktig tröskelkedja och skickar tvetydigt till
granskning.
**AC-C4:**
- AC-4.1 Kategorier med poäng under tröskeln skickas till `ask`.
- AC-4.2 Kategorier med för få olika stödord skickas till `ask`.
- AC-4.3 Otillräcklig marginal till tvåan (absolut och relativt) →
  `ask`.
- AC-4.4 Ett bevisat avsändar-ID (org.nr/domän/bankgiro på avsändarens
  plats) godkänns ensamt, utom när även tvåan är bevisad (`ask` då).
- AC-4.5 Otillräckligt läst text → `ask`.
- AC-4.6 `libreOffice` liknande generiska ord ignoreras via STOPWORDS.

### REQ-C5 (M) — Strikthetsnivåer
Användaren ska kunna välja hur säker appen måste vara.
**AC-C5:**
- AC-5.1 Nivåerna `los`, `normal`, `strikt`, `mycket_strikt`, `egen`
  väljs i Inställningar.
- AC-5.2 Varje nivå styr `min_score`, `ambiguity_margin`, `min_keywords`,
  `require_strong`, `score_ratio`, `min_text_chars`, `require_anchor`,
  `reject_recipient_only`.
- AC-5.3 Vid "Egen" används fälten som de står (användarens värden).
- AC-5.4 **ANVÄNDARORDER 2026-08-26 (2):** Automatisk flytt kräver minst
  **2** träffade stödord på normalnivån och uppåt. Ett *bevisat avsändar-ID*
  (AC-C4.4) räcker fortfarande ensamt. "Lös" behåller 1 ord som explicit
  riskläge.

### REQ-C6 (M) — Kategori med eget krav på antal stödord
En kategori ska kunna kräva fler stödord än nivån.
**AC-C6:**
- AC-6.1 `min_keywords` per kategori; 0 = följ nivån.
- AC-6.2 Kategori-innehavets krav visas i REGEL-kolumnen.

---

## D. Filflytt & mapphantering

### REQ-D1 (M) — Flytta/kopiera till rätt mapp
**AC-D1:**
- AC-1.1 `place_file()` skapar alla mappnivåer vid behov.
- AC-1.2 Åtgärden `move` är standard; `copy` kräver ingen ändrad mapplogik.
- AC-1.3 Mappnamn saneras med `safe_folder_name()`.

### REQ-D2 (M) — Aldrig skriva över
**AC-D2:**
- AC-2.1 Kollisioner ger `faktura (2).pdf` (standard `rename`).
- AC-2.2 `on_conflict` = `skip`/`overwrite` respekteras.
- AC-2.3 `dry_run` utför inga ändringar på disk, men returnerar målsökväg.

### REQ-D3 (M) — Läsa & bevaka på olika OS
**AC-D3:**
- AC-3.1 `FolderWatcher` pollar och kräver att filen är stabil (3 s) samt
  komplett (`%PDF-` … `%%EOF`).
- AC-3.2 Filer som skrivs pågående hoppas över och tas nästa svep.
- AC-3.3 `MultiFolderWatcher` bevakar flera mappar; en otillgänglig
  nätverksmapp blockerar inte de andra.

### REQ-D5 (B) — Undantagsmappar (ANVÄNDARORDER 2026-08-26)
Mappar som hoppas över vid skanning, **även när de ligger inuti en
inmapp** (t.ex. Arkiv/ eller redan sorterade undermappar).
**AC-D5:**
- AC-5.1 `settings["exclude_dirs"]` (lista) sparas och respekteras av
  `list_pdfs`, watchern, `all_input_files`, `rescan_targets` och CLI.
- AC-5.2 GUI: kort "Undantagna mappar" i Inställningar med Lägg till/Ta
  bort; bevakningen startas om vid ändring.
- AC-5.3 CLI: `--exclude MAPP`, upprepbar, adderas till settings-listan.
- AC-5.4 Rekursiv skanning skippar filer i undantagna mappar; icke-rekursiv
  skanning påverkas om hela inmappen undantas.
- AC-5.5 **Leverans 2026-08-26** (E2E-verifierad: fil i undantagen
  undermapp lämnas orörd).
**AC-D4:**
- AC-4.1 `SUBFOLDER_TEMPLATES` stödjer `{år}`, `{år}/{månad}`,
  `{år}-{månad}`, `{år}/{månadsnamn}`, `{kvartal}`.
- AC-4.2 `render_subfolder()` returnerar tomt vid tom mall eller saknat datum.
- AC-4.3 `date_fallback` = `none` | `unknown` (`Utan datum`) | `filedate`.
- AC-4.4 Redan sorterade filer flyttas inte när funktionen slås på.

---

## E. Regler & data (Rules)

### REQ-E1 (M) — Läs/skriv rules.json
**AC-E1:**
- AC-1.1 `Rules.load()`/`save()` läser/skriver `schema_version`,
  `updated`, `categories`.
- AC-1.2 Återinläsning av en sparad fil ger identiska kategorier och
  stödord.
- AC-1.3 Kategorifält `subfolder`, `min_keywords`, `files_sorted`
  överlever spara/läsa.

### REQ-E2 (M) — Olika sorters matchningsregler
**AC-E2:**
- AC-2.1 Lägga till, ta bort och byta namn på kategorier.
- AC-2.2 Lägga till/ta bort/flytta/ändra stödord.
- AC-2.3 Vikt och `whole_word` per stödord.

### REQ-E3 (M) — Namnkrockdetektering
**AC-E3:** Ett stödord använt av flera kategorier ska kunna rapporteras
(via `keyword_owners`) och varnas för i GUI:t.

### REQ-E4 (M) — Historik & ångra
**AC-E4:**
- AC-4.1 Varje flyttad fil loggas i `history.json` (tak 2000 poster).
- AC-4.2 `undo_event()` flyttar tillbaka filen till ursprunglig plats;
  för `copy` tas kopian bort.
- AC-4.3 Historiken kan rensas/replaceras via `replace_history()`.

---

## F. Grafiskt gränssnitt

### REQ-F1 (M) — Granskningsdialog (kärnan i inlärningen)
En osäker fil öppnas med **tio föreslagna stödord** som användaren bockar i.
**AC-F1:**
- AC-1.1 Dialog visar filnamn, storlek, sidor, läsmetod (text/OCR),
  appens gissning och var träffarna hittades.
- AC-1.2 Kandidater är förbockade för starka typer (`sender`, `orgnr`,
  `vat`, `company`, `domain`).
- AC-1.3 Användaren kan välja befintlig kategori eller skapa ny mapp
  (med gissat namn).
- AC-1.4 Knappar: Förhandsgranska, Hoppa över, Lägg i `_Osorterat`,
  "Spara & flytta".
- AC-1.5 "+ Eget ord…" låter användaren lägga till ett eget stödord.
- AC-1.6 **Leverans 2026-08-26 (ANVÄNDARORDER):** mushjulet i dialogen
  rullar **både stödordslistan och hela fönstret** (yttre rullyta runt allt
  utom knappraden), men ändrar aldrig värden i textfält (rullgardin/spinn/
  entry/text) — `_dialog_wheel()` returnerar "break" över fältwidgets,
  rullar listan när pekaren är i den och annars hela fönstret.
- AC-1.7 **Leverans 2026-08-26 (ANVÄNDARORDER):** kategorirullgardinen i
  granskningsdialogen är sökbar med typeahead: skriv "d" → hoppar direkt
  till första kategorin som börjar på D; upp/ner bläddrar endast i detta
  fält; okänt skrivet namn växlar till Ny mapp-läge.

### REQ-F2 (M) — Inlärning & omskanning
När användaren svarat ska appen lära sig och tillämpa regeln på allt
osorterat.
**AC-F2:**
- AC-2.1 Valda ord sparas som permanenta regler (om "Spara valda ord" är
  på).
- AC-2.2 Filen flyttas till vald kategori.
- AC-2.3 Filer som den nya regeln nu täcker tas automatiskt bort ur kön.
- AC-2.4 `rescan_after_learn` skannar om kön, inmapparna och `_Osorterat`
  i bakgrunden. Redan sorterade filer rörs aldrig.

### REQ-F3 (M) — Flikar
**AC-F3:**
- AC-3.1 Flikar: Sortera, Matchningar, Inställningar, Granska, Historik,
  JSON, Hjälp.
- AC-3.2 Statusrad längst ned visar PDF-motor och OCR-status.

### REQ-F4 (M) — Matchningar: sök, sortera och visa
**AC-F4:**
- AC-4.1 Kategorilista till vänster, stödord för vald kategori till höger.
- AC-4.2 Sökfält igenom alla kategorier.
- AC-4.3 Klick på rubrik sorterar; TYP, VIKT, HELT ORD, TRÄFFAR visas.
- AC-4.4 Varannan rad tonad + statusfärger (stark/weak/off).

### REQ-F5 (M) — **Ta bort matchningar i GUI** ⭐
Användaren ska kunna ta bort **både enskilda stödord** ur en kategori och
**en hel kategori (hela listan)** med alla dess stödord, direkt i
gränssnittet utan att öppna JSON-filen.
**AC-F5:**
- AC-5.1 **Enskilt stödord:** Markera ett/flera stödord i Matchningar →
  knappen "Ta bort" eller tangenten `Delete`. En bekräftelsedialog frågar
  först.
- AC-5.2 **Hela kategorin (hela listan):** Markera en kategori → knappen
  "Ta bort". Bekräftelse frågar klartext ("Ta bort kategorin X och alla
  dess stödord?").
- AC-5.3 Högerklicksmeny på ett stödord ska erbjuda "Ta bort"; högerklicksmeny
  på en kategori ska erbjuda "+ Ny kategori", "Byt namn" och "Ta bort kategori".
- AC-5.3b Både kategoriträdet och stödordslistan svarar på
  `Delete`-tangenten för borttagning.
- AC-5.4 Efter borttagning: `rules.save()` körs, regex-cachen rensas
  (`_PATTERN_CACHE.clear()`), och listan uppdateras.
- AC-5.5 **Redan sorterade filer påverkas inte** — bara framtida matchning.
- AC-5.6 Borttagning av en hel kategori tar även bort alla ingående
  stödord; kategorin försvinner ur kategorilistan.

> **Anmärkning.** `Rules.remove_keyword()` och `Rules.remove_category()`
> finns redan i lagringen (REQ-E2); detta krav säkerställer att hela
> kedjan är tydligt och robust tillgänglig i GUI:t, med bekräftelse,
> cache-rensning och uppdatering.

### REQ-F6 (B) — Historik-vy med Ångra
**AC-F6:**
- AC-6.1 Alla flyttade filer visas, senaste först.
- AC-6.2 Markera rader → "Ångra valda" flyttar tillbaka till ursprunglig plats.
- AC-6.3 Dubbelklick/knapp öppnar målfilen.

### REQ-F6b (B) — Matchningsrapport (Markdown) ⭐
Användaren ska kunna exportera en **rapport i Markdown** som sammanfattar
hur matchningen gått under en vald period (standard **10 dagar**), och som
kan visas upp/analyseras för att förbättra sorteringen.
**AC-F6b:**
- AC-6b.1 En knapp "Exportera rapport (MD)" på Historik-fliken samt
  kommandoradsflaggorna `--report` och `--report-days` producerar rapporten.
- AC-6b.2 Rapporten täcker de senaste N dagarna (standard 10) och sparas
  som `.md` (GUI: välj fil; CLI: `report_path()` med dagens datum).
- AC-6b.3 Rapporten innehåller: sammanfattning (total/auto/manuell/osorterat/
  OCR/datum), per-kategori-tabell, tvetydighetsfall, stödord med flest
  träffar, stödord som **aldrig träffat**, **namnkrockar** (ord i flera
  kategorier) och ett avsnitt med konkreta råd.
- AC-6b.4 Fältet `report_days` (default 10) finns i `DEFAULT_SETTINGS` och
  är justerbart i GUI:t.
- AC-6b.5 Rapporten genereras utan att ändra någon data — den läser bara
  `history.json` och `rules.json`.
- AC-6b.6 `build_matching_report(days)` returnerar giltig Markdown och
  hanterar tom historik utan att krascha.

### REQ-F7 (M) — JSON-flik
**AC-F7:**
- AC-7.1 Visa/redigera `rules.json` och `settings.json` direkt.
- AC-7.2 "Kontrollera" validerar och visar antal kategorier/stödord.
- AC-7.3 "Spara ändringar" skriver och uppdaterar appens tillstånd.
- AC-7.4 Historik är skrivskyddad i fliken.
- AC-7.5 Exportera/Importera regler som JSON.

### REQ-F8 (M) — Inställningar: mappar
**AC-F8:**
- AC-8.1 Lägga till flera inmappar, ta bort, öppna i utforskaren.
- AC-8.2 Välja utmapp.
- AC-8.3 Validering: in- och utmapp får inte vara samma mapp eller
  överlappa (inuti varandra), särskilt med "läs undermappar" på.
- AC-8.4 **Undermappar på som standard (ANVÄNDARORDER 2026-09-28: "ska
  även skanna undermapparna i vald mapp"):** `recursive` är True som
  standard och gamla installationer migreras en gång
  (`subfolders_enabled_v2`) till påslaget läge; kryssrutan råder därefter.
  Om toppnivån är tom men undermappar innehåller PDF:er frågar appen
  "Söka i undermappar också?" vid Sortera nu; vid bevakningsstart loggas
  en varning med antalet PDF:er i undermappar när de inte bevakas.
  Verifierat E2E: ny konfig hittar undermapparna, gammal false-konfig
  migreras och hittar dem därefter.

### REQ-F9 (M) — Inställningar: åtgärd och strikthet
**AC-F9:**
- AC-9.1 Åtgärd: Flytta/Kopiera; Testkörning (dry-run); Fråga när osäker.
- AC-9.2 Strikthetsnivå med tillhörande fält och beskrivningstext.

### REQ-F11 (B) — Fönster anpassas dynamiskt efter skärmstorlek
(ANVÄNDARORDER 2026-08-26) Huvudfönster och granskningsdialog ska aldrig
vara större än skärmen, centreras och behålla brukbara minsta mått även på
små skärmar.
**AC-F11:**
- AC-11.1 `_fit_geometry()` beräknar storlek/position från
  `winfo_screenwidth/height`: tänkt storlek på stora skärmar, nedanpassad
  på små.
- AC-11.2 `minsize` krymps på små skärmar så att fönstret alltid är
  åtkomligt; på 800×600 ryms fönstret (780×580), på 2560×1440 blir det
  1280×880 centrerat.
- AC-11.3 Gäller huvudfönstret och granskningsdialogen (oavsett om
  förhandsvisningen är på eller av).
- AC-11.4 **Leverans 2026-08-26.**

### REQ-F10 (M) — Inställningar: systemfält & autostart
**AC-F10:**
- AC-10.1 Starta automatiskt med datorn; starta minimerad; starta
  bevakning direkt; visa ikon i systemfältet; krysset minimerar.
- AC-10.2 Skapa skrivbordsgenväg; spara ikonfil.

---

## G. Systemfält & autostart (systemmodul)

### REQ-G1 (B) — Systemfältsikon med meny
**AC-G1:**
- AC-1.1 `TrayIcon.start()` lyckas bara om pystray är tillgängligt.
- AC-1.2 Meny: Visa fönster, Sortera nu, Bevakning (kryssad), Granska (N),
  Öppna utmappen, Avsluta.
- AC-1.3 All Tk-interaktion går via `App._post` (Tk är inte trådsäkert).
- AC-1.4 `refresh()` uppdaterar ikon och meny (grön prick när bevakning
  är på; räknare i titel).

### REQ-G2 (B) — Autostart & genväg
**AC-G2:**
- AC-2.1 `set_autostart(True/False)` skriver till Windows-registret,
  macOS LaunchAgent eller Linux XDG-autostart.
- AC-2.2 `create_desktop_shortcut()` på Windows (`.lnk`) och Linux (`.desktop`).
- AC-2.3 `install_helpers()` skapar `.pyw`/`.command`/`.sh` för
  dubbelklicksstart utan terminal.
- AC-2.4 **Autostart v2.0 (LÅNAT MÖNSTER L3, leverans 2026-09-17):**
  `classify_autostart()` klassificerar OS-posten exakt: `missing |
  correct | stale_console | stale_path | stale_args | different`.
  `stale_console` (Windows-post som pekar på python.exe → konsol-blink
  vid inloggning) detekteras och repareras av `sync_autostart()`.
  Verify-after-write: varje påslag läses tillbaka och meddelandet får
  "(verifierad)" resp. varning. Roterad backup (max 10, JSON under
  `backups/`, mikrosekundstamp) tas före varje ändring/borttagning.
  `get_autostart_conflicts()` listar andra Run-poster som nämner appen
  (läs-only, rörs aldrig); visas i `--diag` och loggas vid GUI-klick.

### REQ-G3 (B) — Hjälptext
**AC-G3:**
- AC-3.1 Fliken Hjälp visar `HELP_CONTENT` med rubriker, punkter, kod och
  notiser.
- AC-3.2 "Spara hjälpen som textfil" skriver `help_as_text()`.

### REQ-G4 (K) — Ikon genereras i kod
**AC-G4:**
- AC-4.1 `make_icon_image(size, active)` returnerar en PIL-bild utan
  extern bildfil.
- AC-4.2 `write_icon_file()` sparar `.ico` (flera lager) eller `.png`.
- AC-4.3 `ensure_icon_file()` skapar/påminner ikonfil i konfigmappen.

---

## H. Utseende (temamodul)

### REQ-H1 (B) — Genomgående tema
**AC-H1:**
- AC-1.1 `COLORS` och `Theme` ger kort, knappar, flikar, tabeller, fält,
  kryss/radio, rullningslister och statusrad ett sammanhållet utseende.
- AC-1.2 `Theme.card()`, `zebra()`, `fit_columns()` fungerar i GUI:t.
- AC-1.3 Saknas modulen används Tkinter-standardutseende (REQ-A2).

### REQ-H3 (B) — Mörkt läge, växlingsbart live (ANVÄNDARORDER 2026-08-26: design)
`COLORS_DARK` med exakt samma nycklar som `COLORS`; `Theme(root, ttk, dark)`
byter hela ttk-stilbilden direkt. Inställningar → Tema (Ljust/Mörkt) växlar
utan omstart; råa Tk-widgetar (listor, logg, textfält, zebror) färgas om
via `_retint_raw()`. Reservtemat (temamodulen saknas) har egen mörk palett.
**AC-H3:**
- AC-3.1 Valet sparas i `settings["theme"]` och gäller vid nästa start.
- AC-3.2 Växling påverkar inte sorteringen eller någon data.
- AC-3.3 Statusfärger och piller finns i läsbara varianter mot mörk botten.
- AC-3.4 **Leverans 2026-08-26 (tema lager 2):** båda paletterna passerar
  WCAG-kontrastrevision (`audit_palette`): normal text ≥4,5:1, större/fet
  ≥3:1; provkartan visar kontraststatus live.
- AC-3.5 HiDPI: typsnitt skalas efter pixeltäthet (1,1/1,25×) så att UI:t
  inte blir pyttelitet på 4K-skärmar.
- AC-3.6 Alla ttk-anrop guardade (`_cfg/_map/_layout`): okänd option på
  exotisk tk-build kan aldrig krascha eller låsa starten.
- AC-3.7 **Leverans 2026-08-26, rond 3:** `COLORS_HC` (högkontrast, svart/vit/
  gul, brödtext ≥7:1, WCAG-ren) väljs via `Theme(..., contrast="high")`;
  `audit_palette` memo-cachad; typsnittsfamiljer cachade per fönster;
  provkartan har Högkontrast-växel.

### REQ-N12 (B) — Tangentbordsfirst granskningsdialog (KOMMANDE, förslag 51)
(ANVÄNDARORDER 2026-08-26: läggs till som kommande, **implementeras INTE
förrän beställaren uttryckligen säger till** — REQ-K4.)
**AC-N12:**
- AC-12.1 I granskningsdialogen styr tangentbordet kandidatlistan:
  upp/ner flyttar fokus, space bockar/avbockar, 1–9 växlar de nio första
  kandidaterna, Enter = "Spara & flytta", Esc = hoppa över.
- AC-12.2 Fokusindikatorn är tydligt synlig i båda temana (REQ-H3).
- AC-12.3 Musen fungerar exakt som idag; tangentbordet är ett tillägg.
- AC-12.4 Status: **KOMMANDE** — ingen kod ändras förrän order ges.

### REQ-H2 (B) — Statuspiller i temasystemet (ANVÄNDARORDER 2026-08-26: design)
Viktiga tillstånd visas som färgade "piller" ur temat, inte som utspridda
färgattribut: bevakning PÅ/AV och TESTKÖRNING på handlingsraden.
**AC-H2:**
- AC-2.1 `PillOk/PillWarn/PillErr/PillAccent/PillMuted` finns i både riktigt
  tema och reservtema.
- AC-2.2 Bevakning PÅ = grön pille, AV = neutral; testkörning visar gul
  pille endast när den är påslagen.

---

## I. Prestanda & robusthet

### REQ-I1 (M) — Textcache
**AC-I1:**
- AC-1.1 `TextCache` nycklar på (sökväg, storlek, mtime), ogiltig vid ändring.
- AC-1.2 Tak 4000 poster; äldsta poppas.
- AC-1.3 OCR-text cachas så omskanning inte OCR:ar om samma filer.

### REQ-I2 (M) — Robusthet
**AC-I2:**
- AC-2.1 Transienta läs-/flyttfel får inte krascha appen.
- AC-2.2 Trasig/fel JSON hanteras (läggs undan som `.broken-<tid>`, appen
  fortsätter med tomt).
- AC-2.3 Flytt mellan diskar sker via kopiera+radera (säker flytt).
- AC-2.4 `open`/flytt av låst fil loggas som fel och lämnas orörd.
- AC-2.5 **Självläkning (leverans 2026-08-26):** varje lyckad JSON-skrivning
  speglas till `.bak`; vid korrupt huvudfil återställs innehållet automatiskt
  från senaste bra kopian (och huvudfilen skrivs tillbaka), medan den trasiga
  sparas undan för inspektion.
- AC-2.6 **Ingen frysning (leverans 2026-08-26, "50000 % bättre"):**
  historiken är append-only-journal med kompaktering var 25:e händelse och
  `flush_history()` vid avslut — batchsortering skriver inte om hela filen
  per flytt; journalen spelas upp efter krasch.
- AC-2.7 Transienta I/O-fel prövas igen med backoff (`_with_retry`, 3
  försök); `_io_lock()` väntar högst 15 s och fortsätter sedan utan lås
  (atomiska skrivningar skyddar) i stället för att frysa.
- AC-2.8 **Leverans 2026-08-26, rond 3 (snabbhet/minne):** orjson-snabbspår
  med json-fallback; buffrad journalhandle (öppen, flush var 10:e rad / vid
  kompaktering); mtime-cache så att upprepade `load_history()` inte reparsar;
  `Rules` med inverterat ordindex (O(1) `keyword_owners`/`all_keyword_texts`).
- AC-2.9 **Data-rundan 2026-09-17:** (a) pythonw-säkerhet: `_diag()` skriver
  aldrig till `sys.stderr` när den är `None` (autostart utan konsol kunde
  annars krascha i låsväktaren). (b) `InstanceLock.acquire()` bekräftar
  efter skrivningen att det är eget pid i låset — två samtidiga starter
  (autostart + dubbelklick) kan inte längre båda tro att de vann; förloraren
  får den andres pid/starttid och ger sig. (c) Journalhandlen är radbuffrad
  (`buffering=1`, ersätter AC-2.8:s "var 10:e rad"): en hårt avbruten
  process förlorar aldrig en skriven historikrad. (d) `config_dir()` cachad
  per `PDFSORTER_HOME`-värde (en mkdir i stället för en per filoperation).
  Verifierat: modulens självtest + 15 riktade tester inkl. simulerad
  låskapplöpning, stderr=None, radbuffring och .bak-självläkning.

- AC-2.11 **Inga konsolfönster vid underprocesser (ANVÄNDARORDER
  2026-10-05: "ska ej öppna konsolfönster vid varje matchning"):** på
  Windows patchas `subprocess.run/Popen` globalt vid import (endast win)
  med `CREATE_NO_WINDOW` + `STARTF_USESHOWWINDOW/SW_HIDE` via setdefault,
  så att ALLA barnprocesser - inklusive pytesseracts interna
  tesseract-anrop per OCR-sida - startar dolda under pythonw. Egna
  anrop i read (pdftoppm) och system (winget/installer/powershell) får
  dessutom `_win_dold()`-kwargs för fristående körning. Linux/macOS
  opåverkade; anrop som själva begär konsol behåller sitt beteende.

### REQ-I3 (B) — Enkelinstans vid GUI-start
**AC-I3:** Vid GUI-start fångas ett redan körande exempel, och det andra
fönstret visas i stället.

### REQ-I4 (B) — Parallell analys av filbatches (ANVÄNDARORDER 2026-08-26: snabbare)
Sortering och omskanning läser flera PDF:er samtidigt; själva flytten till
disk serialiseras så att säkerhetsreglerna håller även under kapplöpning.
**AC-I4:**
- AC-4.1 `_sort_worker`/`_rescan_worker` analyserar filer parallellt
  (2–8 trådar efter kärnor).
- AC-4.2 `SortEngine.apply`/`send_to_unmatched` serialiserar placeringen;
  parallella flyttar med samma målnamn ger "(2)"-serie, aldrig överskrivning
  (verifierat med 8 samtidiga trådar).
- AC-4.3 Förlopp visas i procent på handlingsraden.
- AC-4.4 **Leverans 2026-08-26 (mycket snabbare):** OCR av flera sidor körs
  parallellt (upp till 4 trådar; Tesseract är subprocessbaserat).

### REQ-I5 (B) — Bestående diskcache för utläst text (ANVÄNDARORDER 2026-08-26: snabbare)
Minnescachen töms vid omstart; diskcachen (`cache/<hash>.json` i konfigmappen)
nycklas på samma signatur (sökväg+storlek+mtime) och gör andra starten lika
snabb som den första - skannade filer OCR:as aldrig två gånger.
**AC-I5:**
- AC-5.1 `read_pdf` prövar minnescache → diskcache → `extract()`, och fyller
  båda vid lyckad läsning.
- AC-5.2 Ändrad fil (ny signatur) träffar aldrig gammal cache.
- AC-5.3 Tak 1500 poster med enkel LRU-städning; cachefel är tysta och
  ofarliga (REQ-I2).
- AC-5.4 **Leverans 2026-08-26:** `DiskTextCache` på plats och verifierad
  (extract() anropas inte vid cacheträff).

### REQ-I6 (M) — Låg minnesanvändning (ANVÄNDARORDER 2026-08-26)
Appen ska inte använda mycket av datorns minne: alla cachar begränsas i
 både antal och byte, och bestående lagring flyttas från RAM till disk.
**AC-I6:**
- AC-6.1 `TextCache` tak: MAX_ENTRIES=800 OCH MAX_BYTES≈24 MB; äldsta posten
  ryker först; byte-räknaren uppdateras vid put/forget/clear.
- AC-6.2 `_PATTERN_CACHE` tak 4000 mönster; töms vid taket och byggs billigt
  upp igen.
- AC-6.3 Bestående textcache ligger på disk (REQ-I5), inte i RAM.
- AC-6.4 OCR-/analystrådar är takade (4 respektive 8) och alla PIL-bilder
  stängs efter användning.
- AC-6.5 GUI-historiken visar endast de 500 senaste raderna.
- AC-6.6 **Leverans 2026-08-26.**

### REQ-I8 (B) — Huvudmodulen, lager 2 (leverans 2026-08-26,
"50000 % bättre, får ej låsa sig")
**AC-I8:**
- AC-8.1 Dödlåsningsfri dubblettfråga: från UI-tråden visas dialogen direkt
  (att posta till kön och vänta skulle blockera i 120 s, kön pumpas av samma
  tråd); workertrådar postar+väntar som förr.
- AC-8.2 `_sort_worker`/`_rescan_worker` i try/finally: `_finish_run`/
  `_rescan_done` nås alltid, så `_busy`/`_rescanning` kan aldrig låsa knappar.
- AC-8.3 Debouncad `rules.save()` (högst 1 skrivning/sekund under batch) +
  `flush_rules()` vid batchslut.
- AC-8.4 Zoncache (`_zones_for`, sha1-nyckel, tak 200): samma dokument som
  beslutas flera gånger bygger zonerna bara en gång.
- AC-8.5 `list_pdfs` använder `os.scandir` (snabbare på Windows/nätverk);
  `FolderWatcher` hoppar över glob när mappens mtime är oförändrad
  (icke-rekursivt och inga väntande filer).
- AC-8.6 Textcachestat loggas vid varje batchslut (felsökning).

### REQ-I9 (B) — Huvudmodulen, lager 3 (leverans 2026-08-26)
**AC-I9:**
- AC-9.1 Samradsboost: två träffade stödord på samma råtextrad ger +0,25
  (avsändarens egen rad är starkare bevis än spridda träffar).
- AC-9.2 Loggraden vid auto-flytt visar zonuppslag per träff ("ord:zon"),
  så felsorteringar syns direkt i loggen.
- AC-9.3 Högkontrast kopplat i GUI: Tema-radens kontrast-radio (Normal/Hög)
  växlar `COLORS_HC` live; sparas i `settings["contrast"]`.
- AC-9.4 `_warm_patterns()`: alla stödordsmönster förkompileras vid start
  och efter import/JSON-spara (första svepet slipper kompilera mitt i).
- AC-9.5 Förhandsvisningsbilder släpps när granskningsdialogen stängs.

---

## J. Kommandorad

### REQ-J1 (M) — Kommandoradsparametrar
**AC-J1:**
- AC-1.1 `--status`, `--input/-i`, `--output/-o`, `--rules`, `--watch`,
  `--no-ask`, `--dry-run`, `--copy`, `--verbose/-v`, `--json`, `--tray`,
  `--install-autostart`, `--remove-autostart`, `--make-shortcut`,
  `--save-icon`, `--version`.
- AC-1.2 Utan argument startas GUI:t.

### REQ-J2 (B) — Headless-läge
**AC-J2:**
- AC-2.1 `--input/--output/--no-ask` kör sortering utan fönster.
- AC-2.2 `--json` skriver resultat som JSON.
- AC-2.3 Fungerar utan display (t.ex. schemalagd körning).

---

## K. Framtida/förbättringsbehov — avsiktligt inlagda av beställaren

### REQ-K1 (B) — 25 förbättringsförslag användaren kan importera eller inte ⭐
Appen ska kunna föreslå upp till **25 förbättringsförslag** som gör appen
bättre, och användaren ska kunna välja att **importera** dem
(postiva/att-göra) **eller hoppa över** dem.
**AC-K1:**
- AC-1.1 Förslagen presenteras i ett tydligt avsnitt (t.ex. i en ny
  "Förslag"-flik eller dialog), med upp till 25 objekt, var för sig.
- AC-1.2 Varje förslag har en kort titel, beskrivning och en möjlig
  klassning (t.ex. ny funktion / förbättring / buggfix).
- AC-1.3 Användaren kan välja "Importera" (samla in/skicka vidare), "Hoppa
  över", eller markera/avmarkera individuella förslag.
- AC-1.4 Ett besparat val ska vara ihågkommet mellan körningar.
- AC-1.5 Att importera ett förslag påverkar inte något befintligt
  stödord, kategori eller någon sorterad fil.

### REQ-K2 (M) — Förbättringsförslag efter var tionde koduppdatering ⭐
Efter **tio koduppdateringscykler** ska en ny omgång förbättringsförslag
presenteras för användaren.
**AC-K2:**
- AC-2.1 Systemet håller räkning på antalet koduppdateringscykler.
- AC-2.2 Vid den tionde cykeln ska förslagen (REQ-K1) presenteras.
- AC-2.3 Förslagen får inte vara påträngande — de meddelas, och användaren
  väljer själv vad som händer.
- AC-2.4 Samma förslag presenteras inte om igen efter att det redan
  hanterats.

> **Utvecklingsprocess (förvaring):** REQ-K1/K2 beskriver dels en
> användarfunktion, dels en del av utvecklingsprocessen: efter tio
> iterationer av kodändringar ska påminnelsen om att ta fram och bjuda in
> till förbättringsförslag tas fram.

### REQ-K3 (B) — Utlösare via tangentordet "förslag" ⭐
När användaren skriver **"förslag"** (som ett utlösande tangentord, t.ex.
som kortkommandorad i chatt/Inmatning) ska appen omedelbart **ta fram och
visa** upp till 25 förbättringsförslag (REQ-K1) att välja från.
(ANVÄNDARORDER 2026-09-24: förslagen ska förbättra appen brett — **kod,
design, minne, snabbhet, matchning, allt** — inte bara en avgränsad del.)
**AC-K3:**
- AC-3.1 Att skriva "förslag" (fristående ord) i avsedd inmatning tolkas
  som utlösare och öppnar förslagsvyn från REQ-K1.
- AC-3.2 Det måste gå att stänga förslagsvyn utan att göra något val.
- AC-3.3 Utlösaren får inte krocka med vanlig inmatning av stödord —
  den aktiveras bara i det avsedda sammanhanget.
- AC-3.4 Att välja/avmarkera förslag följer de regler som definieras i
  REQ-K1 (importera / hoppa över, ihågkommet val).

### REQ-K5 (B) — Utlösare via tangentordet "lista" ⭐
(ANVÄNDARORDER 2026-09-24.) När användaren skriver **"lista"** visas en
**checklista från specen**: alla öppna punkter att välja bland —
KOMMANDE-krav (REQ-N*) och VÄNTAR-förslag ur förslagsloggen, grupperade
och med status. Syftet är att användaren snabbt ska se vad som finns att
ta av och kunna peka ut vad som ska implementeras.
**AC-K5:**
- AC-5.1 "lista" visar checklistan: KOMMANDE-kön + alla VÄNTAR-förslag
  (nummer + kort titel), grupperade så att det går att välja med nummer.
- AC-5.2 Redan levererade/godkända punkter markeras tydligt (eller
  utelämnas) så att listan bara visar valbara punkter.
- AC-5.3 Att välja en punkt följer REQ-K4: valet registreras som order,
  inget byggs utan uttryckligt val.
- AC-5.4 Utlösaren aktiveras bara som fristående ord i det avsedda
  sammanhanget (krockar inte med stödord/inmatning).

### REQ-K6 (B) — Utlösare via tangentordet "forskning" ⭐
(ANVÄNDARORDER 2026-09-24.) När användaren skriver **"forskning"** görs
en omvärldsundersökning: **liknande appar** (PDF-sortering,
dokumentautomatisering, bevakning av mappar, OCR-flöden) undersöks och
deras funktioner rapporteras — med bedömningen om/när något av det går
att implementera i PDF Sorter.
**AC-K6:**
- AC-6.1 "forskning" presenterar funktioner hos jämförbara appar, med
  kort beskrivning och en rekommendation (värt att ha / inte relevant).
- AC-6.2 Varje fynd som bedöms användbart föreslås som kandidat — men
  inget implementeras förrän beställaren väljer det (REQ-K4 gäller).
- AC-6.3 Fynd som redan finns i appen eller i förslagsloggen hänvisas
  till befintligt nummer/krav i stället för att dubbleras.
- AC-6.4 Utlösaren aktiveras bara som fristående ord i det avsedda
  sammanhanget.

---

### REQ-K4 (M) — Kommande förslag förblir kommande tills beställaren säger till
(ANVÄNDARORDER 2026-08-26) Förslag som väljs/importeras från förslagslistan
tilldelas krav-ID men **implementeras inte automatiskt** — de ligger som
KOMMANDE tills beställaren uttryckligen ger klartecken.
**AC-K4:**
- AC-4.1 Valda förslag får REQ-ID och noteras i spec + förslagslogg med
  status KOMMANDE.
- AC-4.2 Implementering börjar endast vid uttrycklig order (t.ex. "kör N3",
  "bygg nu").
- AC-4.3 Beställaren kan när som helst skjuta upp, avbryta eller avbeställa
  utan att andra krav påverkas.
- AC-4.4 Regeln gäller även funktioner som redan kodlevererats men är
  avstängda i väntan på order (t.ex. N7, `preview_in_dialog=False`).
## L. Robusthet mot nya krav — tillägg som ska hållas

### REQ-L1 (M) — Ta bort matchningar i GUI (se REQ-F5)
Se REQ-F5. Detta är ett av beställarens uttryckliga tillägg och ska
tolkas tillsammans med REQ-F5.

---

## M. Sammanfattning av prioriteringar

| Kategori | Krav-ID | Tack till... |
|----------|---------|--------------|
| Struktur/paket | REQ-A1..A4 | Filer, tålighet, enkelinstans, konfigkatalog |
| Läsning/OCR | REQ-B1..B7 | Motorfallback, OCR, logotyp, bättre OCR, datum, läsningshärdning, bildtolk |
| Matchning | REQ-C1..C7 | Styrka, helt-ord, zon, beslut, nivåer, kategorikrav, ignorering |
| Filflytt | REQ-D1..D5 | Flytt, ej över, bevakning, undermapp, undantagsmappar |
| Data | REQ-E1..E4 | Rules, matchningar, krock, historik |
| GUI | REQ-F1..F11 | Dialog, inlärning, flikar, ta bort, JSON, inställningar, skärmanpassning |
| System | REQ-G1..G7 | Tray, autostart, hjälp, ikon, självläkning, hängskydd, ikoncache |
| Tema | REQ-H1..H3 | Utseende, statuspiller, mörkt läge |
| Prestanda/robusthet | REQ-I1..I9 | Cache, robusthet, enkelinstans, parallell analys, diskcache, minnestak, huvudmodul lager 2–3 |
| CLI | REQ-J1..J2 | Parametrar, headless |
| Framtid | REQ-K1..K6 | 25 förslag, efter 10 uppdateringar, utlösare "förslag", kommande-kö, utlösare "lista" (checklista), utlösare "forskning" (omvärld) |
| Tillägg | REQ-L1 | Ta bort matchningar i GUI |
| Kommande | REQ-N1..N14 | Godkända förslag, omgång 1–3 (2026-08-26) + forskning. N1 levererad 2026-09-07 (sessionslogg), N13 levererad 2026-09-07 (flersidig matchning). N14 LEVERERAD 2026-09-28 (lärande klassificerare) |

**Måste (M):** REQ-A1, A2, A3, A4, B1, B2, B3, B5, C1, C2, C3, C4, C5, C6,
D1, D2, D3, D4, E1, E2, E3, E4, F1, F2, F3, F4, F5, F7, F8, F9, F10, I1,
I2, I6, J1, K2, K4, L1
**Bör (B):** REQ-B4, B6, B7, C7, D5, F6, F6b, F11, G1, G2, G3, G5, G6, G7, H1, H2, H3, I3, I4, I5, I8, I9, J2, K1, K3, N1, N2, N3, N4, N5, N6, N7, N8, N9, N10, N11, N12, N13
**Kan (K):** REQ-G4

---

## N. Godkända kommande funktioner — förslagsomgång 1 (2026-08-26)

Godkända via utlösaren **"förslag"** (REQ-K3). Importerade förslag påverkar
inte befintliga stödord, kategorier eller sorterade filer (AC-K1.5).
Revidering: omgång 1 delvis behandlad 2026-08-26 — förslag 3, 7, 8 och 12
importerades (12 med beställarens ändring), plus två nya effektmål
("5000 % bättre" läsning och matchning). Övriga förslag i omgången kvarstår
som VÄNTAR i `PDFSORTER_FORSLAG.md`.

### REQ-N1 (B) — Kategoriserade månadsloggar med session-id
`krasch.log` kompletteras med ett riktigt loggsystem: `logs/<ÅÅÅÅ-MM>/`
med `app.log`, `gui.log` och `errors.log` (roterande, 5 MB × 3, UTF-8).
Varje session får ett SESSION_ID (uuid[:12]) som skrivs i startbanderollen.
`sys.excepthook` och `threading.excepthook` fångar alla fel till errors.log.
**AC-N1:**
- AC-1.1 Uppstart, avstängning och alla fel loggas med session-id.
- AC-1.2 Loggar hamnar i månadsundermapp; äldre månader raderas aldrig
  automatiskt.
- AC-1.3 Ohanterade undantag i valfri tråd fångas, loggas och sänker inte
  appen i tysthet.
- AC-1.4 **Delleverans 2026-08-26:** `crash_report` skriver nu även till
  `logs/<ÅÅÅÅ-MM>/errors.log` (månadsloggar, ingen auto-rensning).
  Kategoriserad app/gui-loggning återstår.
- AC-1.5 **Leverans 2026-09-07 (ANVÄNDARORDER: logga precis allt):**
  Fullständig sessionslogg implementerad. Varje körning öppnar
  `logs/<ÅÅÅÅ-MM>/app_<datum>_<tid>_<session-id>.log` med startbanderoll
  (version, modulversioner, plattform, kommandorad). ALLT loggas med
  tidsstämpel (ms), nivå och kategori: starter, inställningar, varje
  knapptryck (`ui`), VARFÖR fönstret visas eller inte visas (`fönster`,
  med anledning vid show/hide/minimering/--tray), bevakhändelser, varje
  matchningsbeslut med poäng/zoner/flersidiga bevis, flyttar, dubblett-
  frågor och svar, granskningsdialogens öppning/svar, fel med full
  spårning, och avslut. Loggen roterar vid 8 MB till stabila delnamn
  (`_del2`, `_del3`, …). `sys.excepthook` + `threading.excepthook`
  fångar alla ohanterade fel till sessionsloggen + `errors.log` utan
  att sänka appen. `krasch.log` flyttad in i `logs/` (alla loggar på
  ett ställe). Ny knapp \"Kopiera loggen för support\" lägger hela
  loggen i urklipp så att användaren kan klistra in och få problemet
  identifierat direkt; `--status` och `--diag` visar loggsökvägen.
- AC-1.6 Kategorier i loggen: `start`, `gui`, `sortering`, `bevaka`,
  `fönster`, `ui`, `inställningar`, `mappar`, `granska`, `dubblett`,
  `systemfält`, `avslut`, `krasch`, `oväntat`, `support`, `cli`, `tid`,
  `autostart`, `logg`.
- AC-1.7 **Diagnostikpaket (LÅNAT MÖNSTER L1, leverans 2026-09-17):**
  `build_diagnostics()` bygger ETT klistra-in-block (versionsbanner,
  Python/plattform, alla inställningar, regelräkning, läsmotorer,
  OCR-hälsa, autostartklass + konflikter, svansar från sessionslogg/
  errors/krasch). Knappen "Kopiera diagnostik för support" lägger
  paketet + hela sessionsloggen i urklipp (tak 400 kB, slutet aldrig
  avkapat). CLI: `--diagnostik` skriver paketet till stdout.
- AC-1.8 **LogContext (LÅNAT MÖNSTER L5, leverans 2026-09-17):**
  `LogContext(kategori, etikett)` loggar `▶ START` / `✔ KLART (N ms)` /
  `✗ FEL (N ms): exc` till sessionsloggen. Används runt per-fil-analys
  (`tid`) och batchsortering; undantag loggas och propagerar.
- AC-1.9 **Loggmigrering (LÅNAT MÖNSTER L7, leverans 2026-09-17):**
  `migrate_legacy_logs()` körs vid sessionsstart: äldre `krasch.log` i
  config-roten flyttas till `logs/krasch.log`; finns redan en ny
  parkeras den gamla som `krasch-gammal.log` (nyast vinner, inget
  raderas).
- AC-1.10 **Tilläggsdialog vid start (ANVÄNDARORDER 2026-09-28):**
  strax efter start erbjuder appen installation av saknade valfria
  tillägg (Tesseract OCR, pytesseract, PyMuPDF, pdftoppm, pystray) med
  förklaring av vad varje del ger. Knappar: "Installera Python-paket"
  (pip i bakgrundstråd med resultatlogg), **"Installera Tesseract
  automatiskt"** (Windows: winget `UB-Mannheim.TesseractOCR`, med tyst
  fallback: nedladdning av UB Mannheims NSIS-installer + `/S`; därefter
  automatisk hämtning av `swe.traineddata` till tessdata-katalogen.
  Alla steg loggas; nätverksfel blir meddelanden), "Hämta Tesseract…"
  (öppnar nedladdningssidan), "Kontrollera igen", samt "Visa inte
  igen" (`extensions_offer_hidden`). `tesseract_binary()` hittar även
  användarnivåinstallationer (LOCALAPPDATA). **Manuell installation på
  udda ställe (korrektur 2026-09-28):** `set_tesseract_path()` +
  inställningen `tesseract_path` pekar ut tesseract.exe direkt och
  kontrolleras först av `tesseract_binary()`. Dialogen har "Sök datorn"
  (`search_tesseract()`: begränsad genomsökning av rot/Program*/
  undermappar, aldrig hela disken) och "Bläddra…" som sparar träffen;
  valet gäller direkt vid nästa start. Aldrig blockerande: hela bygget i
  try/except, headless/CLI påverkas inte. Loggfångat från användarens
  maskin: 100+ skannade PDF:er felade med "skannad PDF utan OCR".
- AC-1.12 **Tray-zombiefix + loggarkivering (ANVÄNDARORDER 2026-10-15):**
  (a) Bugg: en felrapport som skapade ett ANDRA Tk-fönster i samma
  process (t.ex. från tray-tråden) kunde vid destroy() riva huvud-
  fönstret ("application has been destroyed"); tray-tråden höll sedan
  processen och instanslåset som zombie - appen gick inte att öppna
  efter tray-minimering. Fix: crash_report visar dialog ENDAST från
  huvudtråden och ENDAST när inget Tk-fönster lever; `_process_queue`
  och `show_window` garderas med `winfo_exists()` (tydlig logg i stället
  för TclError-spam); `App.run()` avslutar processen hårt när mainloop
  tar slut med dött fönster (zombieskydd, flush först).
  (b) `archive_old_logs(3)` vid varje start: sessionsloggar äldre än
  3 dagar flyttas till `logs/arkiv/<ÅR>/<MÅNAD>/` - inget raderas.
- AC-1.11 **Autoinstall vid start (ANVÄNDARORDER 2026-10-06: "saknade
  python-tillbehör installeras/uppdateras automatiskt, visa progress
  bar"):** vid start kontrolleras pypdf/Pillow/pytesseract/pystray;
  saknade installeras automatiskt i bakgrundstråd med progressfönster
  (indeterminate bar + live pip-rader), aldrig blockerande. När pip
  blivit klart: status uppdateras, tray startas om pystray kom till,
  allt loggas. Dialogen har dessutom "Uppdatera Python-paket"
  (`pip install --upgrade` med samma progress). Tesseract/svenska
  hanteras som tidigare via dialogknapparna.

### REQ-H4 (B) — Moderniseringsrundan 2026-10-06 (snabbtangenter + design)
(ANVÄNDARORDER: "snabbknapp på alla dropdown menyer ... enkelhet, design,
kod, tema, modern".)
- AC-4.1 **Typahead överallt:** `install_snabbtangenter()` sätter
  klassbindningar på ALLA `TCombobox`/`Listbox` (även framtida, i
  dialoger): bokstav hoppar till första träffen, samma bokstav igen =
  nästa träff; Ctrl-kombinationer och navigeringstangenter fria.
  Granskningsdialogens combo behåller sitt eget beteende (växlar till
  "ny mapp" vid okänt namn) via `_egen_ta`-markering.
- AC-4.2 **Mörk titellist** (`dark_titlebar`, Windows 10+ DWM): huvud-
  fönster, gransknings-, dubblett- och progressfönster följer temat -
  mörk lista i mörkt läge, ljus i ljust; no-op på andra plattformar.
- AC-4.3 Testat: hopp-logik (lista + combobox + cykel + egen_ta), 6/6
  kompilerar, --version/--status gröna.

### REQ-N13 (B) — Flersidig matchning (ANVÄNDARORDER 2026-09-07)
Matchningen ska använda bevis från HELA dokumentet, inte bara första
sidan. Varje ord räknas över de sidor det förekommer på; ord som
upprepas på ≥2 sidor (typiskt firmanamnet i brevhuvud/sidfot som följer
med varje blad) är starka avsändarbevis och får ett poängtillägg.
**AC-N13:**
- AC-13.1 `pdfsorter_read.token_page_counts(page_texts)` räknar
  token -> antal sidor. Endast tokens på ≥2 sidor sparas (de ensidiga
  ger inget bevis och skulle bara äta minne); tak `TOKEN_PAGES_MAX=3000`
  med de vanligaste bevarade.
- AC-13.2 PyMuPDF- och pypdf-vägarna samlar text per sida och lagrar
  räkningen som `_token_pages` i metadata; OCR-vägen bevarar sidgränser
  med `\f` så att `extract()` kan räkna sidor även för skannade dokument.
- AC-13.3 `Extraction.token_pages` serialiseras i `to_cache_dict`/
  `from_cache_dict` så att diskcachen behåller bevisen.
- AC-13.4 `score_text(..., token_pages)` ger +0,15 per stödord vars alla
  delar finns på ≥2 sidor, max +0,45 per kategori. Tillägget ändrar
  rangordningen till förmån för den verkliga avsändaren men lyfter inte
  ensamt en kategori över auto-gränsen. `CategoryScore.multipage` listar
  bevisen (\"pilkington ×4 sidor\").
- AC-13.5 GUI-loggen visar flersidiga bevis vid autoflytt
  (`[flersidig: …]`), så att en felsorterad kategori syns direkt.

### REQ-N14 (B) — Lärande klassificerare från historiken (LEVERERAD 2026-09-28)
(ANVÄNDARORDER 2026-09-24, från forskningsrunda 1.) Appen lär sig av sina
redan fattade beslut: en lokal, molnfri klassificerare byggs upp ur
historiken (fil → kategori + vilka ord som fanns i filen) och används som
**extra matchningsväg** när stödorden inte räcker för ett beslut — den
bryter dödlägen i granskningskön. Inspireation: Paperless-ngx tränar ML
på 20–30 manuellt arkiverade dokument; AI-fakturaprocessorer lär av
varje korrigering.
**AC-N14:**
- AC-14.1 Klassificeraren tränas på historikens beslut (auto + användar-
  val i granskning), helt lokalt, deterministiskt och utan nätverk/ML-
  paket — en ordvägare per kategori räcker för volymen.
- AC-14.2 Minst N fattade beslut per kategori (standard: 5, inställbart)
  krävs innan kategorins lärda profil används; under det är den tyst.
- AC-14.3 Den lärda profilen är en SVAG signal: den kan föreslå/förbättra
  rangordning och bryta nära-oavgjort, men lyfter ALDRIG ensam en fil
  över auto-gränsen på striktare nivå än "Lös" utan stödordsstöd.
  Användarens manuella beslut väger alltid tyngre än modellen.
- AC-14.4 Korrigeringar matas tillbaka: väljer användaren en annan
  kategori än den föreslagna uppdateras profilen (negativ inlärning för
  det falska spåret, kopplat till förslag #116).
- AC-14.5 Profilen följer med rules.json-säkerhetskopior och påverkar
  aldrig redan sorterade filer; den kan slås av helt i inställningarna
  (`learned_matching`, standard på efter beslut).
- AC-14.6 **LEVERERAD 2026-09-28:** `LearnedMatcher` (naiv Bayes,
  Laplace-mjukning + prior) i `learned_model.json`; träningsdata =
  `learn_tokens()` (~60 karakteristiska ord, stoppsord gallrade) som
  sparas i varje historikpost (`tokens`) och tränas stegvis vid varje
  flytt i `engine.apply()`, flush vid batchslut/avslut. Integration i
  `decide()`: (a) bryter regelgodkända dödlägen när marginalen är säker
  (≥0,25 i log-rummet) på någon av de två nära kandidaterna, (b) på
  nivån "Lös" auto-flyttar en säker modell ensam, (c) annars
  `learned_hint` som visas i granskningsrutan ("lärd: X – N liknande
  filer"). Kryssruta "Lärande matchning" i Inställningar
  (`learned_matching`, standard på). Verifierat: 14 tester (träning,
  prediktion, min_files-grind, dödläge, Lös-auto, hint, avstängd,
  träning-via-apply + journal/historik) + e2e-regression (auto 9,55).

### REQ-N2 (B) — requirements.txt med pinnade versioner
En `requirements.txt` bredvid `pdfsorter.py` med `==`-pinnade versioner för
`pymupdf`, `pypdf`, `pdfminer.six`, `pystray`, `Pillow` och `pytesseract`.
**AC-N2:**
- AC-2.1 Filen finns och pinningen motsvarar testad kombination.
  **Leverans 2026-08-26:** testad kombination (pypdf, Pillow) pinnad;
  övriga valfria paket anges som kommenterad installationsväg, eftersom
  appens reservvägar (REQ-A2) gör dem valfria per miljö.
- AC-2.2 Kommentar anger att samtliga beroenden är valfria (appens
  reservvägar gäller fortfarande, REQ-A2).

### REQ-N3 (B) — Diagnostikvy i GUI och --status
`get_diagnostics()` samlar version, PDF-motorer, OCR-status, textcachens
statistik, antal kategorier/stödord, historikposter, senaste backup och
diskanvändning per konfigkatalog. Visas som kort i gränssnittet och i
utökad form via `--status`.
**AC-N3:**
- AC-3.1 Diagnostiken är läsbar i GUI utan att öppna filer manuellt.
- AC-3.2 `--status` skriver samma uppgifter headless.
- AC-3.3 Diagnostiken ändrar ingen data — bara läsning.

### REQ-N4 (B) — Duplikatspärr med SHA-256 och obligatorisk fråga
Varje PDF:s innehållshash (SHA-256) beräknas vid läsning och sparas i
historiken. Upptäcks en dubblett — samma hash eller namnkrock i målmappen —
ska appen **alltid fråga användaren**: *Ersätt* eller *Behåll båda* (kopian
får "(2)" i namnet). Ingen tyst överskrivning, någonsin.
**AC-N4:**
- AC-4.1 SHA-256 beräknas och lagras i history-posten.
- AC-4.2 Vid dubblett visas dialog med valen "Ersätt" / "Behåll båda (2)";
  valet kan kommas ihåg för körningen ("Kom ihåg under denna körning").
- AC-4.3 Headless/bevakning utan fönster skriver aldrig över: standard är
  "Behåll båda (2)" och händelsen loggas tydligt.
- AC-4.4 **Leverans 2026-08-26:** `sha256_file()` i datamodulen; motorn
  upptäcker namnkrock OCH innehållsdubblett (storleksförfilter + hash),
  frågar via `ConflictDialog` (Ersätt / Behåll båda / Avbryt + "kom ihåg"),
  headless väljer behåll-båda och loggar; valet loggas i historikens
  `conflict`-fält. "Behåll båda" vid olika namn = båda filerna behålls
  med sina namn; "(2)" används vid namnkrock.
- AC-4.4 Flytt mellan diskar verifieras med hashen efter kopiering, före
  radering av källan.

### REQ-N5 (B) — Effektmål: 5000 % bättre avläsning av skannade PDF:er
Avläsningen (OCR-röret) av inskannade och svåra PDF:er ska förbättras
väsentligt. "5000 %" läses som ett *effektmål* mot dagens baslinje (jfr
REQ-B4:s anmärkning): felprocenten på nyckeluppgifter ska minska drastiskt,
inte en bokstavlig multiplikation.
**AC-N5:**
- AC-5.1 Referenskorpus + baslinje körs fram *innan* arbetet börjar; måttet
  är korrekt identifierade org.nr, firmanamn och datum.
- AC-5.2 Förbehandling (kontrast, binarisering, deskew, upplösning), bättre
  `--psm`/`--oem` och `swe+eng` används i läget Bättre OCR.
- AC-5.3 Textbaserade PDF:er får inte bli långsammare eller sämre —
  textlagret läses alltid först (REQ-B4 AC-4.5 gäller fortfarande).
- AC-5.4 **Delleverans 2026-08-26:** konfidensvald flerpasses-OCR
  (psm 3 på gråbild + psm 6 på Otsu-binariserad kopia, bästa medelkonfidens
  vinner) och C-snabb skevhetskorrigering är på plats. Referenskorpus och
  baslinje för det fulla effektmålet återstår.

### REQ-N6 (B) — Effektmål: 5000 % bättre matchning av skannade PDF:er
Matchningen på OCR-läst text ska närma sig textbaserad nivå: zonviktning,
helt-ord-logik och stödordsförslag måste tåla OCR-brus.
**AC-N6:**
- AC-6.1 Normaliseringen blir brus-tolerant (OCR-typiska teckenfel, t.ex.
  `0`/`O`, `1`/`l`, hopslagna ord) utan att tappa REQ-C2:s helt-ord-garanti.
- AC-6.2 Starka mönster (org.nr med Luhn, VAT, bankgiro, domän) matchas med
  fuzz-tolerans på OCR-text, men beviskraven (REQ-C4) sänks aldrig.
- AC-6.3 Samma referenskorpus som N5 används; andelen korrekt sorterade
  skannade filer ska öka markant mot baslinjen.
- AC-6.4 **Delleverans 2026-08-26:** `denoise_numbers()` (O/0, I/l/1 i
  sifferdominerade runor), avbrusade zonkopior i `TextZones` och
  OCR-tolerant `keyword_strength` är på plats — "556O33-9O86" räknas som
  org.nr med giltig Luhn, medan Luhn-fel fortfarande ger svagt stödord
  (REQ-C1 AC-1.2). Referenskorpus återstår.

### REQ-N7 (B) — Inbyggd PDF-förhandsvisning i granskningsdialogen
Granskningsdialogen (REQ-F1) visar dokumentet direkt: första sidan som
bild, med bläddring fram/bakåt, så att användaren kan bocka i stödord med
ögonen på själva fakturan i stället för att växla till ett externt program.
**AC-N7:**
- AC-7.1 Första sidan renderas som bild (PyMuPDF) i dialogen; renderingen
  sker i bakgrundstråd så dialogen öppnas direkt, med platshållare under
  tiden.
- AC-7.2 Knappar för föregående/nästa sida (minst de tre första sidorna).
- AC-7.3 Saknas PyMuPDF döljs förhandsvisningen och dialogen behåller
  knappen Förhandsgranska PDF (extern visning) — reservväg enligt REQ-A2.
- AC-7.4 Förhandsvisningen är skrivskyddad och påverkar inte matchning,
  regler eller filer (AC-K1.5).
- AC-7.5 Kodleverans finns (3 sidor, ‹/›-bläddring, bakgrundsrendering,
  pymupdf-fallback), men funktionen är **FRAMSKJUTEN** på beställarens
  order 2026-08-26: `settings["preview_in_dialog"] = False` är standard och
  förhandsvisningen visas inte förrän beställaren säger till. Koden är
  bortkopplad, inte borttagen (INGA FUNKTIONER TAS BORT).

---
*Detta är kontraktet för godkännande av PDF Sorter.*

## Omgång 8 (2026-10-15) — "25 förslag som gör allt bättre enklare"

| # | Titel | Klass |
|---|-------|-------|
| 176 | "Rekommenderade inställningar" - ett klick återställer en beprövad bas (strikthet normal, bevakning på m.m.) | Enkelhet |
| 177 | Konfidens-auto: osäkra filer där lärd modell är mycket säker sorteras utan fråga (fewer questions) | Enkelhet |
| 178 | Enkelt läge i granskningsdialogen: dölj avancerat, knapparna kvar (Spara & flytta / Hoppa / Ignorera) | Enkelhet |
| 179 | Klarspråk-läge: korta vardagliga texter i hela appen (väljs i Inställningar) | Enkelhet |
| 180 | Statusrad längst ned: sorterade idag / väntar / bevakning på - alltid synlig | Enkelhet |
| 181 | Dra en PDF på fönstret = sortera den direkt | Enkelhet |
| 182 | Dubbelklick på kö-rad öppnar granskningen direkt | Enkelhet |
| 183 | Snabbtangenter: F5 = Sortera nu, F2 = Granska, F1 = Hjälp | Enkelhet |
| 184 | "Ångra senaste flytten" som synlig knapp i verktygsraden | Enkelhet |
| 185 | Tray: dubbelklick = Sortera nu (enkelklick öppnar som idag) | Enkelhet |
| 186 | Notis med knappar: Öppna / Ignorera (i stället för bara text) | Enkelhet |
| 187 | Historik: filterknappar Idag / Vecka / Månad i ett klick | Enkelhet |
| 188 | "Kopiera veckosammanfattning" - ett klick ger kort rapport i urklipp | Enkelhet |
| 189 | Granskningsrutan föreslår kategori ur filnamnet med ett klick | Enkelhet |
| 190 | Inställningar i två lägen: Grund / Avancerat (kollapsade kort) | Enkelhet |
| 191 | Tyst läge: fönstret visas bara när appen behöver fråga något | Enkelhet |
| 192 | Dra en mapp till kategorilistan = ny kategori med mappens namn | Enkelhet |
| 193 | Förslag: slå ihop små kategorier (<3 filer) till "Diverse" efter bekräftelse | Enkelhet |
| 194 | Städ-läge: ett klick arkiverar gamla sorterade filer i år/månad-mappar | Enkelhet |
| 195 | Duplettdownload-koll ("fil (2).pdf") med förslag slå ihop/ignorera | Enkelhet |
| 196 | Supportpaket i ett klick: zip med diagnostik + loggar till skrivbordet | Enkelhet |
| 197 | Öppna utmappen automatiskt efter sortering (inställning, av som standard) | Enkelhet |
| 198 | Pil Tangenter + Enter i kölistan (välj fil, Enter = granska) | Enkelhet |
| 199 | "Varför?" i granskningsrutan: klartext ("ordet X i brevhuvudet, org.nr i sidfoten") | Enkelhet |
| 200 | Hälsokort på Sortera-fliken: grönt/rött för OCR, bevakning, mappar, lär-läge | Enkelhet |

### REQ-N15 (B) — Donationsvy + Swish-QR + SV/EN (LEVERERAD 2026-10-15)
(ANVÄNDARORDER: "donationssida som dom andra apparna, anpassad för denna
app, visas i app och html bredvid, swish qr ska jämföras med original,
sve/eng i appen".)
**AC-15:**
- AC-15.1 Donationsvy i appen (Hjälp → "Stöd projektet 💖"): nivåer
  39/99/299 kr, PayPal/Ko-fi/valfritt, SV/EN-växel som översätter vyn
  direkt.
- AC-15.2 HTML-sida bredvid appen: "Stöd ArkivPiloten.html" med samma
  design, SV/EN-växel (JS), Swish-sektion som visar swish_qr.png när
  den finns.
- AC-15.3 Swish-QR ritas BEROENDEFRITT i appen (egen QR-kodare: byte-läge,
  EC M, v1-6, mask 0) när användaren fyller i sitt nummer
  (`settings["swish_number"]`). Verifierad mot oberoende avkodare
  (OpenCV): payloaden avkodas tecken för tecken identiskt - det är
  jämförelsen med originalet. Payload + kopieringsknappar visas i vyn
  så att originalet kan skannas och jämföras.
- AC-15.5 Swish-numret 0721817177 inbakat som standard; swish_qr.png
  ligger bredvid HTML-sidan och visas där ("visa endast QR" -
  Öppna Swish-knappen och fejk-citat/sektionen "quotes" borttagna
  på beställning). QR-payloaden verifierad mot oberoende avkodare.
- AC-15.6 Donationsvyn i appen visar liksom HTML-sidan ENDAST
  QR-koden i Swish-sektionen (nummer/text/payload/kopieringsknappar
  borttagna 2026-10-15: "samma i appen nu?"). Numret ändras vid
  behov via settings["swish_number"].
- AC-15.4 Helappens i18n (SV/EN i hela gränssnittet) läggs som förslag
  #201 i kön - donationsvyn är först ut.

| 201 | Helappens i18n: SV/EN-växel i hela gränssnittet (strängtabell + växling live) | Enkelhet | VÄNTAR |

### REQ-N16 (B) — Årsmappar från filens datum + läslyft (LEVERERAD 2026-10-15)
(ANVÄNDARORDER: "lägg in i årsmappar i vald mapp, tex Pilkington/2022 efter
senast ändrat/skapat datum, sker automatiskt" + "bättre avläsning av
skannade pdf:er, mer matchningsord".)
**AC-16:**
- AC-16.1 `year_subfolder` (standard PÅ): alla sorterade filer läggs i
  `<vald mapp>/<år>`, inklusive `_Osorterat`; dokumentdatum styr året när
  det finns, annars används filens datum. En anpassad datummall behålls
  innanför årsmappen (och ett år som redan ingår dupliceras inte).
  Kryssruta i Datum-kortet; verifierat med egen datum- och unmatched-test.
- AC-16.2 Bättre avläsning: `ocr_max_pages` 3→6 (engångsmigrering för
  gamla inställningar) + extra OCR-pass (psm 4) i läget "high".
- AC-16.3 Fler matchningsord: `keywords_per_file` 10→15 (gransknings-
  rutan visar fler kandidater att bocka i).
- AC-16.4 Donationsidan: belöpssektionen ("Välj hur du vill hjälpa")
  borttagen ur HTML-sidan på beställning; hjältenivåer nås via hero-knappar
  och slutkort.

### REQ-N17 (B) — Robust, förklarbar självinlärning (IMPLEMENTERAS 2026-10-30)
(ANVÄNDARVAL: förslag 1, 2, 5, 6, 8, 9 och 10. Modellen är lokal,
regelstödd och får inte försvaga sorteringens säkerhetsgränser.)
**AC-17:**
- AC-17.1 Lärsignaler byggs per zon: generell text samt prefixade
  avsändar-/brevhuvud-, sidfots-, mottagar- och filnamnsord. Korrigering
  lagrar fel kategori och endast träffade ord i deras zon (plus den
  generella ordsignalen), inte samtliga dokumentord som felbevis.
- AC-17.2 Kategoriprofilen kalibreras med valda respektive korrigerade
  beslut. Enskilda signaler klingar av med två års halveringstid; den
  senaste träffen per signal sparas för drifthantering. Modellen är
  fortfarande bara en svag rangordningssignal.
- AC-17.3 Granskningsdialogen förklarar förslaget med matchade stödord,
  deras dokumentzoner och eventuell lärd/historisk förstärkning.
- AC-17.4 Walk-forward-testet poängsätter varje historikpost innan den
  tränas in (ingen framtida läcka), visar träffsäkerhet totalt och per
  kategori. Historiken kan återuppspelas; en enskild kategoriprofil kan
  inspekteras, nollställas eller återställas från positiva och negativa
  historiksignaler.
- AC-17.5 Modellen sparas lokalt i konfigkatalogen med befintlig atomisk
  JSON-skrivning, säkerhetskopia och korruptionsåterställning. Synkroniserad
  åtkomst skyddar samtidiga sorteringstrådar. Befintlig UI-konfigurerbar
  autostart på Windows, macOS och Linux lämnas intakt; uppdateringar tas
  fortfarande enbart från GitHub Releases.
- AC-17.6 `year_subfolder` standard PÅ appliceras även när datumsmall
  används och i `_Osorterat`: årsmappen ligger direkt under vald mapp,
  eventuell datummallsökväg följer innanför.

### REQ-N18 (B) — Ny gemensam ArkivPiloten-ikon och autostart utan pyw-filassociation
(ANVÄNDARORDER 2026-10-30: ny passande ikon överallt; om autostart väljs
ska den inte använda en `.pyw`-fil som kan visa Pythons ikon.)
**AC-18:**
- AC-18.1 `ArkivPiloten.png` är 512×512 RGBA med transparenta hörn och är
  den gemensamma mastern för fönster, dialoger, aktivitetsfält, tray,
  genvägar, macOS-app och dokumentationsbilder. `ArkivPiloten.ico` byggs
  från samma master med lager från 16 till 256 px.
- AC-18.2 Windows autostart startar `pythonw.exe pdfsorter.py --tray`
  direkt, aldrig `pdfsorter.pyw` via filassociation. AppUserModelID och
  den gemensamma `.ico`-filen används för att undvika Python-standardikon;
  `pythonw.exe` väljs för att undvika konsolfönster.
- AC-18.3 Autostartens plattformsstöd och UI-val för Windows/macOS/Linux
  bevaras. Test täcker att Windows autostart inte pekar på `.pyw`.

### REQ-N19 (B) — Autouppdatering jämför releasebyggen även vid samma versionsnummer
(ANVÄNDARORDER 2026-10-30: jämför releasefiler och commit, och erbjud
uppdatering när något skiljer även om versionsnumret är oförändrat.)
**AC-19:**
- AC-19.1 Releasepaketet innehåller `BUILD-MANIFEST.json` med versions-
  nummer, Git-commit och SHA-256 per distribuerad fil. Release-noterna
  bär samma manifest i en maskinläsbar, dold markör.
- AC-19.2 Vid samma versionsnummer jämför appen installerade filer och
  lokal commit mot manifestet. Olika filhash eller commit ger
  `available=True`; samma version, commit och filer ger ingen onödig
  ominstallation.
- AC-19.3 Äldre releaser utan manifest jämförs från ZIP-filen efter
  SHA-256-verifiering; resultatet cachelagras mot releasehash och lokal
  filfingeravtryck. Endast publicerade GitHub Releases används.
- AC-19.4 Samma versionsnummer får installeras endast när jämförelsen
  bekräftat ett nytt bygge. Paketets release-manifest måste stämma med
  releaseinformationen; appfiler säkerhetskopieras och rollback gäller
  som vid versionsbyte. Versionen bumpas inte automatiskt.

### REQ-W1 (M) — Workspace-hygien var 10:e chatt
(ANVÄNDARORDER 2026-10-06: "rensa ws och endast aktiva filer + spec
kvar - regel i spec efter 10 chattar".) Efter var 10:e chatt rensas
workspacen så att ENDAST aktiva filer + denna master-spec återstår:
kod (.py/.pyw), bat, ikonfiler, desktop.ini, requirements.txt och
PDFSORTER_SPEC.md (med denna bilaga). Öppna checklistor bevaras genom
att de flyttas in i Bilaga A innan källfilerna raderas.


# BILAGA A — ÖPPEN CHECKLISTA (flyttad hit vid ws-rensningen 2026-10-06)
Ur förslags-/forskningsloggarna; väljs med nummer via "lista"/
"kör N". Status VÄNTAR = ej påbörjad. Levererade/KOMMANDE-krav finns
i kravsektionerna ovan (N1-N14 m.fl.).

| # | Titel | Klass |
|---|-------|-------|
| 1 | Settings-schema + auto-repair | Robusthet |
| 2 | Backup före varje JSON-skrivning + månadsarkiv | Ny funktion |
| 4 | Mörkt läge & högkontrast | Ny funktion | **GODKÄND → REQ-H3** (designorder 2026-08-26) | | 5 | Förslagsfunktionen i appen (Förslag-vy + utlösare "förslag") | Ny funktion |
| 6 | Full testsvit tests/test_full_system.py | Kvalitet |
| 8 | Diagnostikkort i GUI + utökat --status | Ny funktion | **GODKÄND → REQ-N3** | | 9 | CSV-export av historiken | Ny funktion |
| 10 | Inbyggd PDF-förhandsvisning i granskningsdialogen | Ny funktion | **KOMMANDE (REQ-N7)** — kod finns men är AVSTÄNGD (`preview_in_dialog=False`) tills beställaren säger till | | 11 | Drag-och-släpp batch-import | Ny funktion |
| 12 | Duplikatspärr + SHA-256, alltid fråga: ersätt eller "(2)" | Ny funktion | **GODKÄND → REQ-N4** | | 13 | Auto-omladdning av rules.json vid extern ändring | Ny funktion |
| 14 | NAS-/nätverksmappar med återanslutning + status | Förbättring |
| 15 | Tangentbordsnav, Ctrl+Z (ångra), Ctrl+F (sök) | Förbättring |
| 16 | Snabbfilter i statusraden + "Senaste fil"-ruta | Förbättring |
| 17 | Kvartalsrapport + avvikelseanalys | Ny funktion |
| 18 | Anpassningsbar rapportheader | Förbättring |
| 19 | Automatiskt OCR-omförsök med Bättre OCR | Förbättring |
| 20 | Kompakt minnesprofil vid storskanning | Prestanda |
| 22 | Buggfix: stäng originalbilder efter OCR-förbehandling | Buggfix | **LEVERERAD 2026-09-17** (avläsningsrundan) | | 23 | Revisionslogg (audit) för regeländringar | Ny funktion |
| 24 | Valfritt PIN-skydd för borttagning | Ny funktion |
| 25 | PyInstaller-paketering + autostart-test per OS | Ny funktion |
| 26 | Kompakt läge (täthetsväxel: radhöjd 30→24, smalare padding) | Design | **KOMMANDE → REQ-N8** | | 27 | Sorteringspilar (▲/▼) i tabellrubriker | Design |
| 28 | Kortkommandon: Ctrl+1–7 byter flik, Ctrl+F fokuserar sökfältet | Design |
| 31 | Färgblindssäker status: symboler ✓/⚠/ i egen kolumn, aldrig enbart färg | Design | **KOMMANDE → REQ-N11** | | 32 | Konfigurerbar minnesbudget (settings max_cache_mb, standard 24) | Minne |
| 33 | TTL-avlastning: TextCache-poster inaktiva >10 min släpps | Minne |
| 34 | Gzip-komprimerad diskcache (mindre disk, färre läsningar) | Minne |
| 35 | Virtuell historik: bläddra förbi 500 rader med ladda-vid-scroll | Minne |
| 36 | En sida i minnet i förhandsvisningen (när N7 aktiveras): bara aktuell sida | Minne |
| 37 | Append-only historikjournal + periodisk kompaktering (ingen hel-omskrivning + fsync per flytt) | Snabbhet | **LEVERERAD 2026-08-26** (data-härdning, REQ-I2 AC-2.6) | | 38 | Katalog-mtime-vakt: oförändrade mappar hoppas över i bevakningssvep | Snabbhet |
| 40 | Zoncache: TextZones återanvänds mellan decide/omskanning av samma fil | Snabbhet | **LEVERERAD** (_ZONES_CACHE, tak 200) | | 41 | Lat flikbygge: flikar byggs vid första besöket → snabbare start | Snabbhet |
| 42 | Debouncad rules.save: max 1 skrivning/sekund under massortering | Snabbhet | **LEVERERAD** (SortEngine._rules_save) | | 43 | Bakgrunds-"readahead": värm diskcachen för inmappar i bakgrunden | Snabbhet |
| 44 | Aliasfält på stödord (t.ex. Pilkington = NSG) | Matchning |
| 45 | Negativa stödord per kategori (uteslut kända falska träffar) | Matchning |
| 46 | Fuzzy-företagsnamn i Bättre OCR-läge (Levenshtein ≤1 för ord ≥6 tecken) | Matchning |
| 47 | Ångra-feedback: vid Ångra föreslås sänkt vikt/borttagning av matchade ord | Matchning |
| 48 | Auto-förslag: ord bekräftat manuellt 3 ggr → ett-klicks förslag som nytt stödord | Matchning |
| 49 | Krockguide: ett-klicks omflytt/renodling av stödord som delas av flera kategorier | Matchning |
| 50 | "Varför den här poängen?"-detaljdialog: zonuppslag per ord med vikter | Matchning |
| 51 | Tangentbordsfirst i granskningsdialogen: pilar/space/1–9 styr kandidatlistan | Design | **KOMMANDE → REQ-N12** (inväntar beställarens order) | | 52 | MRU-kategorier: senast använda överst i rullgardinen | Design |
| 53 | Kategoriprickar: egen färgpunkt per kategori i listor och dialog | Design |
| 54 | Systemnotis med Ångra-knapp när fil sorterats | Design |
| 55 | ASCII-trend (sparkline) per månad i Markdown-rapporten | Design |
| 56 | Konfidens i procent i dialogen i stället för rå poäng | Design |
| 57 | Strömmande historikparsning i rapporten (hela JSON aldrig i RAM) | Minne |
| 58 | zlib-komprimerade TextCache-poster (mer text i samma minnestak) | Minne |
| 59 | Loggtak i GUI: logboxen trimmas till 2 000 rader | Minne |
| 60 | Hash-cache: samma källfils SHA-256 beräknas en gång per körning | Minne/Snabbhet |
| 61 | Mönsterförvärmning: alla stödordsmönster kompileras vid regeländring | Snabbhet | **LEVERERAD** (_warm_patterns) | | 62 | Inkrementell historikuppdatering i GUI (bara nya händelser) | Snabbhet |
| 63 | Samlade logginsatser: logboxen uppdateras max var 100 ms | Snabbhet |
| 64 | En trådpool återanvänds mellan batcher (ingen skap/förstör per körning) | Snabbhet |
| 65 | Små filer först i batchen (snabbare synlig feedback) | Snabbhet |
| 66 | Glob-regel som regeltyp: filnamnsmönster som stödord ("*pilkington*") | Matchning |
| 67 | Autoviktning: föreslå viktjustering utifrån träffstatistik | Matchning |
| 68 | "Fråga alltid" per kategori (auto-flytt avstängd för den kategorin) | Matchning |
| 69 | Dotterbolagsförslag: "X AB" ≈ "X Sverige AB" föreslås som alias | Matchning |
| 70 | Rotationsdetektion: vridna skannade sidor rätas före OCR | Avläsning |
| 71 | Tabellmedveten extraktion (pymupdf "dict"-läge för kolumner) | Avläsning |
| 72 | Självtestknapp i Hjälp-fliken (kör modulernas --check i appen) | Felsökning |
| 73 | Diagnostikpaket: zip med loggar+inställningar för supportsändning | Felsökning |
| 74 | Pump-vakthund: varnar i loggen om UI-pumpen stallar >10 s | Felsökning |
| 75 | Regelsnapshot: tidsstämplad backup före import/ersätt-allt | Robusthet |
| 76 | mypy-strict typ-pass över alla fem modulerna | Kod |
| 77 | Property-baserade tester (hypothesis) för matchningsmotorn | Kod |
| 78 | Append-only-journal för rules.json (samma mönster som historiken) | Kod |
| 79 | Karantän: filer som felat 3 gångr listas & flaggas i stället för att retried | Kod |
| 80 | Självtestsvit i --diag: kör modulernas check och rapportera per modul | Kod |
| 81 | Kommandopalett Ctrl+K (hoppa till flik/åtgärd) | Design |
| 82 | Kanban-vy i Granska: dra filen till en kategori | Design |
| 83 | Minifeed med senaste händelser på Sortera-fliken | Design |
| 84 | Tillgänglighetsnamn (skärmläsare) på alla kontroller | Design |
| 85 | Veckorapport autoexporteras till mapp (utan nätverk) | Design |
| 86 | Färgteckenförklaring på Matchningar-fliken | Design |
| 87 | Poängnormalisering mot kategoristorlek (stora kategorier straffas) | Matchning |
| 88 | Kombinationsregel: två stödord måste träffa i samma stycke | Matchning |
| 89 | Tidsdecay: nyligen tillagda ord väger tyngre under inlärningsfasen | Matchning |
| 90 | Bolagsforms-normalisering vid jämförelse ("X AB" ≈ "X Sverige AB") | Matchning |
| 91 | Org.nr utan bindestreck (5560339086) med Luhn som stark typ | Matchning |
| 92 | Styckeszon: flertalet träffar i samma stycke väger upp | Matchning |
| 93 | Språk-autodetektion per sida (swe/eng/deu via teckenfrekvens) | OCR |
| 94 | Skugg-/marginalbeskärning före OCR | OCR |
| 95 | Adaptiv DPI efter uppmätt bildskärpa | OCR |
| 96 | Kasta OCR-ord med konfidens < 50 ur texten | OCR |
| 97 | Zon-OCR: brevhuvud i högre DPI än brödtext | OCR |
| 98 | Bildhash-cache: identisk bild i flera filer OCR:as en gång | OCR |
| 99 | PUA/garbled-text-detektion → behandla sidan som skannad | OCR |
| 100 | Super-resolution 2× för små textregioner före OCR | OCR |
| 101 | Disk-only-cacheläge: TextCache i RAM helt avstängningsbar (minimal RAM) | Minne |
| 102 | Generator-baserad list_pdfs + chunkad batch (100 filer i taget) | Minne/Snabbhet |
| 103 | Tidigt avbrott i förslagsbygget efter N starka kandidater | Minne |
| 104 | weakref-zoncache som släpper vid minnestryck (gc-kallback) | Minne |
| 105 | Sqlite-backad historik (valfri): index, låg RAM, snabb bläddring | Minne |
| 106 | Inverterat token-index över kategorier (prefilter utan per-kategori-loop) | Snabbhet |
| 107 | orjson vid tillgänglighet (5× JSON), json som fallback | Snabbhet | **LEVERERAD 2026-08-26** (data rond 3) | | 108 | Early-exit i decide() när ledarens marginal > 2× tröskeln | Snabbhet |
| 109 | Förberäknade stödordstokens vid regelladdning (inte per fil) | Snabbhet |
| 110 | Parallell listning av flera inmappar | Snabbhet |
| 111 | ReadDirectoryChangesW på Windows, polling som fallback | Snabbhet |
| 112 | Kontextfönster-boost: två träffar inom 50 tecken väger upp | Matchning |
| 113 | Auto-stoppord per kategori: ord i >50 % av kategoriens filer | Matchning |
| 114 | Konfidensviktad matchning: OCR-ord med conf <60 räknas halvt | Matchning |
| 115 | Filnamnets projektkoder auto-extraheras som "kod"-kandidater | Matchning |
| 116 | Negativ inlärning: byter användare kategori decays fel kategoris ord | Matchning |
| 117 | Layoutmedveten avsändare: största typsnittet överst = avsändare | Matchning |
| 118 | Exklusiva-ords-förslag när två kategorier står oavgjort | Matchning |
| 119 | Ctrl+T växlar tema direkt | Design |
| 120 | In-app-toasts (icke-modala) i stället för messagebox för små saker | Design |
| 121 | Tidslinjevy i Historik, grupperad per dag | Design |
| 122 | Kategorikort med sparkline på Matchningar | Design |
| 123 | Ångra över sessioner (ångra senaste flytten efter omstart) | Design |
| 124 | Sökmarkering i Hjälp-fliken | Design |
| 125 | Statuspille med live minnesanvändning (cache-MB) | Design/Minne |
| L1 | Diagnostikpaket till urklipp (system+inställningar+loggsvans i ETT block) — förfinar #73 | Felsökning | **LEVERERAD 2026-09-17** (build_diagnostics + knapp + --diagnostik) | | L2 | Konfig-härdning: klamp/enum-vakter + dubblettnycklar + rad/kolumn vid JSON-fel — utökar #1 | Robusthet |
| L3 | Autostart v2.0: stale_console-klassificering + verify-after-write + registry-backup + konfliktdetektering | Robusthet | **LEVERERAD 2026-09-17** (classify_autostart m.m.) | | L4 | "System"-tema som följer OS (Windows-registry/macOS defaults/GTK_THEME) + AAA/AA-klassificering | Design |
| L5 | LogContext: ▶ START / ✔ KLART (ms) / ✗ FEL runt OCR, skanning, sortering | Felsökning/Snabbhet | **LEVERERAD 2026-09-17** (analys + batch) | | L6 | Permanent testsvit i tests/ med regression-runner varje runda — utökar #6 | Kvalitet |
| 126 | Delningsförslag: flera avsändare i samma skannade PDF upptäcks → fråga om dela upp och sortera varje del | Matchning |
| 127 | Effektförhandsvisning: innan regeländring sparas, visa hur många senaste filers beslut som skulle ändras (ur journalen) | Matchning |
| 128 | Fästa exempelfiler per kategori (1–3 st): kör mini-test mot dem vid varje regeländring | Matchning/Kvalitet |
| 129 | Döda-ord-rapport: stödord som aldrig träffat + kategorier utan filer → städförslag | Matchning |
| 130 | Lästidsstatistik per motor (pymupdf/pypdf/pdfminer/OCR p50/p95) i --diag → visar långsammaste backend | Avläsning |
| 131 | Lösenordsskyddade PDF:er: lista låsta filer, fråga efter lösenord en gång per session | Avläsning |
| 132 | Bevakningsprofil per mapp: intervall, rekursiv, exkludering och stabil-tid per inmapp i stället för globalt | Ny funktion |
| 133 | Bevakningsvakthund: dör bevakningstråden startas den om tyst + loggrad + statusvarning | Robusthet |
| 134 | Disk-fullt-vakt: ENOSPC vid flytt → tydligt felläge + notis, ingen fil förloras eller glöms | Robusthet |
| 135 | Flyttverifiering: hashkontroll av målfilen efter flytt/kopiering (billig: hashen finns redan från dubblettkontrollen) | Robusthet |
| 136 | Loggläsare i appen: bläddra/filtrera gamla sessionsloggar per nivå och kategori, kopiera urval | Felsökning |
| 137 | Gzip-komprimera sessionsloggar äldre än 3 månader (raderas aldrig — komprimeras bara) | Minne/Ordning |
| 138 | Träffsäkerhets-KPI: andel auto vs användaröverskrivningar per kategori, pill på Matchningar | Ny funktion |
| 139 | Filnamnsnormalisering vid flytt (valfritt): datumprefix, understreck, gemener | Ny funktion |
| 140 | Global sökning (Ctrl+F): ett fält som söker kö + historik + regler och hoppar till rätt flik | Design |
| 141 | Bevakningshälsa per mapp: kort med antal sedda filer, senaste fil, fel per bevakad mapp | Design |
| 142 | Systemfältsmeny: pausa/återuppta bevakning + köantal i menyn | Design |
| 143 | Flyttpaket: zip med regler+inställningar+loggar för att flytta till ny dator | Ny funktion |
| 144 | Auto-omkörning av _Osorterat: när nya stödord lärs in, matcha om tyst och meddela träffar | Ny funktion |
| 145 | Konfigurerbar motorordning: användaren väljer prioritet bland läsmotorerna | Avläsning/Snabbhet |
| 146 | Kösortering: äldst först / namn / storlek i granskningskön | Design |
| 147 | Ljudsignaler (avstagningsbara): ljud när sortering klar / fil väntar på granskning | Design |
| 148 | Fönsterminne per skärm: position/storlek sparas per monitoruppsättning | Design |
| 149 | Mörk/ljus tray-ikonvariant så ikonen syns i både ljust och mörkt aktivitetsfält | Design |
| 150 | Kategoriexport: exportera/importera enstaka kategorier (urklipp eller fil) för delning med kollega | Ny funktion |
| F1 | Lärande klassificerare från historiken (ordvägare byggd på fattade beslut, bryter dödlägen) | Matchning | **GODKÄND 2026-09-24 → REQ-N14 (KOMMANDE)** | | F2 | Sökbart arkiv: fulltextsök bland alla sorterade filer (lätt JSON-index ur textcachen) | Ny funktion |
| F3 | Undermappsnamn som matchningsledtråd (fil i Inmapp/Pilkington/ får svagt bevis) | Matchning |
| F4 | Streckkodsskiljeark: detektera skiljesidor och dela buntar före matchning (komplement till 126) | Avläsning |
| F5 | OCR-städpass: skanningsbrus bort före OCR (paket med 94/96) | OCR |
| F6 | Rotationsrättning per sida med konfidenströskel | OCR | Hänvisas till förslag 70 (AC-6.3) | | F7 | Batchgranskning: markera flera filer i kön, applicera samma kategori eller ignorera på alla (Paperless bulk-ops) | Design/Snabbhet |
| 151 | "Senaste körningen"-kort på Sortera-fliken: sorterade/frågor/fel/tid, kvar mellan sessioner | Design |
| 152 | 14-dagars sparkline (sorterade filer/dag) på Sortera-fliken | Design |
| 153 | Högerklick i granskningskön: öppna mapp / förhandsvisa / ignorera / ta ur kön | Design |
| 154 | Inställbar teckenstorlek (tillgänglighet) utöver HiDPI-autoskalning | Design |
| 155 | Søkfält på Matchningar-fliken: filtrerar kategorier + stödord direkt | Design |
| 156 | Klick på ett stödord → lista tidigare filer det matchade (ur historiken) | Design |
| 157 | Kön visar föreslagen kategori bredvid filnamnet (regel eller lärd) | Design |
| 158 | ETA vid långa batcher: filer/min → beräknad återstående tid | Design/Snabbhet |
| 159 | Släpp extraction-texten efter beslut (behåll endast zondata) - lägre toppminne | Minne |
| 160 | Åldersbaserad rensning av diskcachen (inställbart tak i dagar) | Minne |
| 161 | Dokumenttypsdetektering (faktura/avtal/brev/kvitto) som extra matchningshint | Matchning |
| 162 | Layoutfingeravtryck: lär var i dokumentet (topp/botten) kategoriens ord brukar träffa, bonus vid överensstämmelse | Matchning |
| 163 | Omvänd inlärning: auto-flyttar med stor marginal föreslår sina ord som nya stödord (ett klick) | Matchning |
| 164 | SVE/ENG-synonymtabell för stödord (faktura=invoice, kvitto=receipt) | Matchning |
| 165 | Hoppa över dublettsidor i samma PDF vid OCR (bildhash) - snabbare skannings-svep | Snabbhet/Avläsning |
| 166 | pypdf strict=False-fallback för PDF:er med trasig xref-tabell | Robusthet |
| 167 | Bevaka även bildfiler (JPG/PNG) i inmappen - direkt-OCR som egen källa | Avläsning |
| 168 | Stöd för PDF-portföljer/bundna dokument (extrahera inbäddade PDF:er) | Avläsning |
| 169 | Profiler: --profil NAMN ger flera parallella uppsättningar (regler/logg) från samma appmapp | System |
| 170 | Krasch-vakthund: genväg/bat som startar om appen inom 60 s vid oväntat avslut | System |
| 171 | Nattligt schemalagt självtest (Windows Aktivitetsschemaläggaren kör --check) | System |
| 172 | "Spara logg som fil…"-knapp (export vald sessionslogg till valfri mapp) | System |
| 173 | Daglig ögonblicksbild-backup av rules+settings+learned_model (behåll 7) | Robusthet |
| 174 | Arkivera historik äldre än 12 månader till history-ÅÅÅÅ.json (huvudfilen snabb) | Data |
| 175 | Rensningsguide: slå ihop kategorier med identisk målmapp, flytta deras ord | Data |
