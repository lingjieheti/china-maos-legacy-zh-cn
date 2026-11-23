using System;
using System.Text;
using System.Text.RegularExpressions;

namespace Nostalgames.ZhCN
{
    public static class ChineseLayout
    {
        static readonly Regex Tokens = new Regex(@"</?[A-Za-z#][^<>\r\n]*>|\{[0-9]+(?:[^{}]*)\}|[\r\n|]+|[A-Za-z0-9]+(?:[.,:/-][A-Za-z0-9]+)*|[\uD800-\uDBFF][\uDC00-\uDFFF]|[\s\S]");
        const string Closing = "，。、：；？！）》】」』”’…％,.!?;:%)]";
        const string Opening = "（《【「『“‘(";
        static bool IsChinese(char c) { return c >= '\u3400' && c <= '\u9FFF'; }

        public static string FormatReserve(float value)
        {
            return value.ToString(Math.Abs(value)>0 && Math.Abs(value)<0.01f ? "0.###" : "0.##", System.Globalization.CultureInfo.InvariantCulture);
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

        public static string Prepare(string input, float columns)
        {
            if (String.IsNullOrEmpty(input) || columns < 4) return input;
            bool chinese = false;
            foreach (char c in input) if (IsChinese(c)) { chinese = true; break; }
            if (!chinese) return input;

            // The stock renderer measures Latin columns, then only wraps at ASCII spaces.
            // Supply legal boundaries first. Preserve the stock line-count and panel-sizing logic.
            int limit = Math.Max(4, (int)Math.Floor(columns * 0.96));
            int width = 0;
            var output = new StringBuilder(input.Length + 16);
            foreach (Match match in Tokens.Matches(input))
            {
                string token = match.Value;
                char first = token[0];
                if (first == '<' && token.Length > 1 && token[token.Length-1] == '>') { output.Append(token); continue; }
                if (first == '\r' || first == '\n' || first == '|')
                {
                    output.Append(token.Replace("\r\n","|").Replace('\r','|').Replace('\n','|'));
                    width = 0;
                    continue;
                }
                int units = first == '{' ? 1 : first >= '\u2E80' ? 2 : token.Length;
                bool opens = Opening.IndexOf(first) >= 0;
                if (width > 0 && (width + units > limit || (opens && width + units + 2 > limit)) && Closing.IndexOf(first) < 0)
                {
                    output.Append('|');
                    width = 0;
                }
                if (width == 0 && first == ' ') continue;
                output.Append(token);
                width += units;
            }
            return output.ToString();
        }
    }
}
