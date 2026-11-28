"""Regression checks for the six French events, diplomacy slots, citizen tips and endings."""
import json
import os
from pathlib import Path
import re
import unittest

import audit_text

HERE = Path(__file__).resolve().parent
RESOURCES = json.loads((HERE / "resources.zh-CN.json").read_bytes())
SLOTS = ((1664, 1672), (1672, 1680), (1680, 1686), (1686, 1698), (1698, 1702), (1702, 1710))


class ChineseTexts(unittest.TestCase):
    def test_french_events_have_all_six_titles_bodies_and_results(self):
        rows = RESOURCES["Events_text_en"]
        titles = []
        for start, stop in SLOTS:
            texts = [rows[str(i)] for i in range(start, stop)]
            self.assertTrue(all(re.search(r"[\u3400-\u9fff]", row) for row in texts))
            self.assertGreater(len(texts[1]), 90)
            self.assertGreater(len(texts[-1]), 30)
            titles.append(texts[0])
        self.assertEqual(len(set(titles)), len(SLOTS))
        self.assertIn("雷蒙·巴尔", rows["1669"])
        self.assertIn("98.5%", rows["1685"])

    def test_diplomacy_arguments_and_alliance_conditions(self):
        rows = RESOURCES["other_text_en"]
        self.assertEqual(rows["486"].format(">", "69"), "外交声望 >69")
        self.assertEqual(rows["487"].format(">", "39", "<", "80"), "外交声望须同时满足 >39 和 <80")
        self.assertEqual(rows["492"].format("20"), "军力至少达到 20")
        self.assertEqual([n for n in range(486, 564) if str(n) not in rows], [495])
        self.assertIn("集体安全联盟", rows["560"])
        self.assertIn("利比亚与乍得", rows["563"])
        self.assertIn("至少", rows["331"])
        self.assertIn("西德", rows["338"])
        self.assertIn("预算和储备", rows["469"])

    def test_economy_highlights_match_translated_sections_in_order(self):
        plan = json.loads((HERE / "assembly-plan.json").read_bytes())
        by_site = {site: txt for _, txt, sites in plan["records"] for site in sites}
        headings = [by_site["1553:" + str(n)] for n in (41, 57, 73)]
        disabled = next(txt for token, txt, _ in plan["records"] if token == 449975)
        headings.append(disabled)
        row = RESOURCES["old_modify_opis_en"]["59"]
        self.assertEqual([pos for pos, section in enumerate(row.split("|")) if section in headings],
                         [0, 5, 9, 13])
        self.assertEqual([section for section in row.split("|") if section in headings], headings)
        self.assertIn("七分功绩、三分过失", by_site["1913:4690"])
        self.assertEqual(by_site["1658:73950"], "泛阿拉伯主义")

    def test_endings_and_citizen_buttons(self):
        plan = json.loads((HERE / "assembly-plan.json").read_bytes())
        records = {tok: (txt, sites) for tok, txt, sites in plan["records"]}
        for token, site in [(340927, "1244:766"), (382788, "1244:2133")]:
            txt, sites = records[token]
            self.assertGreater(len(txt), 200)
            self.assertRegex(txt, "中国|中国共产党")
            self.assertEqual(sites, [site])
        with (HERE / "scenes.zh-CN.json").open(encoding="utf8") as f:
            rows = {obj: txt for obj, offset, txt in json.load(f)["level25"] if obj != 1041}
        for group, cue in [((895, 1016, 1044), "拨款"), ((909, 938, 961), "特赦"), ((942, 1064, 1067), "政治追查")]:
            for obj in group:
                self.assertIn(cue, rows[obj])
        self.assertIn("姓和名", rows[920])


@unittest.skipUnless(os.getenv("MAO_TEST_ORIGINAL") and os.getenv("MAO_TEST_STAGE"),
                     "set MAO_TEST_ORIGINAL and MAO_TEST_STAGE to read real game data")
class BuiltResources(unittest.TestCase):
    def test_read_french_slots_and_preserve_every_russian_resource(self):
        original = audit_text.texts(Path(os.environ["MAO_TEST_ORIGINAL"]))[0]
        actual = audit_text.texts(Path(os.environ["MAO_TEST_STAGE"]))[0]
        for key, raw in original.items():
            if key.endswith("_ru"):
                self.assertEqual(actual[key], raw, key)
        self.assertEqual(len(original["Events_text_en"].splitlines()), 1664)
        self.assertEqual(len(actual["Events_text_en"].splitlines()), 1710)
        for name, indices in (("Events_text_en", range(1664, 1710)), ("other_text_en", range(486, 564))):
            rows = actual[name].splitlines()
            for i in indices:
                if name == "other_text_en" and i == 495:
                    self.assertEqual(rows[i], "")
                else:
                    self.assertEqual(rows[i], RESOURCES[name][str(i)], (name, i))

    def test_actual_assembly_indices_in_english_and_russian_branches(self):
        import dnfile
        from dncil.cil.body.reader import read_method_body_from_bytes

        def field_indices(folder, owner, name, field):
            pe = dnfile.dnPE(str(folder / "Managed/Assembly-CSharp.dll"))
            try:
                cls = next(c for c in pe.net.mdtables.TypeDef if str(c.TypeName) == owner)
                methods = [m.row for m in cls.MethodList if name is None or str(m.row.Name) == name]
                out = []
                for method in methods:
                    if not method.Rva:
                        continue
                    ops = read_method_body_from_bytes(pe.get_data(method.Rva)).instructions
                    for a, b, c in zip(ops, ops[1:], ops[2:]):
                        if a.opcode.name != "ldfld" or b.opcode.name != "ldc.i4" or c.opcode.name != "ldelem.ref":
                            continue
                        token = a.operand.value
                        row = pe.net.mdtables.tables[token >> 24].rows[(token & 0xffffff) - 1]
                        if str(row.Name) == field:
                            out.append(b.operand)
                return out
            finally:
                pe.close()

        stock = Path(os.environ["MAO_TEST_ORIGINAL"])
        local = Path(os.environ["MAO_TEST_STAGE"])
        original = field_indices(stock, "DiploButtonScript", "ChineseInfo", "other_text")
        translated = field_indices(local, "DiploButtonScript", "ChineseInfo", "other_text")
        self.assertEqual(translated, [v + 74 if 486 <= v <= 489 else v for v in original])
        self.assertEqual(sum(a != b for a, b in zip(original, translated)), 7)
        for scene, (start, stop) in enumerate(SLOTS, 437):
            indices = field_indices(local, "Event" + str(scene), None, "new_events_text")
            self.assertEqual({n for n in indices if n >= 1664}, set(range(start, stop)))


if __name__ == "__main__":
    unittest.main()
