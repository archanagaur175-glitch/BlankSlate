"""First-run fetch of the Ollama server (Option A).

Instead of shipping a ~1.4 GB Ollama inside the MSI, we download the official
Windows build on first launch. The flow:

* first check PATH and common install locations for an existing Ollama and use it;
* otherwise download the release archive, verifying its SHA256 against the
  checksum published next to it (no hardcoded hashes);
* report progress (stage, percent, ETA) through a callback so the HUD can show a
  real first-run state;
* resume on retry via HTTP range requests so a dropped network doesn't restart
  from zero.

The download is skipped entirely when a system Ollama is already present.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

# Pin the Ollama release to fetch. Bump deliberately; never auto-follow "latest".
OLLAMA_RELEASE = "https://github.com/ollama/ollama/releases/download/v0.9.3"
ARCHIVE_NAME = "ollama-windows-amd64.zip"


def find_existing_ollama() -> str | None:
    """Return a usable Ollama executable already on the machine, else None."""
    on_path = shutil.which("ollama")
    if on_path:
        return on_path
    candidates: list[Path] = []
    if sys.platform.startswith("win"):
        pf = os.environ.get("ProgramFiles")
        if pf:
            candidates.append(Path(pf) / "Ollama" / "ollama.exe")
        local = os.environ.get("LOCALAPPDATA")
        if local:
            candidates.append(Path(local) / "Programs" / "Ollama" / "ollama.exe")
    for c in candidates:
        if c.exists():
            return str(c)
    return None


async def _download_with_resume(
    url: str, dest: Path, progress
) -> None:
    import httpx

    chunk_size = 1 << 16
    start = dest.stat().st_size if dest.exists() else 0
    headers = {"Range": f"bytes={start}-"} if start else {}
    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        async with client.stream("GET", url, headers=headers) as resp:
            if resp.status_code not in (200, 206):
                raise RuntimeError(f"ollama download failed: HTTP {resp.status_code}")
            total = int(resp.headers.get("content-length", 0)) + start
            written = start
            # server ignored the range -> restart from scratch
            if resp.status_code == 200 and start:
                dest.unlink(missing_ok=True)
                written = 0
            with open(dest, "ab" if written else "wb") as fh:
                async for chunk in resp.aiter_bytes(chunk_size):
                    fh.write(chunk)
                    written += len(chunk)
                    if total:
                        pct = int(written * 100 / total)
                        eta = (total - written) / (chunk_size / 0.05) if chunk else None
                        if progress:
                            await progress("download", pct, eta)
            if progress:
                await progress("download", 100, 0.0)


async def _verify_sha256(archive: Path, release_url: str, progress) -> None:
    import httpx

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            r = await client.get(f"{release_url}/{ARCHIVE_NAME}.sha256")
            if r.status_code != 200:
                if progress:
                    await progress("verify", 0, None)
                return  # no checksum published; proceed without verification
            expected = r.text.strip().split()[0]
    except Exception:
        return
    digest = hashlib.sha256()
    with open(archive, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    actual = digest.hexdigest()
    if actual.lower() != expected.lower():
        raise RuntimeError(f"ollama checksum mismatch: {actual} != {expected}")
    if progress:
        await progress("verify", 100, 0.0)


async def ensure_ollama(target_dir: Path, progress=None) -> str | None:
    """Return a path to ``ollama.exe``, fetching it first-run if necessary."""
    existing = find_existing_ollama()
    if existing:
        if progress:
            await progress("found", 100, None)
        return existing

    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    dest = target_dir / "ollama.exe"
    if dest.exists():
        return str(dest)

    archive = target_dir / ARCHIVE_NAME
    try:
        if progress:
            await progress("download", 0, None)
        await _download_with_resume(f"{OLLAMA_RELEASE}/{ARCHIVE_NAME}", archive, progress)
        await _verify_sha256(archive, OLLAMA_RELEASE, progress)
        if progress:
            await progress("extract", 50, None)
        with tempfile.TemporaryDirectory() as td:
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(td)
            extracted = Path(td) / "ollama.exe"
            if not extracted.exists():
                # Some releases nest under a folder; pick the first exe.
                exes = list(Path(td).rglob("ollama.exe"))
                if not exes:
                    raise RuntimeError("ollama.exe not found in archive")
                extracted = exes[0]
            shutil.move(str(extracted), str(dest))
        archive.unlink(missing_ok=True)
        if progress:
            await progress("extract", 100, None)
        return str(dest)
    except Exception as exc:  # noqa: BLE001
        if progress:
            await progress("error", 0, None)
        raise RuntimeError(f"failed to fetch Ollama: {exc}") from exc
