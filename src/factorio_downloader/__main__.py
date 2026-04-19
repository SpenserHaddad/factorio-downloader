"""Download the latest version of Factorio from the official site.

This grabs the DRM-free copies of the latest version for all win64, osx, and linux64.

Mostly taken from https://wiki.factorio.com/Download_API and https://artentus.github.io/FactorioApiDoc/auth-api/
"""

import argparse
import asyncio
import datetime
import hashlib
import json
import logging
import logging.handlers
import os
import sys
import textwrap
from enum import StrEnum
from importlib.metadata import version
from pathlib import Path
from typing import Final, Literal, NamedTuple, cast

import aiohttp
from dateutil import parser
from dotenv import load_dotenv
from rich.console import Console
from rich.logging import RichHandler
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

from factorio_downloader.checksums import download_checksums

LOGIN_URL = "https://www.factorio.com/login"
LATEST_RELEASE_URL = "https://factorio.com/api/latest-releases"
DOWNLOAD_URL_TEMPLATE = (
    "https://www.factorio.com/get-download/{version}/{build}/{distro}"
)
MANIFEST_FILE: Final[str] = "manifest.json"

_logger = logging.getLogger("factorio-downloader")


class FactorioBuild(StrEnum):
    ALPHA = "alpha"
    EXPANSION = "expansion"
    DEMO = "demo"
    HEADLESS = "headless"


class FactorioDistro(StrEnum):
    WIN64 = "win64"
    WIN64_MANUAL = "win64-manual"
    OSX = "osx"
    LINUX64 = "linux64"


class SemVer(NamedTuple):
    major: int
    minor: int
    patch: int

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    @staticmethod
    def from_str(semver_str: str) -> "SemVer":
        fields = semver_str.split(".")
        if len(fields) != 3:
            raise ValueError(
                "semver_str should be a string in format <major>.<minor>.<patch>"
            )
        fields_int = [int(f) for f in fields]
        return SemVer(major=fields_int[0], minor=fields_int[1], patch=fields_int[2])


class DownloadManifest(NamedTuple):
    download_version: SemVer
    download_date: datetime.datetime
    fdl_version: SemVer

    def to_json(self) -> dict[str, str]:
        return {
            "download_version": str(self.download_version),
            "download_date": self.download_date.isoformat(),
            "fdl_version": str(self.fdl_version),
        }

    @staticmethod
    def from_json(data: dict[str, str]) -> "DownloadManifest":
        return DownloadManifest(
            download_version=SemVer.from_str(data["download_version"]),
            download_date=parser.parse(data["download_date"]),
            fdl_version=SemVer.from_str(data["fdl_version"]),
        )


EXTENSION_FOR_DISTRO = {
    FactorioDistro.WIN64: "exe",
    FactorioDistro.WIN64_MANUAL: "zip",
    FactorioDistro.OSX: "dmg",
    FactorioDistro.LINUX64: "tar.gz",
}


async def get_latest_version(
    build: FactorioBuild = FactorioBuild.EXPANSION,
) -> SemVer:
    async with aiohttp.ClientSession() as s:
        resp = await s.get(LATEST_RELEASE_URL)
        version_info = await resp.json()
    version_str = cast(str, version_info["stable"][build.value])
    return SemVer.from_str(version_str)


def get_downloaded_version(version_file: Path) -> SemVer | None:
    if not version_file.is_file():
        return None
    version_str = version_file.read_text().split()[0].strip()
    return SemVer.from_str(version_str)


async def _run(
    build: FactorioBuild,
    factorio_version: str,
    distros: list[FactorioDistro],
    save_dir: Path,
    download_dir: Path | None,
    console: Console,
):
    fdl_version = SemVer.from_str(version("factorio-downloader"))
    run_time = datetime.datetime.now(datetime.timezone.utc)
    _logger.info(f"Running fdl-v{fdl_version} at {run_time}.")

    load_dotenv()
    try:
        username = os.environ["FACTORIO_USERNAME"]
        token = os.environ["FACTORIO_TOKEN"]
    except KeyError as ke:
        raise KeyError(
            "The environment variables FACTORIO_USERNAME and FACTORIO_TOKEN must be defined, optionally in a .env file."
        ) from ke

    version_str = factorio_version
    requested_version: Literal["latest"] | SemVer
    if version_str == "latest" or version_str is None:
        requested_version = "latest"
    else:
        requested_version = SemVer.from_str(version_str)

    if download_dir is None:
        download_dir = save_dir

    manifest_file = save_dir / MANIFEST_FILE
    downloaded_version: SemVer | None = None
    if manifest_file.is_file():
        manifest_file_raw = json.loads((save_dir / MANIFEST_FILE).read_text())
        manifest = DownloadManifest.from_json(manifest_file_raw)
        downloaded_version = manifest.download_version
    else:
        downloaded_version = None

    if requested_version == "latest":
        download_version: SemVer = await get_latest_version(build=build)
        _logger.info(f"Latest version requested, downloading {download_version}.")
    else:
        download_version = requested_version

    # No downloaded version means either our last DL was corrupted or it's our first run
    if downloaded_version is not None:
        if download_version == downloaded_version:
            _logger.info(
                f"Version {download_version} is already downloaded, nothing to do.",
                extra={"style": "blue"},
            )
            sys.exit(0)

    progress = Progress(
        TextColumn("{task.description}"),
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
    )

    # Remove version file while we wait, in case one of the tasks fails, so we can
    # tell if the files are in a corrupted state. (TODO: Find checksums?)
    manifest_file.unlink(missing_ok=True)
    save_dir.mkdir(exist_ok=True)

    with progress as progress:
        async with aiohttp.ClientSession() as session, asyncio.TaskGroup() as tg:
            checksums = await download_checksums(session=session)

            async def download(distro: FactorioDistro):
                nonlocal build
                download_url = DOWNLOAD_URL_TEMPLATE.format(
                    version=download_version, build=build.value, distro=distro.value
                )

                download_task = progress.add_task(
                    f"Downloading {download_version}/{build}/{distro}"
                )
                async with session.get(
                    download_url, params={"username": username, "token": token}
                ) as download_resp:
                    download_resp.raise_for_status()
                    total_size = int(download_resp.headers.get("content-length", 0))
                    progress.update(download_task, total=total_size)

                    file_name = download_resp.url.name
                    save_file = save_dir / file_name

                    if save_file.is_file():
                        with save_file.open("rb") as f:
                            save_file_checksum = hashlib.file_digest(
                                f, "sha256"
                            ).hexdigest()
                        expected_checksum = checksums[save_file]
                        if expected_checksum == save_file_checksum:
                            progress.update(
                                download_task,
                                description=f"Build {download_version}/{build}/{distro} is already saved to {save_file}.",
                                completed=total_size,
                            )
                    else:
                        download_file = download_dir / (save_file.name + ".tmp")
                        download_file.unlink(missing_ok=True)

                        with download_file.open("wb") as f:
                            async for chunk in download_resp.content.iter_chunked(
                                163_840
                            ):
                                f.write(chunk)
                                progress.update(download_task, advance=len(chunk))

                        save_file.unlink(missing_ok=True)
                        download_file.rename(save_file)
                        progress.update(
                            download_task,
                            description=f"Saved {download_version}/{build}/{distro} to {save_file}",
                        )

            for distro in distros:
                tg.create_task(download(distro))

    updated_manifest = DownloadManifest(download_version, run_time, fdl_version)
    manifest_file.write_text(json.dumps(updated_manifest.to_json()))


def main():
    cmd_description = (
        "Download Factorio binaries from the official site.\n\n"
        "You must set your Factorio username and token (see Token on "
        "https://factorio.com/profile) and set them as the environment variables "
        "FACTORIO_USERNAME and FACTORIO_TOKEN, respectively. These can be provided "
        "as a .env file."
    )
    parser = argparse.ArgumentParser(
        description="\n".join(textwrap.wrap(cmd_description, width=70))
    )
    parser.add_argument(
        "--build",
        "-b",
        default=FactorioBuild.EXPANSION,
        choices=[b.value for b in FactorioBuild],
        type=FactorioBuild,
        help="The build of the game to download. Defaults to 'expansion', which includes Space Age.",
    )
    parser.add_argument(
        "--version",
        "-v",
        default="latest",
        help="The version of the game to download. Must either be a version triple (e.g. 2.0.10) or the word 'latest'.",
    )
    parser.add_argument(
        "--distro",
        "-d",
        action="append",
        default=[d for d in FactorioDistro],
        type=FactorioDistro,
        help=(
            "The platform(s) to download executables for. May be provided multiple "
            "times. Defaults to all available platforms."
        ),
    )
    parser.add_argument(
        "--outdir",
        "-o",
        type=Path,
        default=Path.cwd(),
        help="The directory to save the files into. Defaults to the cwd.",
    )
    parser.add_argument(
        "--tempdir",
        "-t",
        type=Path,
        help="The directory to download the files to before saving. Defaults to '--outdir'.",
    )
    parser.add_argument(
        "--logfile",
        type=Path,
        default=None,
        help="The optional file to log output to.",
    )
    parser.add_argument("--quiet", "-q", action="store_true", help="Disable output.")

    args = parser.parse_args()

    logger = logging.getLogger("factorio-downloader")
    logger.setLevel(logging.DEBUG)

    if args.logfile is not None:
        logger.addHandler(
            logging.handlers.RotatingFileHandler(
                args.logfile, backupCount=2, maxBytes=10_000_000
            )
        )

    console = Console(quiet=args.quiet)
    logger.addHandler(
        RichHandler(
            console=console,
            show_time=False,
            show_level=False,
            show_path=False,
            markup=True,
        )
    )

    try:
        asyncio.run(
            _run(
                args.build,
                args.version,
                args.distro,
                args.outdir,
                args.tempdir,
                console,
            )
        )
    except Exception:
        _logger.exception("Failed to download")
        raise


if __name__ == "__main__":
    main()
