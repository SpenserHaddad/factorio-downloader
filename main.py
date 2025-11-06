"""Download the latest version of Factorio from the official site.

This grabs the DRM-free copies of the latest version for all win64, osx, and linux64.

Mostly taken from https://wiki.factorio.com/Download_API and https://artentus.github.io/FactorioApiDoc/auth-api/
"""

import argparse
import asyncio
import os
import sys
import textwrap
from enum import StrEnum
from pathlib import Path
from typing import Final, Literal, NamedTuple, cast

import aiohttp
from dotenv import load_dotenv
from rich.console import Console
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

LOGIN_URL = "https://www.factorio.com/login"
# LOGIN_URL = "https://auth.factorio.com/api-login"
LATEST_RELEASE_URL = "https://factorio.com/api/latest-releases"
DOWNLOAD_URL_TEMPLATE = (
    "https://www.factorio.com/get-download/{version}/{build}/{distro}"
)
DOWNLOADED_VERSION_FILE: Final[str] = "version.txt"


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


class FactorioVersion(NamedTuple):
    major: int
    minor: int
    patch: int

    @staticmethod
    def from_str(s: str) -> "FactorioVersion":
        version_list: list[int] = [int(v) for v in s.split(".")]
        if len(version_list) != 3:
            raise ValueError(f'Incorrect number of version values in version: "{s}"')
        return FactorioVersion(
            major=version_list[0], minor=version_list[1], patch=version_list[2]
        )

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


EXTENSION_FOR_DISTRO = {
    FactorioDistro.WIN64: "exe",
    FactorioDistro.WIN64_MANUAL: "zip",
    FactorioDistro.OSX: "dmg",
    FactorioDistro.LINUX64: "tar.gz",
}


async def get_latest_version(
    build: FactorioBuild = FactorioBuild.EXPANSION,
) -> FactorioVersion:
    async with aiohttp.ClientSession() as s:
        resp = await s.get(LATEST_RELEASE_URL)
        version_info = await resp.json()
    version_str = cast(str, version_info["stable"][build.value])
    return FactorioVersion.from_str(version_str)


def get_downloaded_version(version_file: Path) -> FactorioVersion | None:
    if not version_file.is_file():
        return None
    version_str = version_file.read_text().split()[0].strip()
    return FactorioVersion.from_str(version_str)


async def main():
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

    args = parser.parse_args()

    load_dotenv()

    try:
        username = os.environ["FACTORIO_USERNAME"]
        token = os.environ["FACTORIO_TOKEN"]
    except KeyError as ke:
        raise KeyError(
            "The environment variables FACTORIO_USERNAME and FACTORIO_TOKEN must be defined, optionally in a .env file."
        ) from ke

    console = Console()

    build = cast(FactorioBuild, args.build)
    distros = cast(list[FactorioDistro], args.distro)
    version_str = cast(str, args.version)
    requested_version: Literal["latest"] | FactorioVersion
    if version_str == "latest" or version_str is None:
        requested_version = "latest"
    else:
        requested_version = FactorioVersion.from_str(version_str)

    save_dir = cast(Path, args.outdir)
    download_dir = cast(Path | None, args.tempdir)
    if download_dir is None:
        download_dir = save_dir

    version_file = save_dir / DOWNLOADED_VERSION_FILE
    downloaded_version: FactorioVersion | None = get_downloaded_version(version_file)
    # No downloaded version means either our last DL was corrupted or it's our first run
    if downloaded_version is not None:
        if requested_version == "latest":
            latest_version: FactorioVersion = await get_latest_version(build=build)
            if latest_version == downloaded_version:
                console.print(
                    f"Latest version {latest_version} is already downloaded, nothing to do.",
                    style="blue",
                )
                sys.exit(0)
            elif latest_version < downloaded_version:
                console.print(
                    "Latest version is older than the downloaded version, wtf?",
                    style="red bold",
                )
                sys.exit(-10)
        elif downloaded_version == requested_version:
            console.print(
                f"Requested version {requested_version} is already downloaded, nothing to do.",
                style="blue",
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
    version_file.unlink(missing_ok=True)

    with progress as progress:
        async with aiohttp.ClientSession() as session, asyncio.TaskGroup() as tg:

            async def download(distro: FactorioDistro):
                nonlocal build
                download_url = DOWNLOAD_URL_TEMPLATE.format(
                    version=requested_version, build=build.value, distro=distro.value
                )

                save_file = save_dir / f"{distro.value}.{EXTENSION_FOR_DISTRO[distro]}"
                download_file = download_dir / (save_file.name + ".tmp")

                download_file.unlink(missing_ok=True)
                download_task = progress.add_task(
                    f"Downloading {requested_version}/{build}/{distro}"
                )

                async with session.get(
                    download_url, params={"username": username, "token": token}
                ) as download_resp:
                    download_resp.raise_for_status()
                    total_size = int(download_resp.headers.get("content-length", 0))
                    progress.update(download_task, total=total_size)
                    with download_file.open("wb") as f:
                        async for chunk in download_resp.content.iter_chunked(163_840):
                            f.write(chunk)
                            progress.update(download_task, advance=len(chunk))

                    save_file.unlink(missing_ok=True)
                    download_file.rename(save_file)
                    progress.update(
                        download_task,
                        description=f"Saved {requested_version}/{build}/{distro} to {save_file}",
                    )

            for distro in distros:
                tg.create_task(download(distro))
    version_file.write_text(
        f"{downloaded_version if downloaded_version else requested_version}\n"
    )


if __name__ == "__main__":
    asyncio.run(main())
