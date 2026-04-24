"""Download the latest version of Factorio from the official site.

This grabs the DRM-free copies of the latest version for all win64, osx, and linux64.

Mostly taken from https://wiki.factorio.com/Download_API and https://artentus.github.io/FactorioApiDoc/auth-api/
"""

import argparse
import asyncio
import datetime
import functools
import json
import logging
import logging.handlers
import os
import sys
import textwrap
from importlib.metadata import version
from pathlib import Path
from typing import Final, Literal, cast

import aiohttp
from dotenv import load_dotenv
from rich.console import Console
from rich.logging import RichHandler
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

from factorio_downloader._urls import LATEST_RELEASE_URL
from factorio_downloader.download import (
    DownloadProgressInfo,
    DownloadProgressUpdate,
    FactorioDownloader,
)
from factorio_downloader.models import (
    DownloadManifest,
    FactorioBuild,
    FactorioDistro,
    SemVer,
)

MANIFEST_FILE: Final[str] = "manifest.json"

_logger = logging.getLogger("factorio-downloader")


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
    try:
        manifest = DownloadManifest.model_validate_json(
            (save_dir / MANIFEST_FILE).read_text()
        )
        downloaded_version = manifest.download_version
    except Exception:
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

        def progress_update(
            task_id: TaskID,
            update_type: DownloadProgressUpdate,
            data: DownloadProgressInfo,
        ):
            match update_type:
                case DownloadProgressUpdate.GOT_FILE_SIZE:
                    progress.update(
                        task_id,
                        description=f"Downloading {data.version}/{data.build}/{data.distro}",
                        total=data.total_size,
                    )
                case DownloadProgressUpdate.DOWNLOADED_CHUNK:
                    progress.update(task_id, completed=data.downloaded)
                case DownloadProgressUpdate.FILE_ALREADY_DOWNLOADED:
                    description = f"{data.version}/{data.build}/{data.distro} is already downloaded."
                    progress.update(
                        task_id, description=description, completed=data.total_size
                    )
                case DownloadProgressUpdate.COMPLETED:
                    final_description = "{data.distro} download complete!"
                    progress.update(
                        task_id,
                        completed=data.total_size,
                        description=final_description,
                    )

        async with (
            aiohttp.ClientSession() as session,
            asyncio.TaskGroup() as tg,
            FactorioDownloader(
                username, token, save_dir, download_dir=download_dir, session=session
            ) as downloader,
        ):
            download_tasks: dict[FactorioDistro, asyncio.Task[Path]] = {}
            for distro in distros:
                task = progress.add_task(
                    f"Downloading {download_version}/{build}/{distro}"
                )
                progress_callback = functools.partial(progress_update, task)
                download_tasks[distro] = tg.create_task(
                    downloader.download(
                        distro,
                        download_version,
                        build,
                        progress_callback=progress_callback,
                    )
                )
    for distro, task in download_tasks.items():
        save_file = task.result()
        console.print(f"Saved {download_version}/{build}/{distro} to {save_file}.")

    updated_manifest = DownloadManifest(
        download_version=download_version,
        download_date=run_time,
        fdl_version=fdl_version,
        files=[],
    )
    manifest_file.write_text(json.dumps(updated_manifest.model_dump_json()))


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
