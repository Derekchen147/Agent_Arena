"""
独立测试脚本：测试 OpenCode CLI 调用。
- 执行 opencode run "prompt" --format json
- 解析 NDJSON 输出，提取 text 事件拼接为完整回复
- 支持指定模型: opencode run -m provider/model "prompt"
"""
import json
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# 测试任务：(任务id, prompt)
TASKS = [
    (1, "请用一句话介绍你自己"),
    (2, "请简洁回答\n1+1等于几？"),
]

# 可选：指定模型，None 则使用 opencode 默认模型
# 示例: "anthropic/claude-sonnet-4-5", "openai/gpt-4o"
MODEL = None


def run_one(task_id: int, prompt: str, cwd: str, timeout: int = 120):
    """执行一次 opencode run，返回 (task_id, returncode, stdout, stderr)。"""
    prompt_path = None
    try:
        # 写临时文件，避免 Windows 命令行换行符问题
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        )
        tmp.write(prompt)
        tmp.close()
        prompt_path = tmp.name

        model_args = f"-m {MODEL} " if MODEL else ""

        if os.name == "nt":
            # PowerShell 读文件内容后作为变量传入，保留换行
            shell_cmd = (
                f'powershell -NoProfile -Command "'
                f"$p = Get-Content -Raw -Encoding UTF8 '{prompt_path}'; "
                f'opencode run --format json {model_args}$p"'
            )
        else:
            shell_cmd = f'opencode run --format json {model_args}"$(cat "{prompt_path}")"'

        r = subprocess.run(
            shell_cmd,
            cwd=cwd,
            capture_output=True,
            timeout=timeout,
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


def parse_text(raw: str) -> str:
    """从 opencode NDJSON 输出中拼接所有 text 事件的文本。"""
    parts = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "text":
            text = event.get("part", {}).get("text", "")
            if text:
                parts.append(text)
    return "".join(parts) if parts else raw


def parse_cost(raw: str) -> dict | None:
    """从 step_finish 事件提取 cost 和 tokens 信息。"""
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "step_finish":
            part = event.get("part", {})
            return {
                "cost": part.get("cost", 0),
                "tokens": part.get("tokens", {}),
            }
    return None


def main():
    cwd = PROJECT_ROOT
    print(f"[RUN] 工作目录: {cwd}")
    print(f"[RUN] 模型: {MODEL or '(opencode 默认)'}")
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
            text = parse_text(stdout)
            preview = text[:500] + "..." if len(text) > 500 else text
            print(f"    reply: {preview}")
            info = parse_cost(stdout)
            if info:
                tokens = info["tokens"]
                print(f"    cost: ${info['cost']:.6f}  tokens: in={tokens.get('input',0)} out={tokens.get('output',0)}")
        if stderr:
            preview = stderr[:300] + "..." if len(stderr) > 300 else stderr
            print(f"    stderr: {preview}")
    print("-" * 60)
    print("[OK] 全部成功。" if all_ok else "[FAIL] 存在失败任务。")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
