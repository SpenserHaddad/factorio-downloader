from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Callable

from aiohttp import ClientSession

from factorio_downloader._urls import DOWNLOAD_URL_TEMPLATE
from factorio_downloader.checksums import FactorioValidFileChecker, FileCheckResult
from factorio_downloader.models import FactorioBuild, FactorioDistro, SemVer


class DownloadProgressUpdate(Enum):
    START = auto()
    GOT_FILE_SIZE = auto()
    DOWNLOADED_CHUNK = auto()
    COMPLETED = auto()
    FILE_ALREADY_DOWNLOADED = auto()


@dataclass
class DownloadProgressInfo:
    build: FactorioBuild
    distro: FactorioDistro
    version: SemVer
    total_size: int | None = None
    downloaded: int = 0
    save_file: Path | None = None


class FactorioDownloader:
    def __init__(
        self,
        username: str,
        token: str,
        save_dir: Path,
        download_dir: Path | None = None,
        session: ClientSession | None = None,
    ):
        self._username: str = username
        self._token: str = token
        self._session: ClientSession | None = session
        self._manual_session = session is None
        self._save_dir = save_dir
        self._download_dir = download_dir

        self._file_checker: FactorioValidFileChecker | None = None

    @property
    def session(self) -> ClientSession:
        if self._session is None:
            raise RuntimeError(
                "No session found. Need to provide a session of use as an async context manager."
            )
        return self._session

    @property
    def file_checker(self) -> FactorioValidFileChecker:
        if self._file_checker is None:
            raise RuntimeError(
                "File checker not set. Either call FactorioDownloader.setup() or use this object as a context manager."
            )
        return self._file_checker

    async def setup(self):
        if self._session is None or self._session.closed:
            self._session = ClientSession()
            self._manual_session = True
        else:
            self._manual_session = False

        if self._file_checker is None:
            self._file_checker = await FactorioValidFileChecker.from_web_checksums()

    async def __aenter__(self):
        await self.setup()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self._manual_session and self._session is not None:
            self._session.close()

    async def download(
        self,
        distro: FactorioDistro,
        version: SemVer,
        build: FactorioBuild,
        progress_callback: Callable[
            [DownloadProgressUpdate, DownloadProgressInfo], None
        ]
        | None = None,
    ) -> Path:
        download_url = DOWNLOAD_URL_TEMPLATE.format(
            version=version, build=build.value, distro=distro.value
        )
        progress_info = DownloadProgressInfo(
            build=build, distro=distro, version=version
        )

        def trigger_callback(status: DownloadProgressUpdate):
            if progress_callback is not None:
                progress_callback(status, progress_info)

        async with self.session.get(
            download_url, params={"username": self._username, "token": self._token}
        ) as download_resp:
            download_resp.raise_for_status()
            progress_info.total_size = int(
                download_resp.headers.get("content-length", 0)
            )
            trigger_callback(DownloadProgressUpdate.GOT_FILE_SIZE)

            file_name = download_resp.url.name
            save_file = self._save_dir / file_name
            progress_info.save_file = save_file

            file_check_result = self.file_checker.check_file(save_file)
            # FILE_MISSING or INVALID_CHECKSUM both mean we should (re)download the file.
            if file_check_result == FileCheckResult.VALID:
                trigger_callback(DownloadProgressUpdate.FILE_ALREADY_DOWNLOADED)
                return save_file
            elif file_check_result == FileCheckResult.INVALID_FILE_NAME:
                msg = f"Wanted to save file to {file_check_result}, but it's not a valid Factorio file."
                raise RuntimeError(msg)

            download_dir = self._download_dir or self._save_dir
            download_file = download_dir / (save_file.name + ".tmp")
            download_file.unlink(missing_ok=True)

            with download_file.open("wb") as f:
                async for chunk in download_resp.content.iter_chunked(163_840):
                    f.write(chunk)
                    progress_info.downloaded += len(chunk)
                    trigger_callback(DownloadProgressUpdate.DOWNLOADED_CHUNK)

            save_file.unlink(missing_ok=True)
            download_file.rename(save_file)
            trigger_callback(DownloadProgressUpdate.COMPLETED)
        return download_file
