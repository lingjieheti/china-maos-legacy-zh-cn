"""Validate the distributable patch files without Steam, network access, or third-party modules."""
import bz2
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
import runpy
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
GAMES = ROOT / "games"
sys.dont_write_bytecode = True


def require(value, message):
    if not value:
        raise ValueError(message)

def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, f"{path.name}: duplicate key {key}")
            result[key] = value
        return result
    return json.loads(path.read_text("utf-8-sig"), object_pairs_hook=unique)

def text_line(value):
    require(isinstance(value, str) and value.strip(), f"Empty or invalid text: {value!r}")
    require("\ufffd" not in value and "\0" not in value, "Text contains an invalid character")
    return value

def check_mao(chars):
    folder = GAMES / "mao"
    manifest = read_json(folder / "manifest.json")
    require(re.fullmatch(r"[0-9a-f]{40}", manifest["commit"]), "Unpinned Mao community base")
    require(str(manifest["version"]).isdigit(), "Invalid Mao game build")
    for group in ("upstream", "originals"):
        paths = manifest[group]
        require(paths, f"No fingerprints in Mao {group}")
        for name, sha in paths.items():
            path = PureWindowsPath(name)
            require(not path.anchor and ".." not in path.parts, f"Unsafe asset path {name}")
            require(re.fullmatch(r"[0-9a-f]{64}", sha), f"Invalid fingerprint for {name}")
    resources = read_json(folder / "resources.zh-CN.json")
    french_groups = {"polit_surnames21_en", "polit_names21_en", "Traits21_en", "Part21_en"}
    require(french_groups <= resources.keys(), "French scenario resources are missing")
    require(len(resources["Traits21_en"]) >= 25, "The French scenario has lost trait descriptions")
    party_names = resources["Part21_en"]["0"].split(";")
    require(party_names[0] == "21" and len(party_names) >= 16 and all(party_names),
            "The French scenario needs its index and the full party list")
    total = 0
    for entries in resources.values():
        for key, text in entries.items():
            require(key.isascii() and key.isdecimal(), f"Invalid resource index {key}")
            chars.update(text_line(text))
            total += 1
    require(total >= 406, "Mao resource overrides are incomplete")
    scenes = read_json(folder / "scenes.zh-CN.json")
    scene_entries = 0
    for scene, entries in scenes.items():
        require(scene in manifest["originals"], f"Missing original fingerprint for {scene}")
        positions = set()
        for obj, offset, value in entries:
            require(obj > 0 and offset >= 0 and (obj, offset) not in positions, f"Invalid scene entry in {scene}")
            positions.add((obj, offset))
            chars.update(text_line(value))
        scene_entries += len(positions)
    require(scene_entries >= 520, "Mao scene text is incomplete")
    plan = read_json(folder / "assembly-plan.json")
    require(isinstance(plan["heap_offset"], int) and plan["heap_offset"] > 0, "Invalid string heap position")
    positions = set()
    for offset, value, overrides in plan["records"]:
        require(isinstance(offset, int) and offset >= 0 and offset not in positions, "Invalid string heap key")
        positions.add(offset)
        chars.update(text_line(value))
        require(all(re.fullmatch(r"\d+:\d+", loc) for loc in overrides), "Invalid managed string use")
    require(len(positions) >= 2209, "Mao managed string plan is incomplete")
    print(f"Mao: {total} resource entries, {scene_entries} scene entries, {len(positions)} managed string entries")

def font_coverage_and_spaces(data):
    require(data[:4] == b"\x00\x01\x00\x00", "Expected a TrueType font")
    count = struct.unpack_from(">H", data, 4)[0]
    tables = {}
    for i in range(count):
        name, _, pos, size = struct.unpack_from(">4sIII", data, 12 + 16 * i)
        require(name not in tables and pos + size <= len(data), "Invalid sfnt table directory")
        tables[name] = data[pos:pos+size]
    require({b"head", b"glyf", b"loca", b"cmap", b"hmtx", b"name"} <= tables.keys(), "Missing TrueType tables")
    cmap = tables[b"cmap"]
    records = struct.unpack_from(">H", cmap, 2)[0]
    available = set()
    space_glyphs = {}
    for platform, encoding, pos in struct.iter_unpack(">HHI", cmap[4:4+8*records]):
        if not (platform == 0 or (platform, encoding) == (3, 10)):
            continue
        if struct.unpack_from(">H", cmap, pos)[0] != 12:
            continue
        _, _, length, _, groups = struct.unpack_from(">HHIII", cmap, pos)
        require(length == 16 + 12 * groups and pos + length <= len(cmap), "Malformed Unicode cmap")
        for start, end, glyph in struct.iter_unpack(">III", cmap[pos+16:pos+length]):
            require(start <= end <= 0x10ffff, "Invalid Unicode group")
            available.update(range(start + int(glyph == 0), end + 1))
            for cp in (0x20, 0x200a):
                if start <= cp <= end:
                    space_glyphs[cp] = glyph + cp - start
    require(available and 0x20 in space_glyphs, "Incomplete character map or missing ASCII space")
    long_metrics = struct.unpack_from(">H", tables[b"hhea"], 34)[0]
    require(long_metrics > 0, "Missing horizontal font metrics")
    advances = {cp: struct.unpack_from(">H", tables[b"hmtx"], 4 * min(gid, long_metrics - 1))[0]
                for cp, gid in space_glyphs.items()}
    return available, advances

def check_revised_text():
    data = read_json(GAMES / "mao/resources.zh-CN.json")["new_texts_en"]
    require("华沙条约组织" in data["161"] and "经济互助委员会" in data["162"],
            "Military and economic membership conditions have been conflated")
    require(all(data[k].count("{0}") == 1 for k in ("893", "894")), "Withdrawal line-break placeholders lost")
    require("直接" in data["893"] and "秘密" in data["894"] and "增加5" in data["894"],
            "Direct and secret withdrawal rules must remain distinct")


def main():
    check_revised_text()
    for path in ROOT.rglob("*.py"):
        if ".git" not in path.parts:
            compile(path.read_bytes(), str(path.relative_to(ROOT)), "exec")
    chars = set()
    check_mao(chars)

    needed = {ord(c) for c in chars if 0x3400 <= ord(c) <= 0x9fff}
    for weight, sha in {
        "Regular":"4ee547aaae1f3b04404fffe295ceaf0bec2271b0abde2d8e47e36f24111f650b",
        "Semibold":"5a8ee249f37abd104dac21c4c6fda1edbcda13650eff64466a436cd300d162c6",
    }.items():
        data = (ROOT / "fonts" / f"UI-{weight}.ttf").read_bytes()
        require(hashlib.sha256(data).hexdigest() == sha, "Font checksum mismatch")
        points, _ = font_coverage_and_spaces(data)
        require(needed <= points, f"Missing glyphs in {weight}: {needed - points}")

    for path in ("manage.py", "games/mao/patch.py"):
        proc = subprocess.run([sys.executable, "-B", "-X", "utf8", str(ROOT / path), "--help"],
                              capture_output=True, encoding="utf-8", timeout=30)
        require(proc.returncode == 0 and "install" in proc.stdout and "restore" in proc.stdout,
                f"Player entry point failed: {path}")
    print("Release files and both player entry points passed.")

if __name__ == "__main__":
    main()
