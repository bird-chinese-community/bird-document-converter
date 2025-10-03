#!/usr/bin/env python3
"""Generate Bird documentation snapshots split by headings."""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set

REPO_URL = "https://github.com/CZ-NIC/bird.git"
OUTPUT_ROOT = Path("docs")
MANIFEST_PATH = OUTPUT_ROOT / "manifest.json"


def run(
    cmd: List[str],
    cwd: Optional[Path] = None,
    env: Optional[Dict[str, str]] = None,
) -> str:
    result = subprocess.run(
        cmd,
        cwd=cwd,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        message_parts = [
            f"Command failed with exit code {result.returncode}: {' '.join(cmd)}",
            result.stdout.strip(),
            result.stderr.strip(),
        ]
        message = "\n".join(part for part in message_parts if part)
        raise RuntimeError(message)
    return result.stdout.strip()


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^0-9a-z\-\s]+", "", value)
    value = re.sub(r"[\s]+", "-", value)
    value = re.sub(r"-+", "-", value)
    value = value.strip("-")
    return value or "section"


class HeadingSplitter:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.written_files: List[Path] = []
        self.used_h1: Set[str] = set()
        self.used_h2: Dict[str, Set[str]] = {}
        self.current_h1_slug: Optional[str] = None
        self.current_h1_dir: Optional[Path] = None
        self.current_h1_buffer: List[str] = []
        self.current_h2_slug: Optional[str] = None
        self.current_h2_path: Optional[Path] = None
        self.current_h2_buffer: List[str] = []

    def _unique_slug(self, slug: str, used: Set[str]) -> str:
        candidate = slug
        counter = 2
        while candidate in used:
            candidate = f"{slug}-{counter}"
            counter += 1
        used.add(candidate)
        return candidate

    def _flush_h2(self) -> None:
        if not self.current_h2_path:
            return
        content = "\n".join(self.current_h2_buffer).strip()
        if content:
            self.current_h2_path.write_text(content + "\n", encoding="utf-8")
            self.written_files.append(self.current_h2_path)
        self.current_h2_slug = None
        self.current_h2_path = None
        self.current_h2_buffer = []

    def _flush_h1(self) -> None:
        self._flush_h2()
        if not self.current_h1_dir:
            return
        content = "\n".join(self.current_h1_buffer).strip()
        if content:
            index_path = self.current_h1_dir / "index.md"
            index_path.write_text(content + "\n", encoding="utf-8")
            self.written_files.append(index_path)
        self.current_h1_slug = None
        self.current_h1_dir = None
        self.current_h1_buffer = []

    def process(self, lines: Iterable[str]) -> List[Path]:
        for raw_line in lines:
            line = raw_line.rstrip("\n")
            if line.startswith("# ") and not line.startswith("## "):
                self._flush_h1()
                title = line[2:].strip()
                slug = self._unique_slug(slugify(title), self.used_h1)
                self.current_h1_slug = slug
                self.current_h1_dir = self.base_dir / slug
                self.current_h1_dir.mkdir(parents=True, exist_ok=True)
                self.used_h2.setdefault(slug, set())
                self.current_h1_buffer = [f"# {title}"]
                self.current_h2_buffer = []
                self.current_h2_slug = None
                self.current_h2_path = None
            elif line.startswith("## "):
                if not self.current_h1_dir:
                    continue
                self._flush_h2()
                title = line[3:].strip()
                slug = self._unique_slug(slugify(title), self.used_h2[self.current_h1_slug])
                self.current_h2_slug = slug
                self.current_h2_path = self.current_h1_dir / f"{slug}.md"
                self.current_h2_buffer = [f"## {title}"]
            else:
                if self.current_h2_path:
                    self.current_h2_buffer.append(line)
                elif self.current_h1_dir:
                    self.current_h1_buffer.append(line)
        self._flush_h1()
        return self.written_files


def prepare_markdown(source_dir: Path, work_dir: Path, *, build_if_missing: bool) -> tuple[Path, Path, str, str]:
    work_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    pandoc_path = shutil.which("pandoc")
    if pandoc_path:
        env["PANDOC"] = pandoc_path

    version = (source_dir / "VERSION").read_text(encoding="utf-8").strip()

    parser = source_dir / "tools" / "linuxdoc.lua"
    bird_md = work_dir / "bird.md"
    prog_md = work_dir / "prog.md"

    bird_sgml = source_dir / "obj" / "doc" / "bird.sgml"
    prog_sgml = source_dir / "obj" / "doc" / "prog.sgml"

    artifacts = (bird_sgml, prog_sgml)
    if any(not path.exists() for path in artifacts):
        if not build_if_missing:
            missing_paths = ", ".join(str(path.relative_to(source_dir)) for path in artifacts if not path.exists())
            raise RuntimeError(
                "Missing documentation artifacts. Run 'make obj/doc/bird.sgml obj/doc/prog.sgml' "
                f"in {source_dir} before invoking the converter (missing: {missing_paths})."
            )
        run(["autoreconf", "-fi"], cwd=source_dir)
        run(["./configure"], cwd=source_dir, env=env)
        run(["make", "obj/doc/bird.sgml", "obj/doc/prog.sgml"], cwd=source_dir, env=env)

    missing_after_build = [path for path in artifacts if not path.exists()]
    if missing_after_build:
        missing_paths = ", ".join(str(path.relative_to(source_dir)) for path in missing_after_build)
        raise RuntimeError(
            "Documentation artifacts were not generated. Expected to find: "
            f"{missing_paths} in {source_dir}."
        )

    run(
        ["pandoc", "-f", str(parser), "-s", "-t", "gfm", "-o", str(bird_md), str(bird_sgml)],
        cwd=source_dir,
        env=env,
    )
    run(
        ["pandoc", "-f", str(parser), "-s", "-t", "gfm", "-o", str(prog_md), str(prog_sgml)],
        cwd=source_dir,
        env=env,
    )

    commit = run(["git", "rev-parse", "HEAD"], cwd=source_dir)

    return bird_md, prog_md, version, commit


def write_manifest(files: Iterable[Path], version: str, commit: str) -> None:
    manifest_entries = []
    for path in sorted(files):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest_entries.append({
            "path": path.as_posix(),
            "sha256": digest,
        })

    data = {
        "source_repo": REPO_URL,
        "source_commit": commit,
        "source_version": version,
        "files": manifest_entries,
    }
    MANIFEST_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert Bird SGML documentation to Markdown snapshots.")
    parser.add_argument(
        "--branch",
        dest="branch",
        help="Bird repository branch to clone when no source directory is provided.",
    )
    parser.add_argument(
        "--source",
        dest="source",
        type=Path,
        help="Path to a Bird repository checkout that already contains the built SGML artifacts.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    OUTPUT_ROOT.mkdir(exist_ok=True)

    with contextlib.ExitStack() as stack:
        if args.source:
            source_path = Path(args.source).resolve()
            if not source_path.exists():
                raise FileNotFoundError(f"Provided source directory does not exist: {source_path}")
        else:
            raise RuntimeError("Branch-based source fetching is disabled. Please provide --source pointing to a Bird checkout.")

        work_dir_str = stack.enter_context(tempfile.TemporaryDirectory())
        work_dir = Path(work_dir_str)

        build_if_missing = args.source is None
        bird_md, prog_md, version, commit = prepare_markdown(source_path, work_dir, build_if_missing=build_if_missing)

        all_files: List[Path] = []
        mapping = {
            "user": bird_md,
            "programmer": prog_md,
        }
        for category, md_path in mapping.items():
            if not md_path.exists() or md_path.stat().st_size == 0:
                continue
            category_dir = OUTPUT_ROOT / category
            if category_dir.exists():
                shutil.rmtree(category_dir)
            category_dir.mkdir(parents=True, exist_ok=True)
            lines = md_path.read_text(encoding="utf-8").splitlines()
            splitter = HeadingSplitter(category_dir)
            files = splitter.process(lines)
            all_files.extend(files)
        write_manifest(all_files, version, commit)


if __name__ == "__main__":
    main()
