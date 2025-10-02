# Bird Documentation Converter

This repository automates the process of building the official [CZ-NIC Bird](https://github.com/CZ-NIC/bird) documentation, converting the SGML sources to Markdown, and splitting the output into smaller, heading-based fragments under `docs/`.

## How it works

1. Clone the upstream Bird repository (either locally or inside GitHub Actions).
2. Regenerate the documentation SGML with the standard autotools build (`autoreconf`, `./configure`, `make obj/doc/bird.sgml obj/doc/prog.sgml`).
3. Convert the SGML to Markdown with `pandoc` and the upstream `linuxdoc.lua` parser.
4. Split the Markdown into section files and record checksums in `docs/manifest.json`.

The entry point for the conversion is `scripts/convert_bird_docs.py`.

## Local usage

```bash
python3 scripts/convert_bird_docs.py [--branch <bird-branch>] [--source /path/to/bird]
```

- When `--source` is omitted, the script clones the Bird repository into a temporary directory using the optional `--branch` argument (defaults to `master`).
- When `--source` is provided, the script reuses that checkout. In this mode you must run `make obj/doc/bird.sgml obj/doc/prog.sgml` yourself before invoking the converter.

The generated Markdown fragments are written to `docs/` and can be committed or published wherever you need them.

## GitHub Actions workflow

The workflow defined in `.github/workflows/bird-docs.yml` rebuilds the documentation on a schedule and on manual dispatch. It performs the following steps:

- Restore cached APT packages to speed up dependency installation.
- Install all build dependencies (`pandoc`, autotools, and supporting packages).
- Clone the Bird repository and determine the branch to mirror (matches the triggering branch by default, but can be overridden when manually dispatching the workflow).
- Run the SGML build, convert the output to Markdown, and split the resulting files.
- Auto-commit the updated `docs/` snapshot back to the repository.

## Requirements

For local execution you need:

- Python 3.8 or later
- `pandoc`
- Autotools toolchain (`autoconf`, `automake`, `libtool`, `make`, `pkg-config`)
- `flex` and `bison`

On macOS you can install these via Homebrew; on Debian/Ubuntu the provided workflow shows the required packages.

## Contributing

Issues and pull requests are welcome. Please keep the generated `docs/` directory clean (only content produced by the converter) and run `python3 scripts/convert_bird_docs.py` before submitting changes that affect documentation output.
