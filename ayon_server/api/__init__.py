from nxtools import logging

# The following functions fix the deprecated import method
# in SiteSync addon 1.0.2 and below. That fixes crashes of
# SiteSync in Ayon 1.4.0
#
# They have been added in 1.4.1 and should be removed in 1.5.0


async def dep_current_user(*args, **kwargs):
    from .dependencies import dep_current_user

    logging.warning("Using deprecated dep_current_user")
    return await dep_current_user(*args, **kwargs)


async def dep_project_name(*args, **kwargs):
    from .dependencies import dep_project_name

    logging.warning("Using deprecated dep_project_name")
    return await dep_project_name(*args, **kwargs)


async def dep_representation_id(*args, **kwargs):
    from .dependencies import dep_representation_id

    logging.warning("Using deprecated dep_representation_id")
    return await dep_representation_id(*args, **kwargs)
