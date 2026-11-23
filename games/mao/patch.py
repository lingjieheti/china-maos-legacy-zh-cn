"""Player entry point. Requires Windows and Python 3.11+."""
import argparse
import contextlib
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
from build import HERE, HELPER, MANIFEST, build, digest
from manage import manage, running, atomic_copy

def locate():
    import winreg
    candidates=[]
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r"Software\Valve\Steam") as key:
            steam=Path(winreg.QueryValueEx(key,"SteamPath")[0])
            candidates.append(steam)
            manifest=steam/"steamapps/libraryfolders.vdf"
            if manifest.is_file():
                candidates += [Path(s.replace("\\\\","\\")) for s in re.findall(r'"path"\s+"([^"]+)"',manifest.read_text("utf-8-sig"))]
    except OSError:
        pass
    for lib in candidates:
        app=lib/"steamapps/appmanifest_950740.acf"
        if not app.is_file():continue
        found=re.search(r'"installdir"\s+"([^"]+)"',app.read_text("utf-8-sig"))
        if found:
            data=lib/"steamapps/common"/found[1]/"China_Data"
            if (data.parent/"China.exe").is_file():return data.resolve()
    raise RuntimeError("未找到游戏。请先通过 Steam 安装，或使用 --game-data 指定 China_Data。")

def ensure_dependencies(cache):
    from importlib.metadata import PackageNotFoundError,version
    try:
        if version("UnityPy")=="1.25.4":return
    except PackageNotFoundError:pass
    venv=cache/"python-venv"
    py=venv/"Scripts/python.exe"
    if not py.is_file():
        subprocess.run([sys.executable,"-m","venv",str(venv)],check=True)
    subprocess.run([str(py),"-m","pip","install","--disable-pip-version-check","UnityPy==1.25.4"],check=True)
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE="1")
    raise SystemExit(subprocess.call([str(py),str(HERE/"patch.py"),*sys.argv[1:]],env=env))

def revision(fonts):
    files=["build.py","PatchAssembly.cs","ChineseLayout.cs","manifest.json","assembly-plan.json","scenes.zh-CN.json","resources.zh-CN.json"]
    def source_hash(name):
        text=(HERE/name).read_text("utf-8-sig")
        return hashlib.sha256(text.encode("utf-8")).hexdigest()
    hashes=[source_hash(name) for name in files]+[digest(fonts/name) for name in ("UI-Regular.ttf","UI-Semibold.ttf")]
    return hashlib.sha256("".join(hashes).encode()).hexdigest()

@contextlib.contextmanager
def locked(root):
    import msvcrt
    root.mkdir(parents=True,exist_ok=True)
    with (root/"operation.lock").open("a+b") as f:
        if f.tell()==0:f.write(b"0");f.flush()
        f.seek(0)
        try:msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
        except OSError as err:raise RuntimeError("另一个汉化操作正在进行") from err
        try:yield
        finally:
            f.seek(0)
            msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)

def main():
    if sys.version_info<(3,11):raise RuntimeError("需要 Python 3.11 或更高版本")
    parser=argparse.ArgumentParser(description="中国：毛的遗产 简体中文补丁")
    parser.add_argument("action",choices=["install","verify","restore"])
    parser.add_argument("--game-data",type=Path)
    parser.add_argument("--fonts",type=Path,default=HERE.parents[1]/"fonts")
    parser.add_argument("--cache",type=Path,default=Path(os.getenv("LOCALAPPDATA",tempfile.gettempdir()))/"Nostalgames-ZhCN"/"Mao")
    args=parser.parse_args()
    game=args.game_data.resolve() if args.game_data else locate()
    if (game/"China_Data").is_dir():game=game/"China_Data"
    backup=game.parent/".nostalgames-zh-cn"/"backup"
    cache=args.cache.resolve()
    if args.action=="install":
        if running():raise RuntimeError("请先退出游戏")
        cache.mkdir(parents=True,exist_ok=True)
        ensure_dependencies(cache)
    with locked(backup.parent):
        if args.action in ("restore","verify"):
            return manage(args.action,game,backup)
        fonts=args.fonts.resolve()
        recipe=revision(fonts)
        marker=backup/"recipe.txt"
        if marker.is_file() and marker.read_text("ascii")==recipe:
            try:
                manage("verify",game,backup)
                print("已安装当前版本")
                return
            except ValueError:
                pass
        originals=backup/"original"
        source=originals if (originals/"Managed/Assembly-CSharp.dll").exists() else game
        if source==originals:
            for rel,expected in MANIFEST["originals"].items():
                if not (originals/rel).is_file():
                    if not (game/rel).is_file() or digest(game/rel)!=expected:
                        raise ValueError("新涉及的文件需要 Steam 原件："+rel)
                    atomic_copy(game/rel,originals/rel,expected)
        with tempfile.TemporaryDirectory(prefix="stage-",dir=cache) as tmp:
            stage=Path(tmp)
            hashes=build(source,stage,cache,fonts)
            (stage/"sha256.json").write_text(json.dumps(hashes,indent=2),"utf-8")
            manage("install",game,backup,stage)
        marker.write_text(recipe,"ascii")
        print("安装完成。原件备份位于 "+str(backup))

if __name__=="__main__":
    try:main()
    except (RuntimeError,ValueError,OSError,subprocess.CalledProcessError) as e:
        print(str(e),file=sys.stderr)
        raise SystemExit(1)
