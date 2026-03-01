"""
独立测试脚本：测试 Gemini CLI 调用。
- 执行 gemini -p "prompt" --output-format json --approval-mode yolo
- 工作目录：workspace/architect
- 使用线程池 + subprocess
"""
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed

# 项目根目录（脚本所在目录）
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_DIR = os.path.join(PROJECT_ROOT, "workspaces", "architect")

# 测试任务：每项 (任务id, prompt)
TASKS = [
    (1, "请用一句话介绍你自己"),
    (2, "请简洁回答\n1+1等于几？"),
]


# 代理配置（根据 ipset.sh）
PROXY_HOST = "127.0.0.1"
PROXY_PORT = "7897"


def run_one(task_id: int, prompt: str, cwd: str, timeout: int = 120):
    """在 cwd 下执行一次 Gemini CLI，返回 (task_id, returncode, stdout, stderr)。"""
    run_env = os.environ.copy()

    # 设置代理
    run_env["HTTP_PROXY"] = f"http://{PROXY_HOST}:{PROXY_PORT}"
    run_env["HTTPS_PROXY"] = f"http://{PROXY_HOST}:{PROXY_PORT}"
    run_env["ALL_PROXY"] = f"socks5://{PROXY_HOST}:{PROXY_PORT}"

    prompt_path = None

    try:
        if os.name == "nt":
            # Windows：使用临时文件避免命令行参数截断
            tmp = tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False, encoding="utf-8",
            )
            tmp.write(prompt)
            tmp.close()
            prompt_path = tmp.name

            shell_cmd = (
                f'powershell -NoProfile -Command "'
                f"$p = Get-Content -Raw -Encoding UTF8 '{prompt_path}'; "
                f'gemini -p $p --output-format json --approval-mode yolo"'
            )
            r = subprocess.run(
                shell_cmd,
                cwd=cwd,
                capture_output=True,
                timeout=timeout,
                env=run_env,
                shell=True,
            )
        else:
            # 非 Windows：直接传参
            shell_cmd = f'set HTTP_PROXY=http://127.0.0.1:7897&set HTTPS_PROXY=http://127.0.0.1:7897&gemini -p "{prompt}" --output-format json --approval-mode yolo'
            r = subprocess.run(
                shell_cmd,
                cwd=cwd,
                capture_output=True,
                timeout=timeout,
                env=run_env,
                shell=True,
            )

        stdout = (r.stdout or b"").decode("utf-8", errors="replace").strip()
        stderr = (r.stderr or b"").decode("utf-8", errors="replace").strip()
        return (task_id, r.returncode, stdout, stderr)
    except subprocess.TimeoutExpired:
        return (task_id, -1, "", "(timeout)")
    except Exception as e:
        return (task_id, -2, "", str(e))
    finally:
        if prompt_path:
            try:
                os.unlink(prompt_path)
            except OSError:
                pass


def main():
    cwd = WORKSPACE_DIR
    os.makedirs(cwd, exist_ok=True)

    print(f"[RUN] 工作目录: {cwd}")
    print(f"[RUN] 测试任务数: {len(TASKS)}")
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
                results.append((task_id, -3, "", str(e)))

    results.sort(key=lambda x: x[0])
    all_ok = True
    for task_id, ret, stdout, stderr in results:
        status = "OK" if ret == 0 else "FAIL"
        if ret != 0:
            all_ok = False
        print(f"  task_{task_id}: returncode={ret} [{status}]")
        if stdout:
            # 只打印前 500 字符，避免输出过长
            preview = stdout[:500] + "..." if len(stdout) > 500 else stdout
            print(f"    stdout: {preview}")
        if stderr:
            preview = stderr[:300] + "..." if len(stderr) > 300 else stderr
            print(f"    stderr: {preview}")
    print("-" * 60)
    print("[OK] 全部成功。" if all_ok else "[FAIL] 存在失败任务。")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()