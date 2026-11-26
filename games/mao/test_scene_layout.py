"""Scene geometry and the Chinese formatter used by the five Unity entry points."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


def run_formatter_test(harness):
    csc = Path(os.environ['WINDIR']) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    if not csc.is_file():
        csc = Path(os.environ['WINDIR']) / 'Microsoft.NET/Framework/v4.0.30319/csc.exe'
    with tempfile.TemporaryDirectory() as folder:
        work = Path(folder)
        (work / 'Check.cs').write_text(harness, encoding='utf-8-sig')
        binary = work / 'Check.exe'
        subprocess.run([str(csc), '/nologo', '/utf8output', '/out:' + str(binary),
                        str(HERE / 'ChineseLayout.cs'), str(work / 'Check.cs')], check=True)
        subprocess.run([str(binary)], check=True)


class SceneLayout(unittest.TestCase):
    def test_personnel_actions_fit_on_one_line(self):
        rows = json.loads((HERE / 'scenes.zh-CN.json').read_text('utf8'))['level14']
        actions = {offset: value for obj, offset, value in rows if obj == 2245}
        for offset in (60, 84, 124, 148, 172, 200, 228, 252, 276, 300, 324):
            label = actions[offset]
            self.assertTrue(label and all('\u3400' <= c <= '\u9fff' for c in label))
            # The narrowest of these buttons has room for 1.60 world units.
            self.assertLess(len(label) * 2.7 * .078 * .97, 1.60 - .20)

    @unittest.skipUnless(os.name == 'nt', 'the shipped formatter is compiled with Windows .NET Framework')
    def test_compiled_formatter(self):
        harness = r'''
using System;
using Nostalgames.ZhCN;
class Check {
    static void Require(bool value) { if (!value) throw new Exception("layout regression"); }
    static void Main() {
        string sample = "收入 +0.6，情报人员 +0.2，|军力 +0.5|" +
            "<color=#DC143C>毛泽东逝世后：</color>民众支持度 +0.5，思想自由化 +1.0。";
        int col = 25;
        string result = ChineseLayout.PrepareInt(sample, ref col);
        Require(col == Int32.MaxValue && result.Contains("<color=#DC143C>") && result.Contains("</color>"));
        Require(result.Replace("|","").Replace(" ","") == sample.Replace("|","").Replace(" ",""));
        float width = 25;
        Require(ChineseLayout.PrepareFloat(sample, ref width) == result && width == Single.MaxValue);
        col = 12;
        result = ChineseLayout.PrepareInt("他说：“美国 GDP 为−10.5%。”\r\n制度A|{1:F1}。", ref col);
        Require(result.Contains("−10.5%") && result.Contains("{1:F1}"));
        foreach (string line in result.Split('|')) {
            Require(line.Length > 0 && "。，：）”".IndexOf(line[0]) < 0);
            Require("（“".IndexOf(line[line.Length-1]) < 0);
        }
        col = 18;
        Require(ChineseLayout.PrepareInt("原文 { 与 }\r\n\r\n下一段", ref col).Contains("||"));
        col = 20;
        Require(ChineseLayout.PrepareInt("English / Русский", ref col) == "English / Русский" && col == 20);
        col = 3;
        Require(ChineseLayout.PrepareInt("短行", ref col) == "短行" && col == 3);
    }
}'''
        run_formatter_test(harness)

    @unittest.skipUnless(os.name == 'nt', 'the shipped formatter is compiled with Windows .NET Framework')
    def test_trade_penalty_magnitude(self):
        run_formatter_test(r'''
using System;
using Nostalgames.ZhCN;
class Check {
    static void Verify(int difference, int divisor, string expected) {
        string[] parts = {"前一行", "\n两周变化：−", (difference / divisor).ToString(), ".",
                          Math.Abs(difference / (divisor / 10) % 10).ToString()};
        if (ChineseLayout.FormatTradePenalty(parts) != "前一行\n两周变化：" + expected)
            throw new Exception(difference + " / " + divisor);
    }
    static void Main() {
        Verify(-45, 20, "−2.2");
        Verify(-45, 30, "−1.5");
        Verify(-45, 40, "−1.1");
        Verify(-4, 20, "−0.2");
        Verify(-1, 20, "0.0");
        Verify(0, 20, "0.0");
        Verify(-10, 10, "−1.0");
        Verify(-1, 10, "−0.1");
    }
}''')

    @unittest.skipUnless(os.environ.get('MAO_LAYOUT_STAGE'), 'set MAO_LAYOUT_STAGE to read built Unity scenes')
    def test_built_event_title_and_action_array(self):
        import UnityPy
        from build import read_unity_string
        stage = Path(os.environ['MAO_LAYOUT_STAGE'])
        event = UnityPy.load((stage / 'level11').read_bytes()).file.objects
        self.assertEqual(event[359].read().m_GameObject.m_PathID, 36)
        self.assertAlmostEqual(event[359].read().m_CharacterSize, .074)
        self.assertAlmostEqual(event[359].read().m_LineSpacing, .78)
        self.assertAlmostEqual(event[160].read().m_LocalPosition.y, 4.484, places=5)
        self.assertAlmostEqual(event[130].read().m_LocalPosition.y, 3.72, places=5)
        save = UnityPy.load((stage / 'level12').read_bytes()).file.objects
        load = UnityPy.load((stage / 'level13').read_bytes()).file.objects
        self.assertAlmostEqual(save[21].read().m_LocalPosition.y, load[31].read().m_LocalPosition.y, places=5)
        raw = UnityPy.load((stage / 'level14').read_bytes()).file.objects[2245].get_raw_data()
        pos = 36
        labels = []
        for _ in range(17):
            word, size = read_unity_string(raw, pos)
            labels.append(word)
            pos += size
        self.assertEqual(labels[5:8], ['调入中央军委', '调任外交部', '任命为总理'])
        self.assertFalse(any('|' in word for word in labels))


if __name__ == '__main__':
    unittest.main()
