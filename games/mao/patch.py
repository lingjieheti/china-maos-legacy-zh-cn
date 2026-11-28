"""Player entry point. Requires Windows and Python 3.11+."""
import argparse
import contextlib
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0,str(Path(__file__).resolve().parent))
from build import HERE, HELPER, MANIFEST, build, digest
from manage import manage, running, atomic_copy
from steam_paths import game_data, locate

def ensure_dependencies(cache, offline=False):
    from importlib.metadata import PackageNotFoundError,version
    try:
        if version("UnityPy")=="1.25.4":return
    except PackageNotFoundError:pass
    if any(Path(sys.executable).parent.glob("*._pth")) or offline:
        raise RuntimeError("安装包缺少 UnityPy 1.25.4，请重新获取完整安装包。通过源码安装时可在 Python 环境中预装此依赖。")
    venv=cache/"python-venv"
    py=venv/"Scripts/python.exe"
    if not py.is_file():
        subprocess.run([sys.executable,"-m","venv",str(venv)],check=True)
    subprocess.run([str(py),"-m","pip","install","--disable-pip-version-check","UnityPy==1.25.4"],check=True)
    return py

def revision(fonts):
    files=["build.py","PatchAssembly.cs","ChineseLayout.cs","manifest.json","assembly-plan.json","scenes.zh-CN.json","resources.zh-CN.json","tutorial_art.py"]
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
    parser.add_argument("--game-dir","--game-data",dest="game_dir",type=Path)
    parser.add_argument("--offline",action="store_true",help="仅使用已校验的本地社区缓存")
    parser.add_argument("--fonts",type=Path,default=HERE.parents[1]/"fonts")
    parser.add_argument("--cache",type=Path,default=Path(os.getenv("LOCALAPPDATA",tempfile.gettempdir()))/"Nostalgames-ZhCN"/"Mao")
    args=parser.parse_args()
    game=game_data(args.game_dir) if args.game_dir else locate()
    backup=game.parent/".nostalgames-zh-cn"/"backup"
    cache=args.cache.resolve()
    if args.action=="install":
        if running():raise RuntimeError("请先退出游戏")
        cache.mkdir(parents=True,exist_ok=True)
    with locked(backup.parent):
        if args.action=="restore":
            return manage(args.action,game,backup)
        fonts=args.fonts.resolve()
        recipe=revision(fonts)
        marker=backup/"recipe.txt"
        installed_recipe=marker.read_text("ascii").strip() if marker.is_file() else ""
        if args.action=="verify":
            # Diagnose damaged game/backup files before suggesting a routine update.
            count=manage("verify",game,backup,report=False)
            if installed_recipe!=recipe or count!=len(MANIFEST["originals"])+1:
                raise ValueError("已安装的汉化文件完整，当前安装器的版本更新。请点击“安装汉化”升级。")
            print("当前版本汉化文件及原件备份均已核验")
            return
        # Release 1.2 changed dependency acquisition only. A verified v1.1
        # installation has identical game content. Restrict the fast path to
        # this pair of recipes so any later source or font edit still rebuilds.
        same_content=(installed_recipe,recipe)==(
            "4fcf271a2fcba251c55d8dade8f0ab9a79afa58f781e2be57037b5e40f55322d",
            "a7eef2cc63e26a5d0da1ef8847ed06253c103dc03cbc30706c63608c00f394c1")
        if installed_recipe==recipe or same_content:
            try:
                count=manage("verify",game,backup,report=False)
                if count==len(MANIFEST["originals"])+1:
                    if same_content:marker.write_text(recipe,"ascii")
                    print("已安装当前版本")
                    return
            except ValueError:
                pass
        interpreter=ensure_dependencies(cache,args.offline)
        if interpreter is not None:
            # Release the per-game lock before starting the prepared interpreter.
            return interpreter
        originals=backup/"original"
        source=originals if originals.is_dir() else game
        if source==originals:
            for rel,expected in MANIFEST["originals"].items():
                saved=originals/rel
                if not saved.is_file() or digest(saved)!=expected:
                    if not (game/rel).is_file() or digest(game/rel)!=expected:
                        raise ValueError("需要完整的 Steam 原件："+rel+"。请通过 Steam 验证游戏文件完整性，再安装汉化。")
                    atomic_copy(game/rel,saved,expected)
        with tempfile.TemporaryDirectory(prefix="stage-",dir=cache) as tmp:
            stage=Path(tmp)
            hashes=build(source,stage,cache,fonts,offline=args.offline)
            (stage/"sha256.json").write_text(json.dumps(hashes,indent=2),"utf-8")
            manage("install",game,backup,stage)
        marker.write_text(recipe,"ascii")
        print("安装完成。原件备份位于 "+str(backup))

if __name__=="__main__":
    try:
        interpreter=main()
        if isinstance(interpreter,Path):
            env=dict(os.environ,PYTHONDONTWRITEBYTECODE="1")
            raise SystemExit(subprocess.call([str(interpreter),"-B","-X","utf8",str(HERE/"patch.py"),*sys.argv[1:]],env=env))
    except (RuntimeError,ValueError,OSError,subprocess.CalledProcessError) as e:
        print(str(e),file=sys.stderr)
        raise SystemExit(1)
