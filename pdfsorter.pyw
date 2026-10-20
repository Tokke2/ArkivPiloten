# -*- coding: utf-8 -*-
# Startar ArkivPiloten utan konsolfönster - dubbelklicka mig.
#
# Robust startfil (v1.4.0):
#   * Flyttbar: hittar pdfsorter.py bredvid sig själv i stället för en
#     hårdkodad sökväg - hela mappen kan flyttas utan att startfilen dör.
#   * Rätt ikon i aktivitetsfältet: AppUserModelID sätts före första
#     fönstret, så Windows visar vår ikon i stället för Pythons fjäder.
#   * Tyst felhantering: pythonw har ingen konsol, så stdout/stderr styrs
#     om och startfel visas i en dialog + skrivs till logg.
#   * Snål med minne: inget annat än standardbiblioteket laddas här;
#     allt tungt händer först inne i huvudprogrammet.
#   * Argument skickas vidare: pdfsorter.pyw --tray fungerar.

import os
import sys
from pathlib import Path

#: Eget program-ID för Windows. Utan detta grupperar Windows fönstret
#: under pythonw.exe och visar Pythons ikon i aktivitetsfältet.
_APP_ID = "ArkivPiloten.App.1"


def _config_dir():
    # Portabel (2026-10-05): appmappen först (fungerar på USB/varsom),
    # PDFSORTER_HOME styr om satt. Är appmappen skrivskyddad (t.ex.
    # /Applications eller /opt) används användarens data-mapp, annars
    # kunde startaren inte ens skriva sin kraschlogg.
    env = os.environ.get("PDFSORTER_HOME")
    if env:
        return Path(env).expanduser()
    hem = Path(__file__).resolve().parent
    try:
        t = hem / ".pdfsorter_write_test"
        t.write_text("ok", encoding="utf-8")
        t.unlink()
        return hem
    except OSError:
        pass
    if sys.platform.startswith("win"):
        bas = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(bas) / "ArkivPiloten"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "ArkivPiloten"
    return Path.home() / ".config" / "pdfsorter"


def _fixa_stdio():
    # pythonw har ingen konsol: sys.stdout/sys.stderr är None, vilket får
    # print() och felrapporter att själva krascha. Styr om dem.
    try:
        if sys.stdout is None:
            sys.stdout = open(os.devnull, "w", encoding="utf-8")
        if sys.stderr is None:
            logg = _config_dir() / "logs" / "startare.log"
            logg.parent.mkdir(parents=True, exist_ok=True)
            sys.stderr = open(logg, "a", encoding="utf-8", buffering=1)
    except OSError:
        pass


def _fel_dialog(text):
    # Sista utvägen utan konsol: en dialog som stänger sig själv efter
    # två minuter så att inget kan hänga sig i oändlighet.
    try:
        import tkinter as tk
        from tkinter import messagebox
        rot = tk.Tk()
        rot.withdraw()
        try:
            rot.after(120_000, rot.destroy)
            messagebox.showerror("ArkivPiloten", text)
        finally:
            rot.destroy()
    except Exception:
        pass


def main():
    _fixa_stdio()

    huvud = Path(__file__).resolve().with_suffix(".py")
    if not huvud.is_file():
        _fel_dialog("Hittade inte pdfsorter.py bredvid startfilen.\n\n"
                    "Lägg pdfsorter.pyw i samma mapp som pdfsorter.py.")
        return 1

    # Stabila förhållanden för huvudprogrammet: rätt arbetskatalog,
    # rätt sys.argv[0] och möjlighet att importera grannmodulerna.
    try:
        os.chdir(huvud.parent)
    except OSError:
        pass
    sys.argv = [str(huvud)] + list(sys.argv[1:])
    if str(huvud.parent) not in sys.path:
        sys.path.insert(0, str(huvud.parent))

    if sys.platform.startswith("win"):
        # Måste ske före det första fönstret skapas för att ge vår ikon
        # i aktivitetsfältet. Kan aldrig få starten att misslyckas.
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(_APP_ID)
        except Exception:
            pass

    import runpy
    try:
        runpy.run_path(str(huvud), run_name="__main__")
        return 0
    except SystemExit as exc:
        kod = exc.code
        if kod is None:
            return 0
        return kod if isinstance(kod, int) else 1
    except BaseException:
        # Försök appens egen felrapport (logg + dialog med ikon). Finns
        # inte systemmodulen skrivs felet direkt till krasch.loggen.
        exc = sys.exc_info()[1]
        try:
            import pdfsorter_system
            pdfsorter_system.crash_report(exc)
        except Exception:
            import traceback
            text = traceback.format_exc()
            try:
                # Alla loggar bor i log-mappen (användarorder).
                logg = _config_dir() / "logs" / "krasch.log"
                logg.parent.mkdir(parents=True, exist_ok=True)
                with open(logg, "a", encoding="utf-8") as fh:
                    fh.write("\n===== startare =====\n" + text)
            except Exception:
                pass
            _fel_dialog(f"ArkivPiloten kunde inte starta.\n\n{text[:1500]}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
