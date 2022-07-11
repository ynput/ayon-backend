import copy
import time

from nxtools import logging
from pydantic import BaseModel


def apply_patch(original: BaseModel, patch: BaseModel) -> BaseModel:
    """Patch (partial update) an entity using its patch model."""
    update_data = {}

    for key, value in patch.dict(exclude_unset=True).items():
        if key not in original.__fields__:
            continue

        if isinstance(getattr(original, key), BaseModel):
            # Patch a submodel (attrib)
            ndata = apply_patch(
                getattr(original, key), getattr(original, key).__class__(**value),
            )
            update_data[key] = ndata

        elif type(getattr(original, key)) == dict:
            # Patch arbitrary dict (one level only!)
            if type(value) == dict:
                new_dict = copy.deepcopy(getattr(original, key))
                for dkey, dval in value.items():
                    if dval is None:
                        if dkey in new_dict:
                            del new_dict[dkey]
                    else:
                        new_dict[dkey] = dval
                update_data[key] = new_dict
            else:
                logging.error(f"Unable to patch. {key} only accepts dict")

        else:
            # Patch scalar types such as ints, strings and booleans
            update_data[key] = value

    if "updated_at" in original.__fields__:
        update_data["updated_at"] = int(time.time())

    updated_model = original.copy(update=update_data, deep=True)
    return updated_model
