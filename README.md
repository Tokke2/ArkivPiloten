# ArkivPiloten 📄➡️🗂️

**PDF Sorter 1.1.0** — sorterar dina PDF:er automatiskt i rätt mappar.
Känner igen avsändare (org.nr, VAT, bankgiro, domän, firmanamn), läser
skannade dokument med OCR och lär sig av dina beslut. Portabel: kör från
valfri mapp eller USB, all data sparas i appmappen (`logs/`, `json/`).

## Kom igång (Windows)
1. Dubbelklicka `ArkivPiloten - Installera senaste Python och starta.bat`
   — installerar senaste stabila Python vid behov, samt appens beroenden.
2. Klart. Appen startar utan konsolfönster; allt sparas i appmappen.

Manuellt: `pip install -r requirements.txt` och `pdfsorter.pyw`.

## Funktioner i korthet
- Bevakade mappar + automatisk sortering i `<kategori>/<år>`
- Zonviktad matchning (brevhuvud/sidfot/avsändare) + flersidig matchning
- Självlärande klassificerare (N14) — bryter dödlägen efter ~5 beslut/kategori
- OCR för skannade PDF:er (Tesseract), inklusive Swish-liknande QR-verktyg
- Sessionsloggning i `logs/` med diagnostikpaket ("Kopiera diagnostik")
- Enkelinstans, tray-ikon, autostart, mörkt/ljust tema, SV/EN i donationsvyn
- Donationsvy + `Stöd ArkivPiloten.html` med verifierad Swish-QR

## Struktur
```
ArkivPiloten/
├── ArkivPiloten - Installera senaste Python och starta.bat
├── pdfsorter.py            huvudprogram (GUI, motor, matchning)
├── pdfsorter.pyw           konsolfri start
├── pdfsorter_data.py       regler, historik, lås, atomisk skrivning
├── pdfsorter_read.py       textextraktion, OCR, QR-kodare
├── pdfsorter_system.py     ikon, autostart, tray, loggar, autostart
├── pdfsorter_theme.py      ljus/mörk/högkontrast, HiDPI
├── Stöd ArkivPiloten.html  donationssida (SV/EN, Swish-QR)
├── swish_qr.png            Swish-QR (0721817177), verifierad
├── ArkivPiloten.ico/.png   appikonen (används överallt)
├── desktop.ini             mappikon i Utforskaren
└── PDFSORTER_SPEC.md       kravspecifikation (source of truth)
```

## Testa
`python pdfsorter.py --status` · `python pdfsorter_data.py` ·
`python pdfsorter_read.py --check` · `python pdfsorter_system.py --check`

## Licens & upphov
© 2026 Rickard Längkvist. Donationer: se `Stöd ArkivPiloten.html`
(Swish 0721817177, PayPal, Ko-fi). Appen är och förblir gratis.
