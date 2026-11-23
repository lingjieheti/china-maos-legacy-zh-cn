"""Find App 950740 in registered Steam libraries or verify a player-selected folder."""
import os
import re
from pathlib import Path


def game_data(selected):
    folder=Path(selected).expanduser().resolve()
    if folder.is_file() and folder.name.casefold()=="china.exe":
        folder=folder.parent
    data=folder if folder.name.casefold()=="china_data" else folder/"China_Data"
    if data.is_dir() and (data.parent/"China.exe").is_file():
        return data
    raise ValueError("所选目录不是《中国：毛的遗产》。请选择含 China.exe 的游戏目录或其中的 China_Data。")


def steam_roots():
    import winreg
    for name in ("SteamPath","STEAM_PATH"):
        if os.environ.get(name):
            yield Path(os.environ[name])
    for hive,name in ((winreg.HKEY_CURRENT_USER,"SteamPath"),(winreg.HKEY_LOCAL_MACHINE,"InstallPath")):
        for view in (0,winreg.KEY_WOW64_32KEY,winreg.KEY_WOW64_64KEY):
            try:
                with winreg.OpenKey(hive,r"Software\Valve\Steam",0,winreg.KEY_READ|view) as key:
                    yield Path(winreg.QueryValueEx(key,name)[0])
            except OSError:
                pass
    for var in ("ProgramFiles(x86)","ProgramFiles"):
        if os.environ.get(var):
            yield Path(os.environ[var])/"Steam"


def read_vdf(path):
    try:
        return path.read_text("utf-8-sig")
    except (OSError,UnicodeError):
        return ""


def steam_libraries(roots):
    seen=set()
    for root in roots:
        root=Path(root)
        if root.name.casefold()=="steamapps" or root.is_file():root=root.parent
        config=read_vdf(root/"steamapps/libraryfolders.vdf")
        extras=[]
        for key,value in re.findall(r'"([^"\n]+)"\s*"((?:\\.|[^"\\\n])*)"',config):
            path=Path(value.replace("\\\\","\\"))
            if (key.casefold()=="path" or key.isdecimal()) and path.is_absolute():
                extras.append(path)
        for library in (root,*extras):
            library=library.resolve()
            if library not in seen:
                seen.add(library)
                yield library


def locate(roots=None):
    for lib in steam_libraries(steam_roots() if roots is None else roots):
        apps=lib/"steamapps"
        contents=read_vdf(apps/"appmanifest_950740.acf")
        match=re.search(r'"installdir"\s*"([^"\r\n]+)"',contents,re.I)
        if not match:continue
        relative=Path(match[1])
        if relative.anchor or ".." in relative.parts:continue
        try:
            return game_data(apps/"common"/relative)
        except ValueError:
            continue
    raise RuntimeError("未找到《中国：毛的遗产》。请在安装器中选择含 China.exe 的游戏文件夹。")
