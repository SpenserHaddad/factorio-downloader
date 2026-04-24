import datetime
from enum import StrEnum
from typing import Annotated, Any, NamedTuple

from pydantic import BaseModel, BeforeValidator, Field, StringConstraints


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


def ensure_semver(value: Any) -> Any:
    if isinstance(value, str):
        return list(SemVer.from_str(value))
    else:
        return value


class DownloadFileInfo(BaseModel):
    name: str
    build: FactorioBuild
    sha256: Annotated[
        str,
        StringConstraints(
            min_length=64,
            max_length=64,
            to_lower=True,
            ascii_only=True,
            pattern="[a-fA-F0-9]+",
        ),
    ]


class DownloadManifest(BaseModel):
    download_version: Annotated[SemVer, BeforeValidator(ensure_semver)]
    download_date: datetime.datetime
    fdl_version: SemVer
    files: Annotated[list[DownloadFileInfo], Field(default_factory=list)]
