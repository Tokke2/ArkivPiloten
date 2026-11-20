#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verifiera att release-arbetsflödet lyckades efter en push.

Stående rutin efter varje kodpush: release-arbetsflödet
(.github/workflows/release.yml) ska ha byggt om paketet och skrivit över
filerna i den befintliga releasen. Det här skriptet kontrollerar det:

1. Hittar release.yml-körningen för den pushade committen på grenen.
2. Väntar tills körningen är klar och kräver conclusion == "success".
3. Kontrollerar att releasens inbäddade byggmanifest pekar på samma commit,
   dvs. att releasepaketet faktiskt uppdaterades med den pushade koden.

    python tools/verify_release.py
    python tools/verify_release.py --sha <commit> --branch <gren>

Kräver GitHub CLI (gh) med inloggning. Exitkoder: 0 = OK,
1 = release-jobbet misslyckades eller manifestet matchar inte,
2 = användnings-/miljöfel eller timeout.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import shutil
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]

WORKFLOW = "release.yml"
MANIFEST_BEGIN = "<!-- ARKIVPILOTEN_BUILD_MANIFEST_BEGIN"
MANIFEST_END = "ARKIVPILOTEN_BUILD_MANIFEST_END -->"
EXIT_FAILED = 1
EXIT_ERROR = 2


def release_tag(version: str) -> str:
    """Returnera release-taggen för en appversion (t.ex. v1.4.14)."""
    return f"v{version}"


def read_app_version(root: pathlib.Path = ROOT) -> str:
    """Läs APP_VERSION ur pdfsorter.py utan att importera appen."""
    text = (root / "pdfsorter.py").read_text(encoding="utf-8")
    match = re.search(r'^APP_VERSION\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        raise ValueError("APP_VERSION hittades inte i pdfsorter.py")
    return match.group(1)


def extract_build_manifest(body: str) -> dict:
    """Plocka ut byggmanifestet ur en release-anteckning.

    Returnerar {} när markörerna saknas eller JSON:en är ogiltig.
    """
    try:
        inner = (body or "").split(MANIFEST_BEGIN, 1)[1]
        inner = inner.split(MANIFEST_END, 1)[0]
        manifest = json.loads(inner)
    except (IndexError, ValueError):
        return {}
    return manifest if isinstance(manifest, dict) else {}


def manifest_commit(body: str) -> str:
    """Returnera commiten som releasepaketet byggdes från ("" om okänd)."""
    commit = extract_build_manifest(body).get("commit", "")
    return str(commit or "")


def select_run_for_sha(runs: list, sha: str) -> dict | None:
    """Välj nyaste körningen för en commit (full eller förkortad SHA)."""
    want = (sha or "").strip().lower()
    if not want:
        return None
    for run in runs or []:
        head = str((run or {}).get("headSha", "")).lower()
        if head and (head == want or head.startswith(want)
                     or want.startswith(head)):
            return run
    return None


def _git(*args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} misslyckades: "
                           f"{proc.stderr.strip()}")
    return proc.stdout.strip()


def _gh_json(args: list, repo: str) -> object:
    cmd = ["gh", *args, "--repo", repo]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                          check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)} misslyckades: "
                           f"{proc.stderr.strip()}")
    try:
        return json.loads(proc.stdout or "null")
    except ValueError as exc:
        raise RuntimeError(f"gh gav ogiltig JSON: {exc}") from exc


def detect_repo(explicit: str | None) -> str:
    """Bestäm owner/repo från flagga, gh eller git-remoten."""
    if explicit:
        return explicit
    proc = subprocess.run(
        ["gh", "repo", "view", "--json", "nameWithOwner", "-q",
         ".nameWithOwner"], cwd=ROOT, capture_output=True, text=True,
        check=False)
    if proc.returncode == 0 and proc.stdout.strip():
        return proc.stdout.strip()
    url = _git("remote", "get-url", "origin")
    match = re.search(r"[:/]([^/:]+/[^/]+?)(?:\.git)?$", url)
    if match:
        return match.group(1)
    raise RuntimeError("Kunde inte avgöra repo; ange --repo owner/namn.")


def wait_for_run(run_id: int, repo: str, deadline: float,
                 poll: float) -> dict:
    """Vänta tills en workflow-körning är klar; returnera dess status."""
    last = ""
    while time.monotonic() < deadline:
        run = _gh_json(["run", "view", str(run_id), "--json",
                        "status,conclusion,url"], repo)
        if not isinstance(run, dict):
            raise RuntimeError("gh run view gav oväntat svar.")
        status = str(run.get("status", ""))
        if status != last:
            print(f"  status: {status or '?'}", flush=True)
            last = status
        if status == "completed":
            return run
        time.sleep(poll)
    raise TimeoutError(f"Körning {run_id} blev inte klar i tid.")


def verify(sha: str, branch: str, repo: str, timeout: float,
           poll: float) -> int:
    """Kör hela verifieringen; returnerar exitkod."""
    deadline = time.monotonic() + timeout
    print(f"Söker release-körning för {sha[:12]} på {branch} ...", flush=True)
    run = None
    while time.monotonic() < deadline:
        runs = _gh_json(["run", "list", "--workflow", WORKFLOW, "--branch",
                         branch, "--limit", "20", "--json",
                         "databaseId,headSha,status,conclusion,createdAt"],
                        repo)
        run = select_run_for_sha(runs if isinstance(runs, list) else [], sha)
        if run is not None:
            break
        time.sleep(poll)
    if run is None:
        print(f"FEL: ingen {WORKFLOW}-körning hittades för {sha[:12]}.",
              flush=True)
        return EXIT_ERROR
    run_id = int(run["databaseId"])
    print(f"Hittade körning {run_id}; väntar på slutförande ...", flush=True)
    try:
        finished = wait_for_run(run_id, repo, deadline, poll)
    except TimeoutError as exc:
        print(f"FEL: {exc}", flush=True)
        return EXIT_ERROR
    conclusion = str(finished.get("conclusion", ""))
    url = str(finished.get("url", ""))
    if conclusion != "success":
        print(f"FEL: release-jobbet avslutades med '{conclusion}'. {url}",
              flush=True)
        return EXIT_FAILED
    print("Release-jobbet lyckades; kontrollerar byggmanifest ...", flush=True)
    try:
        tag = release_tag(read_app_version())
    except (OSError, ValueError) as exc:
        print(f"FEL: {exc}", flush=True)
        return EXIT_ERROR
    body = ""
    manifest_deadline = time.monotonic() + 120
    while time.monotonic() < manifest_deadline:
        release = _gh_json(["release", "view", tag, "--json", "body"], repo)
        body = str((release if isinstance(release, dict) else {}).get(
            "body", ""))
        found = manifest_commit(body)
        if found and (found == sha or found.startswith(sha[:7])
                      or sha.startswith(found)):
            print(f"OK: {tag} är byggd från {found[:12]}. {url}", flush=True)
            return 0
        time.sleep(10)
    print(f"FEL: {tag} pekar inte på {sha[:12]} "
          f"(manifest: {manifest_commit(body)[:12] or '?'}). {url}",
          flush=True)
    return EXIT_FAILED


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verifiera att release-jobbet lyckades efter en push.")
    parser.add_argument("--sha", default="",
                        help="commit att verifiera (standard: HEAD)")
    parser.add_argument("--branch", default="",
                        help="gren att söka körningen på (standard: aktiv)")
    parser.add_argument("--repo", default="",
                        help="owner/namn (standard: gissa från gh/git)")
    parser.add_argument("--timeout", type=float, default=900,
                        help="max sekunder att vänta (standard: 900)")
    parser.add_argument("--poll", type=float, default=15,
                        help="sekunder mellan kontroller (standard: 15)")
    args = parser.parse_args(argv)

    if shutil.which("gh") is None:
        print("FEL: GitHub CLI (gh) saknas eller är inte i PATH.",
              flush=True)
        return EXIT_ERROR
    try:
        sha = args.sha.strip() or _git("rev-parse", "HEAD")
        branch = args.branch.strip() or _git("rev-parse", "--abbrev-ref",
                                             "HEAD")
        repo = detect_repo(args.repo.strip() or None)
    except RuntimeError as exc:
        print(f"FEL: {exc}", flush=True)
        return EXIT_ERROR
    try:
        return verify(sha, branch, repo, args.timeout, max(5, args.poll))
    except RuntimeError as exc:
        print(f"FEL: {exc}", flush=True)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
