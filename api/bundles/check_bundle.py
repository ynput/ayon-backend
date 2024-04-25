from typing import Literal

from ayon_server.types import Field, OPModel

from .models import BundleModel


class BundleIssueModel(OPModel):
    severity: Literal["error", "warning"] = Field(..., example="error")
    addon: str | None = Field(None, example="ftrack")
    message: str = Field(..., example="FTrack addon requires Core >= 1.0.0")


class CheckBundleResponseModel(OPModel):
    success: bool = False
    issues: list[BundleIssueModel] | None = None


async def check_bundle(bundle: BundleModel) -> CheckBundleResponseModel:
    issues: list[BundleIssueModel] = []

    return CheckBundleResponseModel(
        success=bool(issue for issue in issues if issue.severity == "error"),
        issues=issues or None,
    )
