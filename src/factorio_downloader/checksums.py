import hashlib
from enum import IntEnum
from pathlib import Path

import aiohttp

DOWNLOAD_SHA_URL = "https://www.factorio.com/download/sha256sums/"


class FileCheckResult(IntEnum):
    VALID = 0
    FILE_MISSING = 1
    INVALID_FILE_NAME = 2
    CHECKSUM_MISMATCH = 3


async def download_checksums(
    session: aiohttp.ClientSession | None = None,
) -> dict[str, str]:
    if session is None:
        session = aiohttp.ClientSession()
    async with session.get(DOWNLOAD_SHA_URL) as resp:
        resp.raise_for_status()
        data = await resp.text()

    file_to_checksum: dict[str, str] = {}
    for line in data.splitlines():
        checksum, filename = line.split("  ")
        file_to_checksum[filename] = checksum

    return file_to_checksum


class FactorioValidFileChecker:
    def __init__(self, checksums: dict[str, str]):
        self.checksums = checksums

    @staticmethod
    async def from_web_checksums() -> "FactorioValidFileChecker":
        checksums = await download_checksums()
        return FactorioValidFileChecker(checksums)

    def check_file(self, factorio_file: Path) -> FileCheckResult:
        if not factorio_file.is_file():
            return FileCheckResult.FILE_MISSING
        file_name = factorio_file.name
        expected_file_checksum = self.checksums.get(file_name)
        if expected_file_checksum is None:
            return FileCheckResult.INVALID_FILE_NAME

        with factorio_file.open("rb") as f:
            file_checkusm = hashlib.file_digest(f, "sha256").hexdigest()

        return (
            FileCheckResult.VALID
            if file_checkusm == expected_file_checksum
            else FileCheckResult.CHECKSUM_MISMATCH
        )
