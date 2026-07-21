"""Windows 前台窗口事实适配器。

该模块只读取用户主动启动任务期间的前台窗口元数据；不截图、不记录键盘、
不访问浏览器历史，也不对学习状态作推断。
"""

from __future__ import annotations

import ctypes
import sys
from dataclasses import dataclass
from typing import Protocol


class ForegroundCaptureUnavailable(RuntimeError):
    """Raised when Windows cannot provide a usable foreground window."""


@dataclass(frozen=True)
class ForegroundWindowSample:
    window_handle: int
    process_id: int
    process_path: str
    window_title: str
    window_class: str

    @property
    def fingerprint(self) -> tuple[int, int, str, str, str]:
        return (
            self.window_handle,
            self.process_id,
            self.process_path,
            self.window_title,
            self.window_class,
        )


class ForegroundWindowProbe(Protocol):
    def read_foreground_window(self) -> ForegroundWindowSample: ...


class WindowsForegroundWindowProbe:
    """Read the active top-level window through documented Win32 APIs."""

    _PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

    def read_foreground_window(self) -> ForegroundWindowSample:
        if sys.platform != "win32":
            raise ForegroundCaptureUnavailable("windows_foreground_capture_requires_win32")

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        handle = int(user32.GetForegroundWindow())
        if handle == 0:
            raise ForegroundCaptureUnavailable("foreground_window_unavailable")

        title_length = int(user32.GetWindowTextLengthW(handle))
        title_buffer = ctypes.create_unicode_buffer(title_length + 1)
        user32.GetWindowTextW(handle, title_buffer, len(title_buffer))
        class_buffer = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(handle, class_buffer, len(class_buffer))

        process_id = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(handle, ctypes.byref(process_id))
        if process_id.value == 0:
            raise ForegroundCaptureUnavailable("foreground_process_unavailable")

        process_path = self._process_path(kernel32, int(process_id.value))
        return ForegroundWindowSample(
            window_handle=handle,
            process_id=int(process_id.value),
            process_path=process_path,
            window_title=title_buffer.value,
            window_class=class_buffer.value,
        )

    def _process_path(self, kernel32: object, process_id: int) -> str:
        process_handle = kernel32.OpenProcess(
            self._PROCESS_QUERY_LIMITED_INFORMATION, False, process_id
        )
        if not process_handle:
            return ""
        try:
            buffer = ctypes.create_unicode_buffer(32768)
            size = ctypes.c_ulong(len(buffer))
            if not kernel32.QueryFullProcessImageNameW(
                process_handle, 0, buffer, ctypes.byref(size)
            ):
                return ""
            return buffer.value
        finally:
            kernel32.CloseHandle(process_handle)
