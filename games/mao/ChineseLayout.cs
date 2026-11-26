using System;
using System.Text;
using System.Text.RegularExpressions;

namespace Nostalgames.ZhCN
{
    public static class ChineseLayout
    {
        static readonly Regex Tokens = new Regex(@"</?[A-Za-z#][^<>\r\n]*>|\r\n|[\r\n|]|[+\-−±]?\{[0-9]+[^{}]*\}[%％]?|[+\-−±]?[0-9]+(?:[.,:/-][0-9]+)*[%％]?|[A-Za-z][A-Za-z0-9]*(?:[./-][A-Za-z0-9]+)*|[\uD800-\uDBFF][\uDC00-\uDFFF]|[\s\S]");
        const string Closing = "，。、：；？！）》】」』”’…％,.!?;:%)]";
        const string Opening = "（《【「『“‘([";
        // Width in thousandths of a Latin column (one full-width Han glyph is
        // two columns). Each advance is the larger of the two shipped weights.
        static readonly int[] AsciiWidth = {
            452, 714, 1092, 1160, 1160, 1902, 1446, 622, 734, 734, 990, 1160, 622, 728, 622, 784,
            1160, 1160, 1160, 1160, 1160, 1160, 1160, 1160, 1160, 1160, 622, 622, 1160, 1160, 1160, 1006,
            1980, 1264, 1348, 1302, 1414, 1216, 1152, 1418, 1498, 638, 1118, 1350, 1136, 1684, 1484, 1524,
            1316, 1524, 1338, 1232, 1236, 1480, 1212, 1808, 1222, 1132, 1220, 734, 784, 734, 1160, 1130,
            1240, 1166, 1274, 1044, 1274, 1146, 718, 1176, 1262, 592, 594, 1178, 612, 1906, 1264, 1240,
            1274, 1274, 846, 974, 816, 1258, 1120, 1692, 1088, 1118, 1002, 734, 578, 734, 1160
        };
        static bool IsChinese(char c) { return c >= '\u3400' && c <= '\u9FFF'; }

        public static string FormatReserve(float value)
        {
            return value.ToString(Math.Abs(value)>0 && Math.Abs(value)<0.01f ? "0.###" : "0.##", System.Globalization.CultureInfo.InvariantCulture);
        }

        public static string FormatTradePenalty(string[] parts)
        {
            // The native English branch supplies a minus in its caption, the
            // signed whole part, a decimal point, and a nonnegative fraction.
            // Only these five verified display calls use this formatter.
            if (parts.Length != 5 || parts[3] != "." ||
                !(parts[1].EndsWith("-", StringComparison.Ordinal) || parts[1].EndsWith("−", StringComparison.Ordinal)))
                return String.Concat(parts);
            string label = parts[1];
            string whole = parts[2];
            string sign = System.Globalization.CultureInfo.CurrentCulture.NumberFormat.NegativeSign;
            if (sign.Length > 0 && whole.StartsWith(sign, StringComparison.Ordinal))
                whole = whole.Substring(sign.Length);
            string caption = label.Substring(0, label.Length - 1);
            string shownSign = whole == "0" && parts[4] == "0" ? "" : "−";
            return parts[0] + caption + shownSign + whole + parts[3] + parts[4];
        }

        public static string[] ChineseQualityNames(string[] names)
        {
            var result = (string[])names.Clone();
            for (int i=0;i<result.Length;i++) result[i]=LauncherText(result[i]);
            return result;
        }

        public static string LauncherText(string name)
        {
            switch(name) {
                case "Fastest": case "Very Low": case "Ultra Lowest": return "极低";
                case "Fast": case "Low": return "低";
                case "Simple": case "Medium": return "中";
                case "Good": case "High": return "高";
                case "Beautiful": case "Very High": return "很高";
                case "Fantastic": case "Ultra": return "极高";
                case "Windowed": return "窗口模式";
                case "Fullscreen": return "全屏";
                case "Exclusive Fullscreen": return "独占全屏";
                case "Fullscreen Window": case "Borderless": return "无边框全屏";
                case "Unlimited Framerate": return "不限帧率";
                case "Display Framerate": return "匹配刷新率";
                default: return name;
            }
        }

        static bool IsTag(string token)
        {
            return token[0] == '<' && token.Length > 1 && token[token.Length-1] == '>';
        }

        static bool IsBreak(char first) { return first == '\r' || first == '\n' || first == '|'; }

        static int Width(string token)
        {
            int total = 0;
            for (int i=0; i<token.Length; i++) {
                char c = token[i];
                if (c == '{' && token.Length > 1) { i = token.IndexOf('}', i); total += 1000; }
                else if (c >= ' ' && c <= '~') total += AsciiWidth[c - ' '];
                else if (Char.IsHighSurrogate(c) && i + 1 < token.Length && Char.IsLowSurrogate(token[i+1]))
                    { total += 2000; i++; }
                else total += c >= '\u2E80' || "“”‘’…±·".IndexOf(c) >= 0 ? 2000 : 1160;
            }
            return total;
        }

        static int AttachedWidth(MatchCollection tokens, int start, bool needsWord)
        {
            int width = 0;
            for (int i=start; i<tokens.Count; i++) {
                string token = tokens[i].Value;
                if (IsTag(token)) continue;
                char c = token[0];
                if (IsBreak(c) || (!needsWord && Closing.IndexOf(c) < 0)) break;
                width += Width(token);
                needsWord = Opening.IndexOf(c) >= 0 || (needsWord && c == ' ');
            }
            return width;
        }

        static bool NeedsWrapping(string input, float columns)
        {
            if (String.IsNullOrEmpty(input) || columns < 4) return false;
            foreach (char c in input) if (IsChinese(c)) return true;
            return false;
        }

        static string Prepare(string input, float columns)
        {
            int limit = (int)(columns * 960);
            int width = 0;
            var output = new StringBuilder(input.Length + 16);
            MatchCollection tokens = Tokens.Matches(input);
            for (int i=0; i<tokens.Count; i++) {
                string token = tokens[i].Value;
                char first = token[0];
                if (IsTag(token)) { output.Append(token); continue; }
                if (IsBreak(first)) {
                    output.Append('|');
                    width = 0;
                    continue;
                }
                int units = Width(token);
                int attached = AttachedWidth(tokens, i+1, Opening.IndexOf(first) >= 0);
                if (width > 0 && width + units + attached > limit && Closing.IndexOf(first) < 0) {
                    output.Append('|');
                    width = 0;
                }
                if (width == 0 && first == ' ') continue;
                output.Append(token);
                width += units;
            }
            return output.ToString();
        }

        // Native code still turns each separator into a newline and computes
        // tooltip height or ending scroll length. It must not wrap these lines
        // a second time by counting the raw letters inside a rich-text tag.
        public static string PrepareInt(string input, ref int columns)
        {
            if (!NeedsWrapping(input, columns)) return input;
            string text = Prepare(input, columns);
            columns = Int32.MaxValue;
            return text;
        }

        public static string PrepareFloat(string input, ref float columns)
        {
            if (!NeedsWrapping(input, columns)) return input;
            string text = Prepare(input, columns);
            columns = Single.MaxValue;
            return text;
        }
    }
}
