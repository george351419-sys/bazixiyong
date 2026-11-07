"""统一回归入口：python3 tools/run_regression.py。失败即返回非零。"""
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
COMMANDS=[
    [sys.executable,'tests/test_geju.py'],
    [sys.executable,'tests/test_wangshuai.py'],
    [sys.executable,'tests/test_wangshuai_invariants.py'],
    [sys.executable,'tests/test_tiaohou.py'],
    [sys.executable,'-m','unittest','tests/test_arbitration.py','tests/test_wangshuai_state.py','tests/test_wangshuai_review.py','tests/test_web_render.py','tests/test_geju_revision.py','tests/test_calendar_regression.py','-q'],
]
if shutil.which('node'):
    COMMANDS.append(['node','--check','web/app.js'])
else:
    raise SystemExit('缺少Node：无法完成网页JavaScript语法检查。')
for command in COMMANDS:
    print('运行：'+' '.join(command),flush=True)
    subprocess.run(command,cwd=ROOT,check=True,timeout=180)
print('全部回归通过。')
