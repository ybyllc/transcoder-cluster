"""Tk compatibility helpers for legacy macOS system Python."""

import os
import sys
import tkinter as tk
import tkinter.ttk as native_ttk
from tkinter.constants import BOTH, LEFT, RIGHT, VERTICAL, Y


def _is_legacy_macos_system_python() -> bool:
    executable = os.path.realpath(sys.executable)
    return sys.platform == "darwin" and (
        executable == "/usr/bin/python3"
        or executable.startswith("/Library/Developer/CommandLineTools/")
    )


def ensure_supported_tk() -> None:
    """Fail clearly instead of opening a blank window with Apple Tk 8.5."""
    if sys.platform == "darwin" and tk.TkVersion < 8.6:
        raise RuntimeError(
            f"当前 Python 使用 Tk {tk.TkVersion}，该版本在 macOS 上会显示白屏。"
            "请安装 Homebrew Python 和 Tk：brew install python@3.14 python-tk@3.14，"
            "然后用 $(brew --prefix)/bin/python3 重新创建虚拟环境。"
        )


def _drop_bootstyle(kwargs):
    kwargs.pop("bootstyle", None)
    return kwargs


def _wrap_widget(base_class):
    class Widget(base_class):
        def __init__(self, master=None, *args, **kwargs):
            super().__init__(master, *args, **_drop_bootstyle(kwargs))

        def configure(self, cnf=None, **kwargs):
            if cnf in ("bootstyle", "style"):
                return ""
            return super().configure(cnf, **_drop_bootstyle(kwargs))

        config = configure

    return Widget


class _NativeWindow(tk.Tk):
    def __init__(
        self,
        title="tk",
        themename=None,
        iconphoto=None,
        size=None,
        position=None,
        minsize=None,
        maxsize=None,
        resizable=None,
        **kwargs,
    ):
        ignored = {
            "hdpi",
            "scaling",
            "transient",
            "overrideredirect",
            "alpha",
        }
        for key in ignored:
            kwargs.pop(key, None)
        super().__init__(**kwargs)
        self.title(title)
        if size is not None:
            self.geometry(f"{size[0]}x{size[1]}")
        if position is not None:
            self.geometry(f"+{position[0]}+{position[1]}")
        if minsize is not None:
            self.minsize(*minsize)
        if maxsize is not None:
            self.maxsize(*maxsize)
        if resizable is not None:
            self.resizable(*resizable)


class _NativeTtk:
    Window = _NativeWindow
    Frame = _wrap_widget(native_ttk.Frame)
    Labelframe = _wrap_widget(native_ttk.Labelframe)
    LabelFrame = Labelframe
    Button = _wrap_widget(native_ttk.Button)
    Label = _wrap_widget(native_ttk.Label)
    Entry = _wrap_widget(native_ttk.Entry)
    Combobox = _wrap_widget(native_ttk.Combobox)
    Panedwindow = _wrap_widget(native_ttk.Panedwindow)
    PanedWindow = Panedwindow
    Treeview = _wrap_widget(native_ttk.Treeview)
    Progressbar = _wrap_widget(native_ttk.Progressbar)
    Radiobutton = _wrap_widget(native_ttk.Radiobutton)
    Checkbutton = _wrap_widget(native_ttk.Checkbutton)
    Scrollbar = _wrap_widget(native_ttk.Scrollbar)

    StringVar = tk.StringVar
    IntVar = tk.IntVar
    BooleanVar = tk.BooleanVar


class _NativeScrolledText(tk.Frame):
    """Small native replacement for ttkbootstrap ScrolledText on old Apple Tk."""

    def __init__(self, master=None, autohide=False, vbar=True, hbar=False, **kwargs):
        kwargs.pop("bootstyle", None)
        kwargs.pop("padding", None)
        super().__init__(master)
        self.text = tk.Text(self, **kwargs)
        # Use classic Tk scrollbars: some Apple Tk builds reject ttk's style option.
        self._vbar = tk.Scrollbar(self, orient=VERTICAL, command=self.text.yview) if vbar else None
        self._hbar = tk.Scrollbar(self, orient="horizontal", command=self.text.xview) if hbar else None
        if self._vbar:
            self.text.configure(yscrollcommand=self._vbar.set)
            self._vbar.pack(side=RIGHT, fill=Y)
        if self._hbar:
            self.text.configure(xscrollcommand=self._hbar.set)
            self._hbar.pack(side="bottom", fill="x")
        self.text.pack(side=LEFT, fill=BOTH, expand=True)

    def insert(self, *args, **kwargs):
        return self.text.insert(*args, **kwargs)

    def see(self, *args, **kwargs):
        return self.text.see(*args, **kwargs)


def use_native_ttk_on_legacy_macos(ttk_module):
    """Return native ttk on old Apple Tk, otherwise keep ttkbootstrap."""
    if _is_legacy_macos_system_python():
        return _NativeTtk
    return ttk_module


def use_native_scrolledtext_on_legacy_macos(scrolledtext_module):
    """Return a native ScrolledText-compatible class on legacy Apple Tk."""
    if _is_legacy_macos_system_python():
        return _NativeScrolledText
    return scrolledtext_module
