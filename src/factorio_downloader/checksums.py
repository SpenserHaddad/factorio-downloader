import aiohttp

DOWNLOAD_SHA_URL = "https://www.factorio.com/download/sha256sums/"


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
