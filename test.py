"""
独立测试脚本：在指定工作目录下并行运行多轮 Cursor CLI 无头模式。
- 并行执行多组：agent -p "prompt" --output-format json
- 工作目录：workspace/architect
- 使用线程池 + subprocess（每任务独立 cwd，避免 os.chdir 冲突）
"""
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

# 项目根目录（脚本所在目录）
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_DIR = os.path.join(PROJECT_ROOT, "workspace", "architect")

# 并行任务：每项 (任务id, prompt)
TASKS = [
    (1, "hello"),
    (2, "say hi in one word"),
    (3, "reply with ok"),
]


def run_one(task_id: int, prompt: str, cwd: str, timeout: int = 120):
    """在 cwd 下执行一次 agent，返回 (task_id, returncode, stdout_preview)。"""
    # Windows 下不用 shell 时找不到 agent（不走 PATH），故用 shell=True + 命令字符串
    safe_prompt = prompt.replace('"', '\\"')
    cmd_str = f'agent -p "{safe_prompt}" --output-format json --trust'
    try:
        r = subprocess.run(
            cmd_str,
            cwd=cwd,
            capture_output=True,
            timeout=timeout,
            env=os.environ.copy(),
            shell=True,
        )
        out = (r.stdout or b"").decode("utf-8", errors="replace").strip()[:200]
        return (task_id, r.returncode, out)
    except subprocess.TimeoutExpired:
        return (task_id, -1, "(timeout)")
    except Exception as e:
        return (task_id, -2, str(e))


def main():
    cwd = WORKSPACE_DIR
    os.makedirs(cwd, exist_ok=True)

    print(f"[RUN] 工作目录: {cwd}")
    print(f"[RUN] 并行任务数: {len(TASKS)}")
    print("-" * 60)

    results = []
    with ThreadPoolExecutor(max_workers=len(TASKS)) as executor:
        futures = {
            executor.submit(run_one, tid, prompt, cwd): tid
            for tid, prompt in TASKS
        }
        for fut in as_completed(futures):
            task_id = futures[fut]
            try:
                results.append(fut.result())
            except Exception as e:
                results.append((task_id, -3, str(e)))

    results.sort(key=lambda x: x[0])
    all_ok = True
    for task_id, ret, preview in results:
        status = "OK" if ret == 0 else "FAIL"
        if ret != 0:
            all_ok = False
        print(f"  task_{task_id}: returncode={ret} [{status}]")
        if preview:
            print(f"    stdout_preview: {preview}")
    print("-" * 60)
    print("[OK] 全部成功。" if all_ok else "[FAIL] 存在失败任务。")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
