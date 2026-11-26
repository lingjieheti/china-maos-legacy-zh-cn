"""Regression checks for the citizen creation screen and ending reports."""
import json
import os
import re
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch as mock_patch

import build


class CitizenText(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "uses the Windows file lock")
    def test_source_dependency_handoff_releases_game_lock(self):
        import patch

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "game" / "China_Data"
            cache = root / "cache"
            interpreter = cache / "python-venv" / "Scripts" / "python.exe"
            args = ["patch.py", "install", "--game-dir", str(data), "--cache", str(cache)]
            with mock_patch.object(patch.sys, "argv", args), \
                    mock_patch.object(patch, "game_data", return_value=data), \
                    mock_patch.object(patch, "running", return_value=False), \
                    mock_patch.object(patch, "revision", return_value="new"), \
                    mock_patch.object(patch, "ensure_dependencies", return_value=interpreter), \
                    mock_patch.object(patch.subprocess, "call") as child:
                self.assertEqual(patch.main(), interpreter)
                child.assert_not_called()
            with patch.locked(data.parent / ".nostalgames-zh-cn"):
                pass

    def test_reports_share_display_labels_and_keep_scoped_jobs(self):
        plan = json.loads((build.HERE / "assembly-plan.json").read_bytes())
        rows = {key: (label, sites) for key, label, sites in plan["records"]}
        for key, text, offset in ((303, "公民档案", 10), (391, "当前职业：", 34),
                                  (553, "主要特质：", 110), (657, "出生日期：", 137)):
            self.assertEqual(rows[key], (text, [f"{method}:{offset}" for method in (7, 14, 21)]))
        self.assertEqual(rows[1271], ("工人", ["7:368", "14:368", "21:368", "1171:57"]))
        self.assertEqual(rows[331191], ("人民起义", ["1244:42"]))
        self.assertEqual(rows[333260], ("种族灭绝", ["1244:239"]))
        empty, sites = rows[293]
        self.assertEqual(empty, "无")
        self.assertEqual(len(sites), 21)
        self.assertEqual(len(set(sites)), len(sites))

    def test_citizen_controls_and_twelve_jobs(self):
        data = json.loads((build.HERE / "scenes.zh-CN.json").read_bytes())
        rows = {offset: text for obj, offset, text in data["level25"] if obj == 1041}
        self.assertEqual(len(rows), 50)
        self.assertEqual([rows[offset] for offset in [72, 212, 168, 188, 504, 532]],
                         ["名", "姓", "请输入名…", "请输入姓…", "公民追踪", "政治立场"])
        self.assertEqual([text for offset, text in sorted(rows.items()) if offset >= 1960],
                         ["失业者", "工人", "农民", "农场主", "小企业主", "公司老板", "服刑人员",
                          "获赦人员", "地下工作者", "地方党支部书记", "地区党支部书记", "重要党员"])

    @unittest.skipUnless(os.getenv("MAO_TEST_GAME") and os.getenv("MAO_TEST_ORIGINAL"),
                         "set MAO_TEST_GAME and MAO_TEST_ORIGINAL to compare built assets")
    def test_preserve_russian_columns_references_and_flags(self):
        import UnityPy
        from steam_paths import game_data

        def components(folder):
            file = UnityPy.load((folder / "level25").read_bytes()).file
            buf = file.objects[1041].get_raw_data()
            pos = 32
            sections = {}
            for field in ("labels", "russian", "text_meshes", "jobs", "russian_jobs"):
                count, = struct.unpack_from("<i", buf, pos)
                pos += 4
                if field == "text_meshes":
                    sections[field] = buf[pos:pos + count * 12]
                    pos += count * 12
                    continue
                values = []
                for _ in range(count):
                    text, span = build.read_unity_string(buf, pos)
                    values.append(text)
                    pos += span
                sections[field] = values
            sections["flags"] = buf[pos:]
            return sections

        old = components(Path(os.environ["MAO_TEST_ORIGINAL"]))
        new = components(game_data(Path(os.environ["MAO_TEST_GAME"])))
        for field in ("russian", "text_meshes", "russian_jobs", "flags"):
            self.assertEqual(new[field], old[field], field)
        for field, size in (("labels", 42), ("jobs", 12)):
            self.assertEqual(len(new[field]), size)
            self.assertEqual([bool(t) for t in new[field]], [bool(t) for t in old[field]])
            for text in filter(bool, new[field]):
                self.assertRegex(text, r"[\u3400-\u9fff]")
                self.assertIsNone(re.search(r"[A-Za-zА-Яа-я]", text))


if __name__ == "__main__":
    unittest.main()
