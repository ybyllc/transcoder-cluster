"""GUI 模块 - 图形用户界面"""

def controller_main():
    """懒加载主控端 GUI 入口，避免 -m 执行时重复导入告警。"""
    from gui.controller_app import main

    return main()


def worker_main():
    """懒加载 Worker GUI 入口，避免 -m 执行时重复导入告警。"""
    from gui.worker_app import main

    return main()

__all__ = ["controller_main", "worker_main"]
