import json
from pathlib import Path
import unittest

import build


class EventLabels(unittest.TestCase):
    def test_costs_keep_fields_signs_and_values(self):
        label = "在 1976-1980 年提供援助（{0}: - 10.0, {2}: + 5.0）"
        self.assertEqual(build.polish_resource("Events_text_en", 0, label),
                         "在 1976-1980 年提供援助（{0}：−10.0，{2}：+5.0）")
        self.assertEqual(build.polish_resource("other_text_en", 0, label), label)

    def test_logical_conditions(self):
        data = json.loads(Path(__file__).with_name("resources.zh-CN.json").read_bytes())
        self.assertIn("或", data["Events_text_en"]["925"])
        self.assertIn("或", data["other_text_en"]["70"])
        self.assertIn("再加上苏联的影响力", data["new_texts_en"]["331"])

    def test_save_status_contrast_on_the_game_panel(self):
        plan = json.loads(Path(__file__).with_name("assembly-plan.json").read_bytes())
        labels = {token: label for token, label, _ in plan["records"]}
        def luminance(rgb):
            channels = [int(rgb[i:i+2], 16)/255 for i in (0, 2, 4)]
            linear = [c/12.92 if c <= .04045 else ((c+.055)/1.055)**2.4 for c in channels]
            return sum(c*w for c,w in zip(linear,(.2126,.7152,.0722)))
        for token, meaning in ((448173, "可解锁"), (448287, "不可用")):
            prefix, text = labels[token].split(">", 1)
            self.assertEqual(text, meaning + "</color>")
            self.assertTrue(prefix.startswith("<color=#"))
            ratio = (luminance("E4D8C4")+.05)/(luminance(prefix[-6:])+.05)
            self.assertGreaterEqual(ratio, 4.5)

    def test_overview_uses_one_line_per_trade_effect_and_faction(self):
        plan = json.loads(Path(__file__).with_name("assembly-plan.json").read_bytes())
        labels = {token: (text, sites) for token, text, sites in plan["records"]}
        for token in (1908912, 1908980, 1909056, 1909124, 1909200,
                      1913972, 1914020, 1914064, 1914110, 1914154, 1914194, 1914232):
            text, sites = labels[token]
            self.assertNotIn("\n", text.removeprefix("\n"))
            self.assertTrue(sites and all(site.startswith("1935:") for site in sites))
        self.assertEqual(labels[1908798], ("出口：", ["1935:131", "1935:226"]))
        self.assertEqual(labels[1908888][0], "出口减进口：")

    def test_game_rules_and_party_choices_use_readable_text(self):
        plan = json.loads(Path(__file__).with_name("assembly-plan.json").read_bytes())
        labels = {token: text for token, text, _ in plan["records"]}
        self.assertEqual(labels[4413], "关闭（有成就）")
        self.assertEqual(labels[4589], "双人（无成就）")
        self.assertEqual(labels[1455491], "卡特（民主党）")
        self.assertEqual(labels[1455511], "里根（共和党）")
        self.assertTrue(labels[1529521].startswith("华国锋同志，祝贺你出任"))
        self.assertIn("无从证实", labels[1529521])
        self.assertEqual(labels[1415125], "严格执行，并在报刊上批判周恩来。")


if __name__ == "__main__":
    unittest.main()
