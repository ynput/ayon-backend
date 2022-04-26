from fastapi import APIRouter, Response

from openpype.types import OPModel, Field
from anatomy.anatomy import AnatomyTemplate

router = APIRouter(tags=["Anatomy"], prefix="/anatomy")


@router.get("/schema")
def get_anatomy_schema():
    """Returns the anatomy JSON schema.

    The schema is used to display the anatomy template editor form.
    """
    return AnatomyTemplate.schema()


@router.get("/templates")
def get_anatomy_templates() -> list[str]:
    """Return a list of stored anatomy templates."""
    return []


@router.get(
    "/templates/{template_name}",
    response_model=AnatomyTemplate,
)
def get_anatomy_template(template_name: str):
    """Returns the anatomy template with the given name.

    Use `_` character as a template name to return the default template.
    """
    tpl = AnatomyTemplate()
    return tpl.dict()


@router.put("/template/{template_name}")
def update_anatomy_template(template_name: str, template: AnatomyTemplate):
    """Create/update an anatomy template with the given name."""
    return Response(status_code=501)


@router.delete("/template/{template_name}")
def delete_anatomy_template(template_name: str):
    """Delete the anatomy template with the given name."""
    return Response(status_code=501)


class DeployRequestModel(OPModel):
    """The request model for the deploy endpoint."""

    project_name: str = Field(
        ...,
        description="The name of the project to deploy to.",
        example="superProject42",
    )
    template: AnatomyTemplate = Field(
        ...,
        description="The anatomy template to deploy.",
    )


@router.post("/deploy")
def deploy_anatomy_template(template: AnatomyTemplate):
    """Deploy the anatomy template.

    Create a new project from the anatomy template.
    """
    return Response(status_code=501)
