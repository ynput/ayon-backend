from ayon_server.types import Field, OPModel, ProjectLevelEntityType

EXAMPLE_URI = "ayon+entity://myproject/assets/env/beach?product=layout&version=v004"


class ResolveRequestModel(OPModel):
    resolve_roots: bool = Field(
        False,
        title="Resolve roots",
        description="If x-ayon-site-id header is provided, "
        "resolve representation path roots",
    )
    uris: list[str] = Field(
        ...,
        title="URIs",
        description="List of uris to resolve",
        example=[EXAMPLE_URI],
    )


class ResolvedEntityModel(OPModel):
    project_name: str | None = Field(
        None,
        title="Project name",
        example="demo_Big_Feature",
    )
    folder_id: str | None = Field(
        None,
        title="Folder id",
        example="0254c370005811ee9a740242ac130004",
    )
    product_id: str | None = Field(
        None,
        title="Product id",
        example="0255ce50005811ee9a740242ac130004",
    )
    task_id: str | None = Field(
        None,
        title="Task id",
        example=None,
    )
    version_id: str | None = Field(
        None,
        title="Version id",
        example="0256ba2c005811ee9a740242ac130004",
    )
    representation_id: str | None = Field(
        None,
        title="Representation id",
        example=None,
    )
    workfile_id: str | None = Field(
        None,
        title="Workfile id",
        example=None,
    )
    file_path: str | None = Field(
        None,
        title="File path",
        description="Path to the file if a representation is specified",
        example="/path/to/file.ma",
    )
    target: ProjectLevelEntityType | None = Field(
        None,
        title="Target entity type",
        description="The deepest entity type queried",
    )


class ResolvedURIModel(OPModel):
    uri: str = Field(
        ...,
        title="Resolved URI",
        example="ayon+entity://demo_Big_Feature/assets/environments/01_pfueghtiaoft?product=layoutMain&version=v004&representation=ma",
    )
    entities: list[ResolvedEntityModel] = Field(
        default_factory=list,
        title="Resolved entities",
        example=[
            {
                "projectName": "demo_Big_Feature",
                "folderId": "0254c370005811ee9a740242ac130004",
                "productId": "0255ce50005811ee9a740242ac130004",
                "taskId": None,
                "versionId": "0256ba2c005811ee9a740242ac130004",
                "representationId": None,
                "workfileId": None,
                "filePath": "/path/to/file.ma",
            }
        ],
    )
    error: str | None = Field(
        None,
        title="Error",
        description="Error message if the URI could not be resolved",
    )


class ParsedURIModel(OPModel):
    uri: str = Field(..., title="Resolved URI")
    project_name: str = Field(..., title="Project name")
    path: str | None = Field(None, title="Path")
    product_name: str | None = Field(None, title="Product name")
    task_name: str | None = Field(None, title="Task name")
    version_name: str | None = Field(None, title="Version name")
    representation_name: str | None = Field(None, title="Representation name")
    workfile_name: str | None = Field(None, title="Workfile name")
