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
        self.stock = {"level5": b"original settings", "sharedassets1.assets": b"original artwork"}
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
        initial = {name: patch.digest(self.data / name) for name in ("level5", patch.HELPER)}
        manager.write_state({"game": str(self.data), "patched": initial}, self.backup / "installed.json")
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
