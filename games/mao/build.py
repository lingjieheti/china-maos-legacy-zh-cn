"""Build the Chinese patch from local Steam files and pinned community data."""
import argparse
import base64
import collections
import copy
import hashlib
import http.client
import json
import os
import re
import shutil
import struct
import subprocess
import tempfile
import time
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
MANIFEST = json.loads((HERE / "manifest.json").read_text("utf-8"))
CECIL_SHA = "d2a23832aaa948ba9a01acc42b5726e34c5f995958f1b30d45c0e7c70b3a72d5"
HELPER = "Managed/Nostalgames.ChineseLayout.dll"

def digest(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()

def fetch(url, dest, expected, offline=False):
    if dest.is_file() and digest(dest) == expected:
        return False
    if offline:
        raise ValueError("离线缓存缺失或校验失败：" + str(dest))
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=dest.parent, delete=False) as f:
        temp = Path(f.name)
    try:
        # Keep completed files across retries. Never replace a cached file with an incomplete download.
        for attempt in range(3):
            try:
                request=urllib.request.Request(url,headers={"User-Agent":"China-Maos-Legacy-ZhCN"})
                with urllib.request.urlopen(request,timeout=60) as response, temp.open("wb") as f:
                    total=0
                    while block:=response.read(1024*1024):
                        f.write(block)
                        total+=len(block)
                        if total//(16*1024*1024)!=(total-len(block))//(16*1024*1024):
                            print(f"{dest.name} 已接收 {total//(1024*1024)} MB",flush=True)
                if digest(temp)!=expected:raise ValueError("下载内容的 SHA-256 不匹配")
                break
            except (OSError, ValueError, EOFError, http.client.HTTPException) as err:
                if attempt==2:raise RuntimeError(f"三次下载均未通过：{dest.name}。已核验的缓存会保留，下次安装可继续。{err}") from err
                time.sleep(attempt+1)
        os.replace(temp, dest)
        return True
    finally:
        temp.unlink(missing_ok=True)

def dependencies(cache, offline=False):
    commit = MANIFEST["commit"]
    def download(item):
        rel, sha = item
        host = "media.githubusercontent.com/media" if rel.endswith("/resources.assets") else "raw.githubusercontent.com"
        url = f"https://{host}/LeXwDeX/Mao-s-Legacy-Chinese-Tools/{commit}/{rel}"
        if fetch(url, cache / rel, sha, offline=offline):
            print("已下载并校验 " + rel, flush=True)
    package = HERE / "vendor/mono.cecil.0.11.6.nupkg"
    if not package.is_file() or digest(package)!=CECIL_SHA:
        raise ValueError("Mono.Cecil 组件缺失或校验失败，请重新获取完整的简体中文安装包。")
    print("正在核验社区汉化缓存，首次安装会下载缺少的文件。" if not offline else "正在核验离线缓存。",flush=True)
    print(f"缓存目录：{cache}",flush=True)
    with ThreadPoolExecutor(max_workers=5) as pool:
        list(pool.map(download, MANIFEST["upstream"].items()))
    return package

def read_unity_string(raw, offset):
    length = struct.unpack_from("<I", raw, offset)[0]
    if offset + 4 + length > len(raw):
        raise ValueError("Unity 字符串越界")
    return raw[offset + 4:offset + 4 + length].decode("utf-8"), 4 + (length + 3) // 4 * 4

def unity_string(text):
    b = text.encode("utf-8")
    return struct.pack("<I",len(b)) + b + bytes((-len(b))%4)

def heap_string(data, pos):
    first = data[pos]
    if first & 0x80 == 0: size, header = first, 1
    elif first & 0xc0 == 0x80: size, header = (first & 63) << 8 | data[pos+1], 2
    else: size, header = int.from_bytes(data[pos:pos+4], "big") & 0x1fffffff, 4
    return data[pos+header:pos+header+size-1].decode("utf-16le")

def terminology(text):
    for old, preferred in (
        ("陈希连","陈锡联"), ("王东兴","汪东兴"), ("乔治·马尔尚","乔治·马歇"),
        ("诋毁度","外交声望"), ("情报代理网络","情报网"), ("代理人网络","情报网"),
        ("代理网络","情报网"), ("干员网络","情报网"), ("炮轰总部","炮打司令部"),
        ("赛义夫丁·阿齐兹","赛福鼎·艾则孜"), ("布尔汗·沙希迪","包尔汉·沙希迪"),
        ("埃尔金·阿尔普特金","艾尔肯·阿勒普特金"), ("Türkiye","土耳其"),
        ("《Zёri i popullit》（《人民之声》）","《人民之声报》"), ("СPI","CPI"),
        ("同志主席","主席同志"), ("潘亚·雅托图（Pany Yathotou）","巴妮·雅陶都"),
        ("潘亚·雅托图","巴妮·雅陶都"),
    ):
        text=text.replace(old,preferred)
    return text

def polish_resource(table, index, text):
    # These names appear in button labels as well as the surrounding narrative.
    for old, new in (
        ("Forbes Burnham","福布斯·伯纳姆"), ("Cheddi Jagan","契迪·贾根"),
        ("Marcellus Fielden Singh","马塞勒斯·菲尔登·辛格"), ("Hugh Desmond Hoyt","休·德斯蒙德·霍伊特"),
        ("Brindley Benn","布林德利·本"), ("Burnham","伯纳姆"), ("Jagan","贾根"),
        ("Hoyt","霍伊特"), ("Brindley","布林德利"), ("Singh","辛格"), ("Benn","本"),
        ("Desi Bouterse","德西·鲍特瑟"), ("Bouterse","鲍特瑟"),
        ("Johan Ferrier","约翰·费里埃"), ("Chin Ah Sen","陈亚先"), ("Chin Ah Sung","陈亚先"),
        ("Rambokus","兰博库斯"), ("Wilfred Hawker","威尔弗雷德·霍克"), ("Hawker","霍克"),
        ("拉斐尔·卡尔德拉（Rafael Caldera）","拉斐尔·卡尔德拉"), ("Rafael Caldera","拉斐尔·卡尔德拉"),
        ("哈梅·卢辛奇（Jaime Lusinchi）","海梅·卢辛奇"), ("Jaime Lusinchi","海梅·卢辛奇"),
        ("乌戈·查韦斯（Hugo Chavez）","乌戈·查韦斯"), ("Hugo Chavez","乌戈·查韦斯"),
        ("Lusinchi","卢辛奇"), ("Caldera","卡尔德拉"), ("国民党（国民党）","国民党"),
        ("Korda-Austin","科尔德和奥斯汀"), ("伯纳德·科尔达","伯纳德·科尔德"), ("Maurice Bishop","莫里斯·毕晓普"),
        ("Aldo Moro","阿尔多·莫罗"), ("萨德诺·佩尔蒂尼","桑德罗·佩尔蒂尼"),
        ("萨丹罗·佩尔蒂尼","桑德罗·佩尔蒂尼"), ("让·马尔谢","乔治·马歇"),
        ("凯修·桑潘（Khieu Samphan）","乔森潘"), ("农诺切亚（Nuon Chea）","农谢"),
        ("宋森（Son Sen）","宋成"), ("民主独立党（民主独立党）","民主独立党"),
        ("《人民日报》（Renmin Zhibao）","《人民日报》"),
    ):
        text = text.replace(old, new)
    # Normalize malformed literal attributes that Unity's legacy rich-text parser rejects.
    text = re.sub(r"<color=#\s+([0-9a-fA-F]{6})>", r"<color=#\1>", text)
    text = text.replace("<color='s successor #8B4513>", "<color=#8B4513>")
    if table=="new_texts_en" and index==448:
        text=text.replace("（<color=none>perestroika</color>）","")
    if table=="Events_text_en" and index==1290:
        text=re.sub(r"<color=none>([^<>]*)</color>",r"\1",text)
    if table == "Events_text_en":
        # The source separates the sign from the value in many event costs.
        # Restrict this to keyed effects so that dates and ranges stay intact.
        text = re.sub(r"[:：] *([-+]) +(?=[0-9])",
                      lambda m: "：" + ("−" if m[1] == "-" else "+"), text)
        text = re.sub(r"(\{\d+\}) +([-+]) +(?=[0-9])",
                      lambda m: m[1] + "：" + ("−" if m[2] == "-" else "+"), text)
        text = re.sub(r"[,;] *(?=\{\d+\}[：:])", "，", text)
    if table=="new_texts_en" and index==981 and not text.endswith("|"):
        text+="|"
    return text


def build_assembly(data, stage, cache, package, temp):
    plan = json.loads((HERE/"assembly-plan.json").read_text("utf-8"))
    translations = json.loads((cache/"dll_strings/translated.json").read_text("utf-8"))
    source = data/"Managed/Assembly-CSharp.dll"
    binary = source.read_bytes()
    rows = []
    b64 = lambda s: base64.b64encode(s.encode("utf-8")).decode("ascii")
    for token, choice, sites in plan["records"]:
        original = heap_string(binary, plan["heap_offset"]+token)
        if choice.startswith("@"):
            row = translations[choice[1:]]
            if original != row["text"]:
                raise ValueError("字串与当前游戏不符")
            chinese = row["translated"].strip(" ")
            # Upstream inserted hard breaks into narrative that is now wrapped by glyph widths.
            if "\n" not in original:
                chinese = chinese.replace("\n","")
            if not re.search(r'</?(?:color|size|b|i|material)(?:=[^<>]+)?>|<#[\da-fA-F]+>',original):
                chinese=re.sub(r'</?(?:color|size|b|i|material)(?:=[^<>]+)?>|<#[\da-fA-F]+>','',chinese)
            if original.startswith("\n") and not chinese.startswith("\n"):
                chinese = "\n" + chinese
            if original.endswith("\n") and not chinese.endswith("\n"):
                chinese += "\n"
        else:
            chinese = choice
        rows.append("\t".join([b64(original),b64(terminology(chinese)),",".join(sites)]))
    table = temp/"strings.tsv"
    table.write_text("\n".join(rows),"utf-8")
    csc = Path(os.environ["WINDIR"])/"Microsoft.NET/Framework64/v4.0.30319/csc.exe"
    if not csc.exists():
        csc = Path(os.environ["WINDIR"])/"Microsoft.NET/Framework/v4.0.30319/csc.exe"
    cecil = temp/"Mono.Cecil.dll"
    with zipfile.ZipFile(package) as archive:
        cecil.write_bytes(archive.read("lib/net40/Mono.Cecil.dll"))
    helper = stage/HELPER
    helper.parent.mkdir(parents=True, exist_ok=True)
    program = temp/"PatchAssembly.exe"
    subprocess.run([str(csc),"/nologo","/optimize+","/target:library","/out:"+str(helper),str(HERE/"ChineseLayout.cs")],check=True)
    subprocess.run([str(csc),"/nologo","/optimize+","/r:"+str(cecil),"/out:"+str(program),str(HERE/"PatchAssembly.cs")],check=True)
    subprocess.run([str(program),str(source),str(stage/"Managed/Assembly-CSharp.dll"),str(table),str(helper)],check=True)
    launcher="Managed/NewResolutionDialog.dll"
    subprocess.run([str(program),"launcher",str(data/launcher),str(stage/launcher),str(helper)],check=True)

def with_line_endings(original, lines):
    ending = "\r\n" if "\r\n" in original else "\n"
    return ending.join(lines)

def split_lines(text):
    return text.replace("\r\n","\n").split("\n")

def placeholders(text):
    return sorted(re.findall(r"\{\d+(?:[^{}]*)\}",text))

def script_keys(script):
    return [s.strip() for s in re.findall(r"<name>\s*(.*?)\s*<title>", script, re.S)]

def merge_resources(original, upstream, font_files, edits):
    # The game requests Part21_en, but its French party table is present only in Russian.
    # Add the missing language counterpart and register its name with the ResourceManager.
    original_party=original.objects[268]
    example=original_party.read()
    if example.m_Name!="Part21_ru" or original_party.get_raw_data()!=unity_string(example.m_Name)+unity_string(example.m_Script):
        raise ValueError("法国政党表模板不匹配")
    additions=edits["Part21_en"]["0"]
    if len(additions.split(";"))!=len(example.m_Script.split(";")):raise ValueError("法国政党字段不一致")
    clone=copy.copy(original_party)
    clone.path_id=560
    if clone.path_id in original.objects:raise ValueError("法国文本资源 ID 冲突")
    clone.set_raw_data(unity_string("Part21_en")+unity_string(additions))
    for pid, obj in original.objects.items():
        if obj.type.name == "Font":
            data = obj.read()
            data.m_FontData = font_files[1 if pid in {338,341,342} else 0]
            data.save()
        elif obj.type.name == "MonoBehaviour" and pid in {547,548,549,550,551,552,555,556}:
            if obj.read(check_read=False).m_Name != upstream.objects[pid].read(check_read=False).m_Name:
                raise ValueError("TMP 字体标识不匹配")
            obj.set_raw_data(upstream.objects[pid].get_raw_data())
        elif obj.type.name == "TextAsset":
            data = obj.read()
            old = data.m_Script
            name = data.m_Name
            community = upstream.objects[pid].read()
            if community.m_Name != name:
                raise ValueError("文本资源标识不匹配")
            if community.m_Script == old and name not in edits:
                continue
            originals = split_lines(old)
            if name=="Traits21_en":
                ru=original.objects[285].read()
                if ru.m_Name!="Traits21_ru":raise ValueError("法国特质表模板不匹配")
                originals=split_lines(ru.m_Script)
            lines = split_lines(community.m_Script) if name!="Traits21_en" else originals.copy()
            while len(lines)<len(originals) and originals[len(lines)].strip()=="":
                lines.append("")
            if len(lines)!=len(originals):
                raise ValueError("文本行数不匹配 "+name)
            lines = [s.rstrip(" \t") for s in lines]
            for index,text in edits.get(name,{}).items():
                lines[int(index)] = text
            if name in {"new_focuses_texts_en", "new_event_text_en"}:
                # Both Readers use <name> as a dictionary key. The English focus
                # resource contains display aliases for seven hard-coded Russian-slot keys.
                key_source = old
                if name == "new_focuses_texts_en":
                    template = original.objects[313].read()
                    if template.m_Name != "new_focuses_texts_ru":
                        raise ValueError("国策标识模板不匹配")
                    key_source = template.m_Script
                keys = script_keys(key_source)
                indices = [i + 1 for i, line in enumerate(originals) if line.strip() == "<name>"]
                expected = 24 if name == "new_focuses_texts_en" else 1
                if len(indices) != expected or len(set(keys)) != expected or len(keys) != expected:
                    raise ValueError("脚本标识数量不匹配 " + name)
                for i, key in zip(indices, keys):
                    lines[i] = key
            for idx,(source, target) in enumerate(zip(originals,lines)):
                if name=="new_texts_en" and idx==880:
                    old_label="冲突进度的代价："
                    if old_label not in target:raise ValueError("冲突进度标签不匹配")
                    target=target.replace(old_label,"冲突进度提高 +5.0 的代价：")
                if name=="Events_text_en" and idx==1512:
                    first,remaining=target.split("{0}",1)
                    target=first+"{0}"+remaining.replace("{0}","")
                if name=="Events_text_en" and idx==1585:
                    # The original uses a malformed {0) once; the game expects {0}.
                    source = source.replace("{0)","{0}")
                    target=target.replace("LГ¤nder议院","各州议院").replace("LГ¤nder","各州")
                if placeholders(source)!=placeholders(target):
                    raise ValueError(f"占位符不匹配 {name}[{idx}]")
                if name in {"Part1_en","Part7_en","Doctr_en","Opis_en"}:
                    if re.findall("[;:]",source)!=re.findall("[;:]",target):
                        raise ValueError("政党或人物记录分隔符不匹配 "+name)
                if name in {"new_focuses_texts_en","new_event_text_en"} and re.fullmatch(r"<[^>]+>",source.strip()):
                    if source.strip()!=target.strip():
                        raise ValueError("脚本标记不匹配 "+name)
                    target=source
                lines[idx]=polish_resource(name,idx,terminology(target))
            data.m_Script=with_line_endings(old,lines)
            data.save()

    original.objects[clone.path_id]=clone

def french_resource_index(src):
    obj=src.objects[13]
    manager=obj.read()
    pairs=manager.m_Container
    if any(key=="part21_en" for key,_ in pairs):raise ValueError("法国资源已存在")
    pointer=copy.copy(next(v for k,v in pairs if k=="part21_ru"))
    if pointer.m_FileID!=9 or pointer.m_PathID!=268:raise ValueError("法国资源索引不匹配")
    rebuilt=type(pointer)(m_FileID=9,m_PathID=560,assetsfile=src)
    at=next(i for i,(key,_) in enumerate(pairs) if key=="part21_ru")
    manager.m_Container=[*pairs[:at],("part21_en",rebuilt),*pairs[at:]]
    manager.save()

def patch_launcher(src):
    external=copy.copy(src.externals[0])
    external.path="resources.assets"
    src.externals.append(external)
    font_file=len(src.externals)
    words={
        "Quit":"退出","Graphics Settings":"图形设置","Close":"关闭","Play":"开始游戏",
        "16000x12000":"16000×12000","1999 fps":"1999 帧/秒","Exclusive Fullscreen":"独占全屏",
        "Fullscreen Window":"无边框全屏","Windowed":"窗口模式","Unlimited Framerate":"不限帧率",
        "Display Framerate":"匹配刷新率","1/2 Display Framerate":"刷新率的 1/2",
        "1/3 Display Framerate":"刷新率的 1/3","1/4 Display Framerate":"刷新率的 1/4",
        "Display 1":"显示器 1","Ultra Lowest":"极低","Option A":"选项 A","Option B":"选项 B","Option C":"选项 C",
        "Warning: can cause screen tearing, decreases battery life, increases power consumption, heat & fan noise.":"不限帧可能导致画面撕裂，并增加耗电、发热和风扇噪声。",
        "Display changes will only take effect after restarting the application.":"重启游戏后，显示器设置生效。"
    }
    for pid,obj in src.objects.items():
        if obj.type.name!="MonoBehaviour": continue
        raw=bytearray(obj.get_raw_data())
        script=struct.unpack_from("<iq",raw,16)
        if script==(1,378):
            old,width=read_unity_string(raw,128)
            if struct.unpack_from("<iq",raw,72)!=(3,10102): raise ValueError("启动器字体标识不匹配")
            struct.pack_into("<iq",raw,72,font_file,338 if pid in {629,645,677} else 343)
            if pid==717: struct.pack_into("<i",raw,84,12)
            if old in words:raw[128:128+width]=unity_string(words[old])
            obj.set_raw_data(bytes(raw))
        elif pid in {546,547,564,565,680,681,710,711,762,763,774,775}:
            # Keep event names and animation states unchanged. Edit only captions in the option list.
            for at in reversed(range(372,len(raw)-4,4)):
                try: word,width=read_unity_string(raw,at)
                except (ValueError,UnicodeDecodeError):continue
                if word in words:raw[at:at+width]=unity_string(words[word])
            obj.set_raw_data(bytes(raw))

def language_buttons(src, fontdir, settings):
    from PIL import Image, ImageDraw, ImageFont

    # The settings screen has its own smaller pair, without hover sprites.
    # Textures alone change; the original sprites and colliders retain their size.
    if settings:
        choices = [(29, 70, "Русский", 224, False), (37, 78, "简体中文", 224, False)]
        height, original_format, chinese_size, russian_size = 136, 10, 41, 36
    else:
        choices = [(2, 8, "Русский", 415, True), (3, 9, "简体中文", 414, True),
                   (4, 10, "简体中文", 414, False), (5, 11, "Русский", 415, False)]
        height, original_format, chinese_size, russian_size = 207, 4, 72, 64
    fonts = {label: ImageFont.truetype(str(fontdir / "UI-Semibold.ttf"), size)
             for label, size in (("简体中文", chinese_size), ("Русский", russian_size))}
    for pid, sprite_id, label, width, hover in choices:
        texture = src.objects[pid].read()
        sprite = src.objects[sprite_id].read()
        if (sprite.m_RD.texture.m_PathID != pid or sprite.m_RD.texture.m_FileID != 0
                or (texture.m_Width, texture.m_Height, texture.m_TextureFormat) != (width, height, original_format)):
            raise ValueError("语言按钮原图不匹配")
        image = Image.new("RGBA", (width, height), "#833a36" if hover else "#442d2a")
        draw = ImageDraw.Draw(image)
        inset = 4 if settings else 7
        draw.rectangle((inset, inset, width-inset-1, height-inset-1),
                       outline="#efdba9" if hover else "#ad9675", width=2 if settings else 4)
        font = fonts[label]
        left, top, right, bottom = draw.textbbox((0, 0), label, font=font)
        origin = ((width - left - right) // 2, (height - top - bottom) // 2)
        draw.text(origin, label, font=font, fill="#fff6df")
        texture.set_image(image, target_format=4)
        texture.save()

def economy_typography(src):
    # Budget cards share the same art and text area. Values and +/- controls retain their original scale.
    budget={523,524,533,538,540,543,547,555,559,564,569,574,575,580,597,599,600}
    right={541:(0.031,0.94),592:(0.048,0.96),598:(0.050,0.96),603:(0.044,0.95),609:(0.048,0.96),610:(0.043,0.96)}
    for pid in budget|set(right):
        obj=src.objects[pid]
        if obj.type.name!="TextMesh":raise ValueError("经济标签标识不匹配")
        mesh=obj.read()
        mesh.m_CharacterSize,mesh.m_LineSpacing=right.get(pid,(0.063,1.0))
        mesh.save()

def event_title_typography(src):
    # doneventscript.Name is shared by event headlines; its upper edge sits
    # against the top HUD. Zaglav is the separate body immediately below it.
    label = src.objects[359].read()
    transform = src.objects[160].read()
    if (label.m_GameObject.m_PathID != 36 or transform.m_GameObject.m_PathID != 36 or
        label.m_FontSize != 50 or label.m_Anchor != 1 or
        abs(label.m_CharacterSize - .10) > .00001 or
        abs(label.m_LineSpacing - .70) > .00001 or
        abs(transform.m_LocalPosition.y - 4.596) > .00001):
        raise ValueError("事件标题的原始排版与预期不符")
    label.m_CharacterSize = .074
    label.m_LineSpacing = .78
    transform.m_LocalPosition.y = 4.484
    label.save()
    transform.save()

def load_details_typography(src):
    # Save and load use the same background art. In the load scene only, the
    # details start 0.09 units higher and intersect the panel's top border.
    transform = src.objects[31].read()
    if transform.m_GameObject.m_PathID != 15 or abs(transform.m_LocalPosition.y - .98) > .00001:
        raise ValueError("读档详情的位置与预期不符")
    transform.m_LocalPosition.y = .89
    transform.save()

def build_assets(data, stage, cache, fontdir):
    import UnityPy
    patch = cache/"1.8.5_output"
    regular, bold = [(fontdir / n).read_bytes() for n in ("UI-Regular.ttf","UI-Semibold.ttf")]
    scenes=json.loads((HERE/"scenes.zh-CN.json").read_text("utf-8"))
    edited=json.loads((HERE/"resources.zh-CN.json").read_text("utf-8"))
    for rel in MANIFEST["originals"]:
        if rel.endswith(".dll"):
            continue
        env=UnityPy.load((data/rel).read_bytes())
        src=env.file
        community=UnityPy.load((patch/rel).read_bytes()).file if ("1.8.5_output/"+rel) in MANIFEST["upstream"] else None
        if community and set(src.objects)!=set(community.objects):
            raise ValueError("资源对象集合有变化 "+rel)
        if rel=="resources.assets":
            merge_resources(src, community, (regular,bold),edited)
        elif rel=="globalgamemanagers":
            french_resource_index(src)
        elif rel=="sharedassets0.assets":
            patch_launcher(src)
        elif rel in ("sharedassets1.assets","sharedassets5.assets"):
            language_buttons(src, fontdir, settings=rel=="sharedassets5.assets")
        elif rel in ("sharedassets2.assets","sharedassets3.assets"):
            for obj in src.objects.values():
                if obj.type.name=="Font":
                    f=obj.read()
                    f.m_FontData=bold if f.m_Name=="Capture_it" else regular
                    f.save()
        elif rel in ("sharedassets15.assets","sharedassets18.assets"):
            for pid,obj in src.objects.items():
                if obj.type.name=="TextMesh":
                    d=obj.read()
                    other=community.objects[pid].read()
                    if d.m_Text!=other.m_Text:
                        d.m_Text=other.m_Text
                        d.save()
        else:
            grouped=collections.defaultdict(list)
            for pid,offset,value in scenes[rel]:
                grouped[pid].append((offset,value))
            for pid,changes in grouped.items():
                obj=src.objects[pid]
                raw=obj.get_raw_data()
                for at,value in sorted(changes,reverse=True):
                    _,width=read_unity_string(raw,at)
                    if value=="@":
                        value=read_unity_string(community.objects[pid].get_raw_data(),at)[0].strip(" ")
                    raw=raw[:at]+unity_string(value)+raw[at+width:]
                obj.set_raw_data(raw)
        if rel=="level9":economy_typography(src)
        if rel=="level11":event_title_typography(src)
        if rel=="level13":load_details_typography(src)
        dst=stage/rel
        dst.write_bytes(src.save())
        reread=UnityPy.load(dst.read_bytes()).file
        if set(src.objects)!=set(reread.objects):
            raise ValueError("重读对象集合有变化 "+rel)
        for pid,obj in src.objects.items():
            if (obj.data if obj.data is not None else obj.get_raw_data())!=reread.objects[pid].get_raw_data():
                raise ValueError(f"写入不一致 {rel}/{pid}")
        print("OK "+rel,flush=True)

def build(data, stage, cache, fonts, offline=False):
    for rel,h in MANIFEST["originals"].items():
        if not (data/rel).is_file() or digest(data/rel)!=h:
            raise ValueError("需要指定版本的 Steam 原件，校验失败 "+rel)
    for folder in (stage, cache):
        if folder==data or data in folder.parents: raise ValueError("构建与缓存目录须位于游戏目录以外")
    stage.mkdir(parents=True,exist_ok=True)
    package=dependencies(cache, offline)
    with tempfile.TemporaryDirectory(dir=stage) as tmp:
        build_assembly(data,stage,cache,package,Path(tmp))
    build_assets(data,stage,cache,fonts)
    return {n:digest(stage/n) for n in [*MANIFEST["originals"],HELPER]}

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--game-data",required=True,type=Path)
    parser.add_argument("--output",required=True,type=Path)
    parser.add_argument("--cache",type=Path,default=Path.home()/".cache"/"nostalgames-zh-cn"/"mao")
    parser.add_argument("--fonts",type=Path,default=HERE.parents[1]/"fonts")
    args=parser.parse_args()
    hashes=build(args.game_data.resolve(),args.output.resolve(),args.cache.resolve(),args.fonts.resolve())
    (args.output/"sha256.json").write_text(json.dumps(hashes,indent=2),"utf-8")
