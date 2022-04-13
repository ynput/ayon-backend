import enum
import time

from openpype.types import Field, OPModel


class StatusEnum(enum.IntEnum):
    """
    -1 : State is not available
    0 : Transfer in progress
    1 : File is queued for Transfer
    2 : Transfer failed
    3 : Tranfer is paused
    4 : File/representation is fully synchronized
    """

    NOT_AVAILABLE = -1
    IN_PROGRESS = 0
    QUEUED = 1
    FAILED = 2
    PAUSED = 3
    SYNCED = 4


class SortByEnum(enum.Enum):
    folder: str = "folder"
    subset: str = "subset"
    version: str = "version"
    representation: str = "representation"
    localStatus: str = "localStatus"
    remoteStatus: str = "remoteStatus"


class SyncStatusModel(OPModel):
    status: StatusEnum = Field(StatusEnum.NOT_AVAILABLE)
    size: int = Field(0)
    totalSize: int = Field(0)
    timestamp: int = Field(default_factory=time.time)
    message: str | None = Field(None)
    retries: int = Field(0)


class SyncStatusPostModel(SyncStatusModel):
    fileHash: str


class FileModel(OPModel):
    fileHash: str
    size: int
    path: str
    baseName: str
    localStatus: SyncStatusModel
    remoteStatus: SyncStatusModel


class SiteSyncSummaryItem(OPModel):
    folder: str = Field(...)
    subset: str = Field(...)
    version: int = Field(...)
    representation: str = Field(...)
    representationId: str = Field(...)
    fileCount: int = Field(...)
    size: int = Field(..., description="Total size of all files")
    localStatus: SyncStatusModel
    remoteStatus: SyncStatusModel

    files: list[FileModel] | None = Field(
        None,
        description="List of individual files. Available in single-representation mode",
    )


class SiteSyncSummaryModel(OPModel):
    representations: list[SiteSyncSummaryItem] = Field(...)


class SiteSyncParamsModel(OPModel):
    count: int
    names: list[str] = Field(default_factory=list)


class RepresentationStateModel(OPModel):
    files: list[SyncStatusPostModel]
    priority: int | None = Field(None)
