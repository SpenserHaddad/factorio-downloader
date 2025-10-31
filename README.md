# factorio-downloader

A rough and dirty script for downloading Factorio binaries from factorio.com.

Mostly built as a Python wrapper around with https://wiki.factorio.com/Download_API.


# Installation

Dependencies are listed in a typical PEP 621 `pyproject.toml`. Install with whatever
package manager you like. Tested with `uv`, however.

```bash
uv sync
```

# Usage

Run `python main.py`, with `--help` for flag details.

## Help

```
usage: main.py [-h] [--build {alpha,expansion,demo,headless}] [--version VERSION] [--distro DISTRO] [--outdir OUTDIR] [--tempdir TEMPDIR]

Download Factorio binaries from the official site. You must set your Factorio username 
and token (see Token on https://factorio.com/profile) and set them as the environment
variables FACTORIO_USERNAME and FACTORIO_TOKEN, respectively. These can be provided as
a .env file.

options:
  -h, --help            show this help message and exit
  --build {alpha,expansion,demo,headless}, -b {alpha,expansion,demo,headless}
                        The build of the game to download. Defaults to 'expansion', which includes Space Age.
  --version VERSION, -v VERSION
                        The version of the game to download. Must either be a version triple (e.g. 2.0.10) or the word 'latest'.
  --distro DISTRO, -d DISTRO
                        The platform(s) to download executables for. May be provided multiple times. Defaults to all available platforms.
  --outdir OUTDIR, -o OUTDIR
                        The directory to save the files into. Defaults to the cwd.
  --tempdir TEMPDIR, -t TEMPDIR
                        The directory to download the files to before saving. Defaults to '--outdir'.
```