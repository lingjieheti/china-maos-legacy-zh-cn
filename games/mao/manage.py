"""Install, verify or restore an already built patch, with per-file SHA-256 checks."""
import argparse
import csv
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from build import HERE, HELPER, MANIFEST, build, digest


def atomic_copy(source, dest, expected):
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=dest.parent,prefix=".mao-zh-",delete=False) as tmp:
        temp=Path(tmp.name)
    try:
        shutil.copyfile(source,temp)
        if digest(temp)!=expected:
            raise ValueError("复制校验失败 "+str(dest))
        os.replace(temp,dest)
    finally:
        temp.unlink(missing_ok=True)

def write_state(state, path):
    with tempfile.NamedTemporaryFile(dir=path.parent,prefix="state-",delete=False) as tmp:
        tmp.write(json.dumps(state,indent=2).encode())
        name=tmp.name
    os.replace(name,path)

def running():
    if os.name!="nt":
        return False
    tasklist=Path(os.environ["SystemRoot"])/"System32/tasklist.exe"
    listing=subprocess.check_output([str(tasklist),"/FO","CSV","/NH","/FI","IMAGENAME eq China.exe"])
    return any(row and row[0].lower()=="china.exe" for row in csv.reader(listing.decode("mbcs",errors="replace").splitlines()))

def fingerprint(path):
    return digest(path) if path.is_file() else None

def check_state(state,game,backup,originals):
    recorded=set(state.get("patched",{}))
    # 1.2.1 added the language-selector artwork. Old receipts still describe
    # precisely the files that their version installed and can restore.
    artwork={"sharedassets1.assets","sharedassets5.assets"}
    if recorded not in (set(originals),set(originals)-artwork,set(originals)-{"sharedassets5.assets"}):
        raise ValueError("安装记录与本版本的文件清单不符")
    if Path(state["game"])!=game:
        # Steam can move an installation, backup folder included. Only reuse a
        # relocated backup when every original matches this supported Steam build.
        for n in recorded:
            if originals[n] is not None and fingerprint(backup/"original"/n)!=originals[n]:
                raise ValueError("移动后的游戏缺少完整原件备份："+n)

def manage(action, game, backup, stage=None, report=True):
    game=game.resolve()
    backup=backup.resolve()
    originals={**MANIFEST["originals"],HELPER:None}
    if game.name.casefold()!="china_data" or not (game.parent/"China.exe").is_file():
        raise ValueError("请指定 China.exe 旁的 China_Data 目录")
    if backup==game or game in backup.parents:
        raise ValueError("备份目录须位于游戏目录外")
    state_path=backup/"installed.json"
    if action!="verify" and running():
        raise RuntimeError("请先退出《毛的遗产》")
    if action=="install":
        if stage is None:
            raise ValueError("缺少 --stage")
        stage=stage.resolve()
        target=json.loads((stage/"sha256.json").read_text("utf-8"))
        if set(target)!=set(originals) or any(fingerprint(stage/n)!=h for n,h in target.items()):
            raise ValueError("构建文件校验失败")
        if state_path.is_file():
            state=json.loads(state_path.read_text("utf-8"))
            check_state(state,game,backup,originals)
            previous=state["patched"]
        else:
            previous={}
        current={n:fingerprint(game/n) for n in originals}
        if any(current[n] not in (h,previous.get(n,h),target[n]) for n,h in originals.items()):
            raise ValueError("游戏文件已被其他版本或补丁改动，已保留现场")
        backup.mkdir(parents=True,exist_ok=True)
        for n,h in originals.items():
            if h is None:continue
            saved=backup/"original"/n
            if not saved.exists() and current[n]==h:
                atomic_copy(game/n,saved,h)
            if fingerprint(saved)!=h:
                raise ValueError("原件备份缺失或损坏 "+n)
        # Journal both valid generations before any replacement (re-run after interruption).
        if state_path.is_file() and previous!=target and any(current[n] not in (h,previous.get(n,h)) for n,h in originals.items()):
            raise ValueError("请先还原上一次未完成的安装")
        state={"game":str(game),"patched":target,"previous":previous}
        write_state(state,state_path)
        try:
            for n,h in target.items():
                if current[n]!=h:atomic_copy(stage/n,game/n,h)
        except Exception:
            for n,h in originals.items():
                if h is None:
                    if fingerprint(game/n)==target[n]:(game/n).unlink()
                else:atomic_copy(backup/"original"/n,game/n,h)
            raise
    if not state_path.is_file():
        raise ValueError("找不到安装记录 "+str(state_path))
    state=json.loads(state_path.read_text("utf-8"))
    check_state(state,game,backup,originals)
    if action=="restore":
        originals={n:originals[n] for n in state["patched"]}
        for n,h in originals.items():
            if fingerprint(game/n) not in (h,state["patched"][n],state.get("previous",{}).get(n,h)):
                raise ValueError("游戏版本已变化，已保留现场 "+n)
            if h is not None and fingerprint(backup/"original"/n)!=h:
                raise ValueError("备份校验失败 "+n)
        for n,h in originals.items():
            if h is None:(game/n).unlink(missing_ok=True)
            else:atomic_copy(backup/"original"/n,game/n,h)
        target=originals
    else:
        target=state["patched"]
    for n,h in target.items():
        if fingerprint(game/n)!=h:
            raise ValueError("游戏文件校验失败："+n+"。请通过 Steam 验证游戏文件完整性，再安装汉化。")
    if action=="verify":
        for n in target:
            if originals[n] is not None and fingerprint(backup/"original"/n)!=originals[n]:
                raise ValueError("原件备份缺失或损坏："+n+"。请先保留备份，通过 Steam 验证游戏文件完整性。")
    if report:print(f"{action}: {len(target)} files verified")
    return len(target)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=["install","restore","verify"])
    parser.add_argument("--game-data",required=True,type=Path)
    parser.add_argument("--stage",type=Path)
    parser.add_argument("--backup",required=True,type=Path)
    args=parser.parse_args()
    manage(args.action,args.game_data,args.backup,args.stage)
