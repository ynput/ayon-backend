from demogen.namegen import namegen


async def gen_shots(parent):
    num = parent.get("_children_count", 20)
    padding = parent.get("_padding", 2)
    for i in range(1, num):
        yield {
            "name": f"{parent.get('_sequence', '')}sh{i:0{padding}d}0",
            "folder_type": "Shot",
            "_products": parent.get("_leaf_products", []),
            "_tasks": parent.get("_leaf_tasks", []),
        }


async def gen_sequences(parent):
    for i in range(1, 10):
        seq_name = f"{parent.get('_episode', '')}sq{i:03d}"
        yield {
            "name": seq_name,
            "folder_type": "Sequence",
            "_sequence": seq_name,
            "_leaf_products": parent.get("_leaf_products", []),
            "_leaf_tasks": parent.get("_leaf_tasks", []),
            "_children": "gen_shots",
        }


async def gen_episodes(parent):
    num = parent.get("_children_count", 10)
    for i in range(101, 101 + num):
        ep_name = f"ep{i:03d}"
        yield {
            "name": ep_name,
            "folder_type": "Episode",
            "_episode": ep_name,
            "_leaf_products": parent.get("_leaf_products", []),
            "_leaf_tasks": parent.get("_leaf_tasks", []),
            "_children": "gen_sequences",
        }


async def gen_assets(parent):
    """Return a list of asset folders.

    This is for testing/demo purposes only.
    using parent variables, the following parameters can be set:
        - _children_count: number of children to generate
        - _children_naming: naming scheme to use for children
        - _combine: number of strings joined into a single name
    """
    num = parent.get("_children_count", 20)
    combine = int(parent.get("_combine", 2))
    names = ["_".join(namegen.generate_words(combine, 2)) for _ in range(num)]

    for i, name in enumerate(names):
        name_slug = f"{i:02d}_{name}"  # + slugify(name, separator="_")
        label = f"{i:02d} {name.replace('_', ' ').title()}"
        yield {
            "name": name_slug,
            "label": label,
            "folder_type": "Asset",
            "_version_count": 5,
            "_products": parent.get("_leaf_products", []),
            "_tasks": parent.get("_leaf_tasks", []),
        }


generators = {
    "gen_episodes": gen_episodes,
    "gen_assets": gen_assets,
    "gen_sequences": gen_sequences,
    "gen_shots": gen_shots,
}
