"""Raw-data inventory: a SHA-256 manifest of data/raw_data and a check against it (Stage 0).

Why: BoE curves are revised and the DMO re-issues reports under the same file names, so a file
name is not an identity. The manifest pins the exact bytes every result was built from; any later
stage can call `verify_manifest()` and refuse to run on changed inputs.

Usage
  python -m gilt_study.inventory --check    # compare data/raw_data with data/raw_manifest.csv
  python -m gilt_study.inventory --write    # (re)write the manifest; only after a logged re-download

The manifest lives in data/ (not in raw_data/, which is never written to).
"""
import argparse
import hashlib
import sys
from pathlib import Path

import pandas as pd

from . import paths

MANIFEST_COLUMNS = ["path", "bytes", "sha256"]


def sha256(path: Path, chunk: int = 1 << 20) -> str:
    """SHA-256 hex digest of a file, read in 1 MB chunks."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def list_raw_files(raw_dir: Path = paths.RAW) -> list[Path]:
    """Every file under raw_dir (recursively), sorted by POSIX path; hidden files skipped."""
    files = [p for p in Path(raw_dir).rglob("*") if p.is_file() and not p.name.startswith(".")]
    return sorted(files, key=lambda p: p.relative_to(raw_dir).as_posix())


def build_manifest(raw_dir: Path = paths.RAW) -> pd.DataFrame:
    """One row per raw file: path relative to raw_dir (POSIX style), size in bytes, SHA-256."""
    rows = [dict(path=p.relative_to(raw_dir).as_posix(), bytes=p.stat().st_size, sha256=sha256(p))
            for p in list_raw_files(raw_dir)]
    return pd.DataFrame(rows, columns=MANIFEST_COLUMNS)


def write_manifest(raw_dir: Path = paths.RAW, out: Path = paths.RAW_MANIFEST) -> pd.DataFrame:
    """Build the manifest and save it as CSV."""
    m = build_manifest(raw_dir)
    m.to_csv(out, index=False)
    return m


def verify_manifest(raw_dir: Path = paths.RAW, manifest: Path = paths.RAW_MANIFEST) -> list[str]:
    """Problems found comparing raw_dir with the manifest; an empty list means all files match.

    Reports files missing from raw_dir, files not in the manifest, and size or hash changes.
    """
    expected = pd.read_csv(manifest, dtype={"path": str, "bytes": "int64", "sha256": str})
    expected = expected.set_index("path")
    found = {p.relative_to(raw_dir).as_posix(): p for p in list_raw_files(raw_dir)}
    problems = [f"missing: {name}" for name in expected.index if name not in found]
    problems += [f"not in manifest: {name}" for name in found if name not in expected.index]
    for name, p in found.items():
        if name not in expected.index:
            continue
        if p.stat().st_size != expected.at[name, "bytes"]:
            problems.append(f"size changed: {name}")
        elif sha256(p) != expected.at[name, "sha256"]:
            problems.append(f"hash changed: {name}")
    return problems


def main(argv=None) -> int:
    """Command-line entry point; returns a process exit code (0 = all files match)."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true", help="verify data/raw_data against the manifest")
    g.add_argument("--write", action="store_true", help="rewrite the manifest from data/raw_data")
    args = ap.parse_args(argv)
    if args.write:
        m = write_manifest()
        print(f"Wrote {paths.RAW_MANIFEST}: {len(m)} files, {m.bytes.sum() / 1e6:.1f} MB")
        return 0
    problems = verify_manifest()
    if problems:
        print("\n".join(problems))
        return 1
    print(f"OK: every file in {paths.RAW} matches {paths.RAW_MANIFEST.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
