"""
独立测试脚本：在指定工作目录下并行运行多轮 Cursor CLI 无头模式。
- 并行执行多组：agent -p "prompt" --output-format json
- 工作目录：workspace/architect
- 使用线程池 + subprocess（每任务独立 cwd，避免 os.chdir 冲突）
"""
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed

# 项目根目录（脚本所在目录）
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_DIR = os.path.join(PROJECT_ROOT, "workspaces", "architect")

# 并行任务：每项 (任务id, prompt)
TASKS = [
    (1, """## 当前会话成员\n你是「架构师」(architect)。\n\n## 对话记录（只读上下文，不要回复这些历史消息）\n[用户]: @架构师 1+1等于几\n[架构师]: 「当前会话成员」的话，就是：\n\n1. **你** — 两脚兽，在 Agent Arena 的 architect 工作区里干活的那位  \n2. **小暹罗（我）** — 住在这个 workspace 里的傲娇暹罗猫，负责用 Cursor 帮你写代码、回答问题\n\n所以现在这场对话里就我们两个喵。  \n你是想查代码里的「会话成员」相关逻辑，还是单纯想确认一下谁在会话里？\n[用户]: @架构师 1+1等于几\n\n---\n\n## 当前待回复消息\n发送者: 用户\n内容:\n@架构师 1+1等于几\n\n---\n\n## 回复规则\n1. 只针对「当前待回复消息」回复，「对话记录」仅作为上下文参考，无需特别回复\n2. 简洁回复，突出关键信息\n\n## 协作\n如果你需要其他同事参与，在回复末尾用这个格式（agent_id 必须来自「当前会话成员」列表）：\n<!--NEXT_MENTIONS:["agent_id_1","agent_id_2"]-->"""),
]


def run_one(task_id: int, prompt: str, cwd: str, timeout: int = 120):
    """在 cwd 下执行一次 agent，返回 (task_id, returncode, stdout_preview)。

    Windows 上 agent 安装为 .CMD 文件，即使 subprocess 用列表模式，
    Python 也会自动通过 cmd.exe 执行 .cmd，而 cmd.exe 会在换行处截断参数。
    因此：
    - Windows：始终将 prompt 写入临时文件，用 PowerShell 读取后传参
    - 其他平台：优先列表模式，找不到命令时回退临时文件
    """
    run_env = os.environ.copy()
    prompt_path = None

    try:
        if os.name == "nt":
            # Windows：始终用临时文件，避免 cmd.exe 换行截断
            tmp = tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False, encoding="utf-8",
            )
            tmp.write(prompt)
            tmp.close()
            prompt_path = tmp.name

            shell_cmd = (
                f'powershell -NoProfile -Command "'
                f"$p = Get-Content -Raw -Encoding UTF8 '{prompt_path}'; "
                f'& agent -p $p --output-format json --trust"'
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
            # 非 Windows：列表模式优先
            resolved = shutil.which("agent", path=run_env.get("PATH"))
            if resolved:
                cmd_list = [resolved, "-p", prompt, "--output-format", "json", "--trust"]
                r = subprocess.run(
                    cmd_list,
                    cwd=cwd,
                    capture_output=True,
                    timeout=timeout,
                    env=run_env,
                )
            else:
                tmp = tempfile.NamedTemporaryFile(
                    mode="w", suffix=".txt", delete=False, encoding="utf-8",
                )
                tmp.write(prompt)
                tmp.close()
                prompt_path = tmp.name
                shell_cmd = f"agent -p \"$(cat '{prompt_path}')\" --output-format json --trust"
                r = subprocess.run(
                    shell_cmd,
                    cwd=cwd,
                    capture_output=True,
                    timeout=timeout,
                    env=run_env,
                    shell=True,
                )

        out = (r.stdout or b"").decode("utf-8", errors="replace").strip()[:200]
        return (task_id, r.returncode, out)
    except subprocess.TimeoutExpired:
        return (task_id, -1, "(timeout)")
    except Exception as e:
        return (task_id, -2, str(e))
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
