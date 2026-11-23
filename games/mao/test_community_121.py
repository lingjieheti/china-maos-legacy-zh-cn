"""Run with Python's standard library. Set MAO_TEST_GAME to inspect a patched game's actual button textures."""
import contextlib
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import manage as manager
import patch


class ReceiptChecks(unittest.TestCase):
    def setUp(self):
        self.scope = contextlib.ExitStack()
        self.addCleanup(self.scope.close)
        self.root = Path(self.scope.enter_context(tempfile.TemporaryDirectory()))
        self.data = self.root / "China_Data"
        self.data.mkdir()
        (self.root / "China.exe").touch()
        self.backup = self.root / ".nostalgames-zh-cn/backup"
        self.backup.mkdir(parents=True)
        self.source = self.backup / "original"
        self.source.mkdir()
        self.stock = {"level5": b"original settings", "sharedassets1.assets": b"original artwork",
                      "sharedassets5.assets": b"original settings artwork"}
        originals = {n: hashlib.sha256(v).hexdigest() for n, v in self.stock.items()}
        self.scope.enter_context(mock.patch.dict(patch.MANIFEST, {"originals": originals}))
        self.scope.enter_context(mock.patch.object(manager, "running", return_value=False))
        self.scope.enter_context(mock.patch.object(patch, "locked", lambda _: contextlib.nullcontext()))
        self.scope.enter_context(mock.patch.object(patch, "revision", return_value="current"))
        self.scope.enter_context(contextlib.redirect_stdout(io.StringIO()))
        self.helper = self.data / patch.HELPER
        self.helper.parent.mkdir()
        self.helper.write_bytes(b"helper")
        (self.source / "level5").write_bytes(self.stock["level5"])
        (self.data / "level5").write_bytes(b"old translated scene")
        (self.data / "sharedassets1.assets").write_bytes(self.stock["sharedassets1.assets"])
        (self.data / "sharedassets5.assets").write_bytes(self.stock["sharedassets5.assets"])
        initial = {name: patch.digest(self.data / name) for name in ("level5", patch.HELPER)}
        manager.write_state({"game": str(self.data.resolve()), "patched": initial}, self.backup / "installed.json")
        (self.backup / "recipe.txt").write_text("old", "ascii")

    def verify(self):
        with mock.patch.object(sys, "argv", ["patch.py", "verify", "--game-dir", str(self.root)]):
            patch.main()

    def test_old_verified_files_suggest_upgrade(self):
        with self.assertRaisesRegex(ValueError, "安装汉化.*升级"):
            self.verify()

    def test_old_receipt_with_new_marker_still_needs_upgrade(self):
        (self.backup / "recipe.txt").write_text("current", "ascii")
        with self.assertRaisesRegex(ValueError, "安装汉化.*升级"):
            self.verify()

    def test_damaged_file_takes_precedence_over_upgrade(self):
        (self.data / "level5").write_bytes(b"other patch")
        with self.assertRaisesRegex(ValueError, "游戏文件校验失败：level5"):
            self.verify()

    def test_missing_backup_takes_precedence_over_upgrade(self):
        (self.source / "level5").unlink()
        with self.assertRaisesRegex(ValueError, "备份缺失或损坏：level5"):
            self.verify()

    def test_old_restore_does_not_require_future_artwork_backup(self):
        manager.manage("restore", self.data, self.backup)
        for n, data in self.stock.items():
            self.assertEqual((self.data / n).read_bytes(), data)
        self.assertFalse(self.helper.exists())

    def test_stock_and_new_receipt_after_upgrade(self):
        stage = self.root / "stage"
        (stage / "Managed").mkdir(parents=True)
        names = [*self.stock, patch.HELPER]
        for n in names:
            (stage / n).write_bytes(("new " + n).encode())
        (stage / "sha256.json").write_text(json.dumps({n: patch.digest(stage / n) for n in names}))
        manager.manage("install", self.data, self.backup, stage)
        (self.backup / "recipe.txt").write_text("current", "ascii")
        self.verify()
        self.assertEqual((self.source / "sharedassets1.assets").read_bytes(), self.stock["sharedassets1.assets"])
        manager.manage("restore", self.data, self.backup)
        self.assertFalse(self.helper.exists())
        for n, data in self.stock.items():
            self.assertEqual((self.data / n).read_bytes(), data)


@unittest.skipUnless(os.getenv("MAO_TEST_GAME"), "set MAO_TEST_GAME for the optional game-data readback")
class ArtworkReadback(unittest.TestCase):
    def test_settings_music_titles_use_one_line(self):
        import struct
        import UnityPy
        from build import read_unity_string
        data = patch.game_data(Path(os.environ["MAO_TEST_GAME"]))
        level = UnityPy.load((data / "level5").read_bytes()).file
        raw = level.objects[562].get_raw_data()
        count, = struct.unpack_from("<I", raw, 32)
        self.assertEqual(count, 43)
        english_slot = []
        cursor = 36
        for _ in range(count):
            value, width = read_unity_string(raw, cursor)
            english_slot.append(value)
            cursor += width
        self.assertEqual([english_slot[i] for i in (22, 23, 25, 30, 38)], [
            "献给毛主席", "大海航行靠舵手", "全世界人民热爱毛主席", "毛主席思想永放光芒", "跟着毛主席"])
        for title in english_slot[1:41]:
            self.assertTrue(title)
            self.assertNotRegex(title, r"[|\r\n]")

    def test_visible_settings_controls_follow_their_actual_sprite_links(self):
        import UnityPy
        from PIL import Image, ImageDraw, ImageFont
        data = patch.game_data(Path(os.environ["MAO_TEST_GAME"]))
        level = UnityPy.load((data / "level5").read_bytes()).file
        rel = "sharedassets5.assets"
        patched = UnityPy.load((data / rel).read_bytes()).file
        original = UnityPy.load((data.parent / ".nostalgames-zh-cn/backup/original" / rel).read_bytes()).file
        self.assertEqual({pid for pid, obj in patched.objects.items() if
                          obj.get_raw_data() != original.objects[pid].get_raw_data()}, {29, 37})
        for renderer_id, label, size in ((448, "Русский", 36), (452, "简体中文", 41)):
            renderer = level.objects[renderer_id].read()
            self.assertEqual(level.externals[renderer.m_Sprite.m_FileID-1].path, rel)
            sprite = patched.objects[renderer.m_Sprite.m_PathID].read()
            image = patched.objects[sprite.m_RD.texture.m_PathID].read().image.convert("RGB")
            self.assertEqual(image.size, (224, 136))
            mask = image.split()[0].point(lambda r: 255 if r == 255 else 0)
            bounds = mask.getbbox()
            self.assertIsNotNone(bounds)
            x, y, right, bottom = bounds
            self.assertGreater(min(x, image.width-right, y, image.height-bottom), 20)
            glyphs = Image.new("L", image.size)
            font = ImageFont.truetype(str(patch.HERE.parents[1] / "fonts/UI-Semibold.ttf"), size)
            ImageDraw.Draw(glyphs).text((0, 0), label, font=font, fill=255)
            glyphs = glyphs.point(lambda r: 255 if r == 255 else 0)
            expected = glyphs.crop(glyphs.getbbox())
            actual = mask.crop(bounds)
            self.assertEqual(actual.size, expected.size)
            self.assertLess(sum(a != b for a, b in zip(actual.tobytes(), expected.tobytes())),
                            actual.width * actual.height * .01)

    def test_sprite_targets_word_shapes_and_hover(self):
        import UnityPy
        from PIL import Image, ImageDraw, ImageFont

        data = patch.game_data(Path(os.environ["MAO_TEST_GAME"]))
        rel = "sharedassets1.assets"
        backup = data.parent / ".nostalgames-zh-cn/backup/original" / rel
        original = UnityPy.load(backup.read_bytes()).file
        installed = UnityPy.load((data / rel).read_bytes()).file
        changed = {pid for pid, o in installed.objects.items()
                   if o.get_raw_data() != original.objects[pid].get_raw_data()}
        self.assertEqual(changed, {2, 3, 4, 5})
        font_path = patch.HERE.parents[1] / "fonts/UI-Semibold.ttf"
        for label, normal, hover, size in (("简体中文", 4, 3, 72), ("Русский", 5, 2, 64)):
            font = ImageFont.truetype(str(font_path), size)
            states = []
            for pid in (normal, hover):
                sprite = installed.objects[pid + 6].read()
                self.assertEqual((sprite.m_RD.texture.m_FileID, sprite.m_RD.texture.m_PathID), (0, pid))
                texture = installed.objects[pid].read()
                image = texture.image.convert("RGB")
                # Extract pale title pixels from the decoded texture. Compare their
                # glyph shapes with a separate rendering of the expected word.
                mask = image.convert("RGB").split()[0].point(lambda r: 255 if r == 255 else 0)
                actual = mask.getbbox()
                self.assertIsNotNone(actual)
                x, y, r, b = actual
                self.assertGreater(min(x, image.width-r), 20)
                self.assertGreater(min(y, image.height-b), 40)
                self.assertLessEqual(abs(x - (image.width-r)), 2)
                self.assertLessEqual(abs(y - (image.height-b)), 2)
                expected = Image.new("L", image.size)
                ImageDraw.Draw(expected).text((0, 0), label, fill=255, font=font)
                expected = expected.point(lambda a: 255 if a == 255 else 0)
                # Maximal coverage can differ by one gray level after compositing.
                shape = mask.crop(actual)
                ref = expected.crop(expected.getbbox())
                self.assertEqual(shape.size, ref.size)
                differences = sum(a != b for a, b in zip(shape.tobytes(), ref.tobytes()))
                self.assertLess(differences, shape.width * shape.height * .01)
                states.append(image)
            self.assertNotEqual(states[0].getpixel((20, 20)), states[1].getpixel((20, 20)))


if __name__ == "__main__":
    unittest.main()
