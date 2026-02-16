"""
独立测试脚本：仅测试在指定工作目录下运行 Cursor CLI 无头模式。
- 命令：agent -p "hello" --output-format json
- 工作目录：workspace/architect
- 使用 os.system：输出直接打到控制台，最后打印返回码
"""
import os
import sys

# 项目根目录（脚本所在目录）
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_DIR = os.path.join(PROJECT_ROOT, "workspace", "architect")


def main():
    # 命令行字符串（Windows 下 agent -p "hello" --output-format json）
    cmd_str = 'agent -p "hello" --output-format json'
    cwd = WORKSPACE_DIR

    os.makedirs(cwd, exist_ok=True)

    print(f"[RUN] cmd: {cmd_str}")
    print(f"[RUN] cwd: {cwd}")
    print("-" * 60)

    old_cwd = os.getcwd()
    try:
        os.chdir(cwd)
        ret = os.system(cmd_str)
    finally:
        os.chdir(old_cwd)

    print("-" * 60)
    print(f"[RETURNCODE] {ret}")

    if ret == 0:
        print("[OK] Cursor CLI 返回 0。")
    else:
        print("[FAIL] 返回码非 0，请根据上方控制台输出排查。")
    sys.exit(0 if ret == 0 else 1)


if __name__ == "__main__":
    main()
