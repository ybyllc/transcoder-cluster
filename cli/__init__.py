"""CLI 命令行入口模块"""

def controller_main():
    """懒加载主控端 CLI 入口，避免 -m 执行时重复导入告警。"""
    from cli.controller import main

    return main()


def worker_main():
    """懒加载 Worker CLI 入口，避免 -m 执行时重复导入告警。"""
    from cli.worker import main

    return main()

__all__ = ["worker_main", "controller_main"]
