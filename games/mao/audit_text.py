"""Read-only four-way audit of installed Chinese, pinned community and Steam EN/RU resources."""
import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

TABLES = (
    "Country", "Doctr", "Events_text", "Opis", "Part1", "Part7", "Part21",
    "Traits1", "Traits7", "Traits21", "new_event_text", "new_focuses_texts",
    "new_modify_opis", "new_modify_texts", "new_texts", "old_modify_opis", "old_modify_text",
    "other_text", "polit_names1", "polit_names7", "polit_names21",
    "polit_surnames1", "polit_surnames7", "polit_surnames21",
)
TAGS = re.compile(r"<(/?)(color|b|i|size|material)(?:\s*=\s*[^<>]*)?>", re.I)
HAN = re.compile(r"[\u3400-\u9fff]")
CYRILLIC = re.compile(r"[\u0400-\u04ff]|\ufffd")
PLACEHOLDER = re.compile(r"\{\d+(?::[^{}]*)?\}")
NUMBER = re.compile(r"(?<![a-zA-Z0-9])[-+−]?\d+(?:[.,]\d+)?%?")
COLORS = set("aqua black blue brown cyan darkblue fuchsia green grey gray lightblue lime magenta maroon navy olive orange pink purple red silver teal white yellow".split())
ANCHORS = {
    ("new_texts", 161): ["华沙条约组织"], ("new_texts", 162): ["经济互助委员会"],
    ("new_texts", 164): ["毛主义堡垒"], ("new_texts", 265): ["赛福鼎", "塔什干"],
    ("new_texts", 266): ["包尔汉", "凯末尔"], ("new_texts", 267): ["艾尔肯", "土耳其"],
    ("new_texts", 323): ["民族救国阵线", "过渡"], ("new_texts", 707): ["取消", "黑五类"],
    ("new_texts", 804): ["250.0"], ("new_texts", 815): ["300.0"], ("new_texts", 880): ["+5.0"],
    ("new_texts", 893): ["直接", "{0}"], ("new_texts", 894): ["秘密", "{0}"],
    ("Events_text", 713): ["国家安全委员会", "民族行动党", "土耳其"],
    ("Events_text", 1306): ["科尔德", "毕晓普", "军委会"],
    ("Events_text", 1307): ["毕晓普", "格林纳达民主运动"], ("other_text", 326): ["不低于", "100.0"],
}
def texts(path):
    import UnityPy
    if path.is_dir():
        path = path / "resources.assets"
    binary = path.read_bytes()
    table = {}
    for obj in UnityPy.load(binary).file.objects.values():
        if obj.type.name == "TextAsset":
            item = obj.read()
            table[item.m_Name] = item.m_Script
    return table, hashlib.sha256(binary).hexdigest()

def visible(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^<>]+>|\{[^{}]*\}|\|", " ", s)).strip()

def balanced(s):
    tags = []
    for tag in TAGS.finditer(s):
        closing, name = tag.groups()
        name = name.lower()
        if closing:
            if not tags or tags.pop() != name:
                return False
        else:
            tags.append(name)
    return not tags

def script_field(script, tag):
    return [v.strip() for v in re.findall(r"<" + tag + r">([^<>]*)", script)]

def lookup_calls(assembly):
    import dnfile
    from dncil.cil.body.reader import read_method_body_from_bytes
    image=dnfile.dnPE(str(assembly))
    try:
        groups={"AddFocus":[], "CreateEvent":[]}
        for cls in image.net.mdtables.TypeDef:
            group={"USSRFocuses":("Init","AddFocus"),"Events":("InitEvents","CreateEvent")}.get(str(cls.TypeName))
            if not group:continue
            wanted, operation=group
            for ref in cls.MethodList:
                method=ref.row
                if str(method.Name)!=wanted or not method.Rva:continue
                ins=read_method_body_from_bytes(image.get_data(method.Rva)).instructions
                for i,load in enumerate(ins):
                    if load.opcode.name!="ldstr" or i+1>=len(ins):continue
                    j=i+1
                    # AddFocus(string,int) loads the default duration after its name.
                    if operation=="AddFocus" and ins[j].opcode.name.startswith("ldc.i4"):j+=1
                    if j>=len(ins):continue
                    call=ins[j]
                    if call.opcode.name not in {"call","callvirt"}:continue
                    token=call.operand.value
                    row=image.net.mdtables.tables[token>>24].rows[(token & 0xffffff)-1]
                    if str(row.Name)==operation:
                        groups[operation].append(image.net.user_strings.get(load.operand.value & 0xffffff).value)
        return groups
    finally:
        image.close()

def audit_fonts(localized, report):
    import dnfile
    from dncil.cil.body.reader import read_method_body_from_bytes
    import runpy
    folder = localized if localized.is_dir() else localized.parent
    translated = texts(folder)[0]
    chars = {ch for name in TABLES for ch in translated[name + "_en"]}
    image = dnfile.dnPE(str(folder / "Managed/Assembly-CSharp.dll"))
    try:
        tokens = set()
        for method in image.net.mdtables.MethodDef:
            if method.Rva:
                code = read_method_body_from_bytes(image.get_data(method.Rva)).instructions
                tokens.update(ins.operand.value & 0xffffff for ins in code if ins.opcode.name == "ldstr")
        count = 0
        for token in tokens:
            value = image.net.user_strings.get(token).value
            if HAN.search(value):
                chars.update(value)
                count += 1
    finally:
        image.close()
    root = Path(__file__).resolve().parents[2]
    coverage = runpy.run_path(str(root / "tools/check_release.py"))["font_coverage_and_spaces"]
    needed = {ord(ch) for ch in chars if ch.isprintable()}
    report["font_coverage"] = {"managed_chinese_strings": count, "unique_printable_characters": len(needed)}
    for weight in ("Regular", "Semibold"):
        supported, _ = coverage((root / "fonts" / f"UI-{weight}.ttf").read_bytes())
        missing = sorted(needed - supported)
        if missing:
            report["errors"].append({"missing_glyphs": weight, "codepoints": [f"U+{cp:04X}" for cp in missing]})

def audit(original, community, localized):
    (source, hs), (base, hb), (actual, ha) = map(texts, (original, community, localized))
    summary = {"sha256": {"original": hs, "community": hb, "localized": ha}, "tables": {},
               "errors": [], "attention": defaultdict(list)}
    error = summary["errors"].append
    attention = summary["attention"]
    changed = {name for name, value in actual.items() if name.endswith("_en") and value != source.get(name)}
    if changed != {n+"_en" for n in TABLES}:
        error({"unexpected_changed_tables": sorted(changed ^ {n+"_en" for n in TABLES})})
    for name in TABLES:
        en, ru = name+"_en", name+"_ru"
        final = actual.get(en,"")
        eng = source.get(en,"")
        russian = source.get(ru,"")
        # This build ships new_event_text_en without a corresponding Russian TextAsset.
        if not final or (not russian and name!="new_event_text"):
            error({"missing_reference_or_translation": name})
        script = name in {"new_event_text","new_focuses_texts"}
        if script:
            # RU and EN wrap descriptions differently. Compare token fields rather than physical row offsets.
            expected = russian if name=="new_focuses_texts" else eng
            for field, language in [("name",expected),("icon",eng)]:
                if script_field(language,field) != script_field(final,field):
                    error({"script_keys_or_icons": [name,field]})
            if re.findall(r"<[^<>]+>",eng) != re.findall(r"<[^<>]+>",final):
                error({"script_markers": name})
        mirror = russian if name in {"Part21","Traits21"} else eng
        src, target = mirror.splitlines(), final.splitlines()
        upstream = base.get(en,"").splitlines()
        if len(src)!=len(target):
            error({"line_count": [name,len(src),len(target)]})
        stats={"rows":len(target),"en_reference":len(eng.splitlines()),"ru_reference":len(russian.splitlines()),
               "community_rows":len(upstream),"different_from_community":0,
               "placeholder_uses":0,"visible_han_rows":0,"long_english_rows":0}
        seen=defaultdict(list)
        for i,(s,t) in enumerate(zip(src,target)):
            key=f"{en}[{i}]"
            if i>=len(upstream) or t.strip()!=upstream[i].strip():stats["different_from_community"]+=1
            if name=="Events_text" and i==1585:s=s.replace("{0)","{0}")
            expected=Counter(PLACEHOLDER.findall(s)); got=Counter(PLACEHOLDER.findall(t))
            stats["placeholder_uses"]+=sum(got.values())
            if got!=expected:error({"placeholder":key})
            if name in {"Part1","Part7","Part21","Doctr","Opis"} and re.findall("[;:]",s)!=re.findall("[;:]",t):
                error({"record_delimiter":key})
            if not balanced(t):error({"unbalanced_tags":key})
            for color in re.findall(r"<color=([^<>]+)>",t,re.I):
                if color.lower() not in COLORS and not re.fullmatch(r"#[0-9A-Fa-f]{6}(?:[0-9A-Fa-f]{2})?|#?\{\d+\}",color):
                    error({"invalid_color":key})
            if CYRILLIC.search(t):error({"replacement_or_cyrillic":key})
            if t.count("|")!=s.count("|"):attention["display_separators"].append(key)
            if Counter(m.group(2).lower() for m in TAGS.finditer(t) if not m.group(1))!=Counter(m.group(2).lower() for m in TAGS.finditer(s) if not m.group(1)):
                attention["emphasis_difference"].append(key)
            st,tt=visible(s),visible(t)
            if HAN.search(tt):stats["visible_han_rows"]+=1
            if not script and st and not tt:error({"empty_translation":key})
            if len(st)>=85:stats["long_english_rows"]+=1
            if tt and len(st)>100 and not script and (len(tt)/len(st)<0.17 or len(tt)/len(st)>0.70):
                attention["length_outlier"].append(key)
            if tt and not HAN.search(tt) and re.search("[a-zA-Z]{3,}",tt):attention["latin_only"].append(key)
            if not script and re.search("[0-9]",st):
                if Counter(NUMBER.findall(st))!=Counter(NUMBER.findall(tt)):attention["numerals"].append(key)
            if len(tt)>=55:
                seen[tt].append((key,st))
            if any(word not in t for word in ANCHORS.get((name,i),[])):error({"regression_anchor":key})
        for group in seen.values():
            if len({st for _,st in group})>1:attention["identical_translation_different_source"].append([k for k,_ in group])
        summary["tables"][en]=stats
    return summary

def main():
    p=argparse.ArgumentParser(description="只读复核英语、俄语、社区汉化和已构建的简体中文文本")
    for name in ["original","community","localized"]:p.add_argument("--"+name,type=Path,required=True)
    p.add_argument("--json",type=Path,help="写入只含表名、索引、计数和哈希的报告")
    p.add_argument("--check-assembly",action="store_true",help="额外对照原版与译版程序集的国策和事件查询键，需要 dnfile 和 dncil")
    p.add_argument("--check-fonts",action="store_true",help="核对两套字体对中文资源表和程序集中文字符串的字形覆盖，需要 dnfile 和 dncil")
    args=p.parse_args()
    report=audit(args.original,args.community,args.localized)
    if args.check_assembly:
        def data_folder(path):return path if path.is_dir() else path.parent
        inputs=[data_folder(i)/"Managed/Assembly-CSharp.dll" for i in (args.original,args.localized)]
        original,final=map(lookup_calls,inputs)
        translated=texts(args.localized)[0]
        for op,table,count,distinct in [("AddFocus","new_focuses_texts_en",20,19),("CreateEvent","new_event_text_en",1,1)]:
            keys=final[op]
            if len(keys)!=count or len(set(keys))!=distinct or keys!=original[op] or not set(keys)<=set(script_field(translated[table],"name")):
                report["errors"].append({"binary_lookup_mismatch":op})
        report["assembly_calls"]={op:len(values) for op,values in final.items()}
    if args.check_fonts:
        audit_fonts(args.localized, report)
    if args.json:args.json.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n","utf8")
    print(f"{len(report['tables'])} 张表，{sum(s['rows'] for s in report['tables'].values())} 行，{len(report['errors'])} 项错误")
    print("复核提示（允许正常的译文差异）", {k:len(v) for k,v in report["attention"].items()})
    if report["errors"]:print(json.dumps(report["errors"],ensure_ascii=False))
    return bool(report["errors"])

if __name__=="__main__":
    raise SystemExit(main())
