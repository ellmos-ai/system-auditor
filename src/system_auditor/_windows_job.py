"""Windows audit containment: a trusted pipe gate enters a non-breakaway job.

Job semantics: https://learn.microsoft.com/windows/win32/procthread/job-objects
No producer code runs before job assignment. The job handle is not inherited.
"""

from __future__ import annotations

import ctypes
import json
import sys
import time
from ctypes import wintypes

GATE = """
import json,os,subprocess,sys
def exact(size):
    result=bytearray()
    while len(result)<size:
        part=os.read(0,size-len(result))
        if not part:
            raise SystemExit(86)
        result.extend(part)
    return bytes(result)
size=int.from_bytes(exact(4),'big')
if not 0<size<=1048576:
    raise SystemExit(86)
argv=json.loads(exact(size))
if type(argv) is not list or not argv or not all(type(v) is str for v in argv):
    raise SystemExit(86)
raise SystemExit(subprocess.call(argv,stdin=sys.stdin.buffer,
    stdout=sys.stdout.buffer,stderr=sys.stderr.buffer,close_fds=True))
"""


def frame_command(command: list[str], payload: bytes) -> tuple[list[str], bytes]:
    if type(command) is not list or not command or not all(type(v) is str for v in command):
        raise ValueError("plain native command argv required")
    encoded = json.dumps(command, ensure_ascii=True).encode("ascii")
    if len(encoded) > 1024 * 1024:
        raise ValueError("native command argv exceeds gate bound")
    framed = len(encoded).to_bytes(4, "big") + encoded + payload
    return [sys.executable, "-I", "-S", "-B", "-c", GATE], framed


class _BasicLimits(ctypes.Structure):
    _fields_ = [
        ("process_time", ctypes.c_longlong), ("job_time", ctypes.c_longlong),
        ("flags", wintypes.DWORD), ("minimum_working_set", ctypes.c_size_t),
        ("maximum_working_set", ctypes.c_size_t), ("active_process_limit", wintypes.DWORD),
        ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD),
        ("scheduling", wintypes.DWORD),
    ]


class _IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in (
        "read_ops", "write_ops", "other_ops", "read_bytes", "write_bytes", "other_bytes",
    )]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [
        ("basic", _BasicLimits), ("io", _IoCounters),
        ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
        ("peak_process_memory", ctypes.c_size_t), ("peak_job_memory", ctypes.c_size_t),
    ]


class _Accounting(ctypes.Structure):
    _fields_ = [
        ("user_time", ctypes.c_longlong), ("kernel_time", ctypes.c_longlong),
        ("period_user_time", ctypes.c_longlong), ("period_kernel_time", ctypes.c_longlong),
        ("page_faults", wintypes.DWORD), ("total", wintypes.DWORD),
        ("active", wintypes.DWORD), ("terminated", wintypes.DWORD),
    ]


class WindowsAuditJob:
    """Own an anonymous kill-on-close job; never signal a PID found by lookup."""

    def __init__(self):
        self.handle = None
        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        signatures = {
            "CreateJobObjectW": ([ctypes.c_void_p, wintypes.LPCWSTR], wintypes.HANDLE),
            "SetInformationJobObject": (
                [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD], wintypes.BOOL,
            ),
            "AssignProcessToJobObject": ([wintypes.HANDLE, wintypes.HANDLE], wintypes.BOOL),
            "TerminateJobObject": ([wintypes.HANDLE, wintypes.UINT], wintypes.BOOL),
            "QueryInformationJobObject": (
                [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
                 ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL,
            ),
            "CloseHandle": ([wintypes.HANDLE], wintypes.BOOL),
        }
        for name, (args, result) in signatures.items():
            function = getattr(self.api, name)
            function.argtypes = args
            function.restype = result

    @staticmethod
    def checked(value):
        if not value:
            raise ctypes.WinError(ctypes.get_last_error())
        return value

    def __enter__(self):
        self.handle = self.checked(self.api.CreateJobObjectW(None, None))
        limits = _ExtendedLimits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE; no breakaway.
        try:
            self.checked(self.api.SetInformationJobObject(
                self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits),
            ))
        except BaseException:
            self.api.CloseHandle(self.handle)
            self.handle = None
            raise
        return self

    def assign(self, process):
        # CPython's Popen retains the original Windows process HANDLE.
        self.checked(self.api.AssignProcessToJobObject(self.handle, int(process._handle)))

    def terminate_and_wait(self, timeout: float = 20):
        self.checked(self.api.TerminateJobObject(self.handle, 1))
        deadline = time.monotonic() + timeout
        while True:
            accounting = _Accounting()
            self.checked(self.api.QueryInformationJobObject(
                self.handle, 1, ctypes.byref(accounting), ctypes.sizeof(accounting), None,
            ))
            if accounting.active == 0:
                return
            if time.monotonic() >= deadline:
                raise TimeoutError("native audit job termination is unconfirmed")
            time.sleep(0.01)

    def __exit__(self, *_exc):
        if self.handle is not None:
            handle, self.handle = self.handle, None
            self.checked(self.api.CloseHandle(handle))
