"""Inventory the stock text sources without copying game text into the report."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re

from audit_text import TABLES, texts


def managed_counts(path):
    import dnfile
    from dncil.cil.body.reader import read_method_body_from_bytes

    image = dnfile.dnPE(str(path))
    counts = Counter()
    try:
        for method in image.net.mdtables.MethodDef:
            if not method.Rva:
                continue
            instructions = read_method_body_from_bytes(image.get_data(method.Rva)).instructions
            loads = sum(op.opcode.name == "ldstr" for op in instructions)
            counts["methods_with_string_literals"] += bool(loads)
            counts["string_literal_uses"] += loads
    finally:
        image.close()
    return dict(counts)


def inventory(game_data, original):
    import UnityPy

    files = sorted(p.name for p in game_data.iterdir()
                   if re.fullmatch(r"(?:resources|globalgamemanagers|sharedassets\d+)\.assets|level\d+", p.name))
    types = Counter()
    meshes = 0
    for name in files:
        path = original / name
        if not path.is_file():
            path = game_data / name
        assets = UnityPy.load(path.read_bytes()).file
        types.update(obj.type.name for obj in assets.objects.values())
        meshes += sum(bool(obj.read().m_Text) for obj in assets.objects.values() if obj.type.name == "TextMesh")
    table, digest = texts(original)
    return {"containers": len(files), "scenes": sum(name.startswith("level") for name in files),
            "types": dict(sorted(types.items())), "nonempty_text_meshes": meshes,
            "stock_resources_sha256": digest, "gameplay_assembly": managed_counts(original / "Managed/Assembly-CSharp.dll"),
            "language_tables": {n: {suffix: len(table.get(n + "_" + suffix, "").splitlines())
                                   for suffix in ("en", "ru")} for n in TABLES}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-data", required=True, type=Path, help="complete Steam China_Data directory")
    parser.add_argument("--original", required=True, type=Path, help="verified stock resources or the installer's original backup")
    parser.add_argument("--json", type=Path, help="optional inventory report")
    args = parser.parse_args()
    result = inventory(args.game_data, args.original)
    if args.json:
        args.json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", "utf8")
    print(f"{result['containers']} containers, {result['scenes']} scenes, "
          f"{result['types']['TextAsset']} TextAssets, {result['types']['Texture2D']} textures, "
          f"{result['nonempty_text_meshes']} nonempty TextMesh objects, "
          f"{result['gameplay_assembly']['string_literal_uses']} managed string uses")
