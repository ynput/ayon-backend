from .common import AppGroupWithPython, AppVariantWithPython, ListPerPlatform

maya_default_variants = [
    AppVariantWithPython(
        name="2023",
        label="Maya 2023",
        executables=ListPerPlatform(
            windows=["C:\\Program Files\\Autodesk\\Maya2023\\bin\\maya.exe"],
            darwin=[],
            linux=["/usr/autodesk/maya2023/bin/maya"],
        ),
        environment="{\n  \"MAYA_VERSION\": \"2023\"\n}"
    )
]


maya_defaults = AppGroupWithPython(
    enabled=True,
    label="Maya",
    icon="{}/app_icons/maya.png",
    hostName="maya",
    environment="{}",
    variants=maya_default_variants,
)
