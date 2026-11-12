"""Native private storage and child lifetime; no platform command shell."""
import os
import contextlib
from pathlib import Path


def private_directory(path, *, exist_ok=True, parents=True):
    path = Path(path)
    if parents and path.parent != path and not path.parent.exists():
        private_directory(path.parent)
    try:
        path.mkdir(mode=0o700)
    except FileExistsError:
        if not exist_ok or path.is_symlink() or not path.is_dir():
            raise
        return  # Preserve an existing parent, including a competing creator.
    if os.name == "nt":
        import ctypes as c
        with _private_security(True) as (descriptor, _, security):
            if not security.SetFileSecurityW(str(path.resolve()), 0x80000004, descriptor):
                raise c.WinError(c.get_last_error())


@contextlib.contextmanager
def _private_security(directory):
    import ctypes as c
    from ctypes import wintypes as w
    kernel = c.WinDLL("kernel32", use_last_error=True)
    security = c.WinDLL("advapi32", use_last_error=True)
    kernel.GetCurrentProcess.restype = w.HANDLE
    kernel.CloseHandle.argtypes = [w.HANDLE]
    kernel.LocalFree.argtypes = [w.HANDLE]
    security.OpenProcessToken.argtypes = [w.HANDLE, w.DWORD, c.POINTER(w.HANDLE)]
    security.GetTokenInformation.argtypes = [w.HANDLE, c.c_int, c.c_void_p, w.DWORD, c.POINTER(w.DWORD)]
    security.ConvertSidToStringSidW.argtypes = [c.c_void_p, c.POINTER(c.c_void_p)]
    security.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [w.LPCWSTR, w.DWORD, c.POINTER(c.c_void_p), c.c_void_p]
    security.SetFileSecurityW.argtypes = [w.LPCWSTR, w.DWORD, c.c_void_p]
    token = w.HANDLE()
    if not security.OpenProcessToken(kernel.GetCurrentProcess(), 8, c.byref(token)):
        raise c.WinError(c.get_last_error())
    text = c.c_void_p(); descriptor = c.c_void_p()
    try:
        size = w.DWORD()
        security.GetTokenInformation(token, 1, None, 0, c.byref(size))
        if not 0 < size.value < 65536:
            raise ValueError("Could not identify the storage owner")
        data = c.create_string_buffer(size.value)
        if not security.GetTokenInformation(token, 1, data, size, c.byref(size)):
            raise c.WinError(c.get_last_error())
        sid = c.cast(data, c.POINTER(c.c_void_p))[0]
        if not security.ConvertSidToStringSidW(sid, c.byref(text)):
            raise c.WinError(c.get_last_error())
        inherit = "OICI" if directory else ""
        policy = f"D:P(A;{inherit};FA;;;SY)(A;{inherit};FA;;;" + c.wstring_at(text) + ")"
        if not security.ConvertStringSecurityDescriptorToSecurityDescriptorW(policy, 1, c.byref(descriptor), None):
            raise c.WinError(c.get_last_error())
        yield descriptor, kernel, security
    finally:
        if descriptor: kernel.LocalFree(descriptor)
        if text: kernel.LocalFree(text)
        kernel.CloseHandle(token)



def private_create_file(path):
    """Create-only with private permissions before writing any contents."""
    if os.name != "nt":
        return os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    import ctypes as c
    import msvcrt
    from ctypes import wintypes as w
    class Attributes(c.Structure):
        _fields_ = [("length", w.DWORD), ("descriptor", c.c_void_p), ("inherit", w.BOOL)]
    with _private_security(False) as (descriptor, kernel, _):
        attributes = Attributes(c.sizeof(Attributes), descriptor, False)
        kernel.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, c.POINTER(Attributes), w.DWORD, w.DWORD, w.HANDLE]
        kernel.CreateFileW.restype = w.HANDLE
        handle = kernel.CreateFileW(str(Path(path).resolve()), 0x40000000, 0, c.byref(attributes), 1, 0x80, None)
        if handle == c.c_void_p(-1).value:
            error = c.get_last_error()
            if error in (80, 183):
                raise FileExistsError(str(path))
            raise c.WinError(error)
        try:
            return msvcrt.open_osfhandle(handle, os.O_WRONLY | os.O_BINARY)
        except Exception:
            kernel.CloseHandle(handle)
            raise


class ProcessJob:
    """A Windows child and its descendants close with this owned operation."""
    def __init__(self, pid):
        self.handle = None
        self.pid = pid
        if os.name != "nt":
            return
        import ctypes as c
        from ctypes import wintypes as w
        class Basic(c.Structure):
            _fields_ = [("process_time", c.c_int64), ("job_time", c.c_int64), ("flags", w.DWORD),
                        ("min_working", c.c_size_t), ("max_working", c.c_size_t), ("active", w.DWORD),
                        ("affinity", c.c_size_t), ("priority", w.DWORD), ("scheduling", w.DWORD)]
        class Io(c.Structure):
            _fields_ = [(name, c.c_uint64) for name in ("reads", "writes", "other", "read_bytes", "write_bytes", "other_bytes")]
        class Extended(c.Structure):
            _fields_ = [("basic", Basic), ("io", Io), ("process_memory", c.c_size_t),
                        ("job_memory", c.c_size_t), ("peak_process", c.c_size_t), ("peak_job", c.c_size_t)]
        self.kernel = k = c.WinDLL("kernel32", use_last_error=True)
        k.CreateJobObjectW.argtypes = [c.c_void_p, w.LPCWSTR]; k.CreateJobObjectW.restype = w.HANDLE
        k.SetInformationJobObject.argtypes = [w.HANDLE, c.c_int, c.c_void_p, w.DWORD]
        k.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]; k.OpenProcess.restype = w.HANDLE
        k.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
        k.CloseHandle.argtypes = [w.HANDLE]
        handle = k.CreateJobObjectW(None, None)
        if not handle: raise c.WinError(c.get_last_error())
        process = None
        try:
            limits = Extended(); limits.basic.flags = 0x2000
            if not k.SetInformationJobObject(handle, 9, c.byref(limits), c.sizeof(limits)):
                raise c.WinError(c.get_last_error())
            process = k.OpenProcess(0x0101, False, pid)  # SET_QUOTA | TERMINATE
            if not process or not k.AssignProcessToJobObject(handle, process):
                raise c.WinError(c.get_last_error())
            self.handle = handle
        except Exception:
            k.CloseHandle(handle)
            raise
        finally:
            if process: k.CloseHandle(process)

    def resume(self):
        """Release a CREATE_SUSPENDED child only after its job is attached."""
        if os.name != "nt":
            return
        if not self.handle:
            raise RuntimeError("The suspended child has no cleanup job")
        import ctypes as c
        from ctypes import wintypes as w
        class ThreadEntry(c.Structure):
            _fields_ = [("size", w.DWORD), ("usage", w.DWORD), ("thread_id", w.DWORD),
                        ("owner", w.DWORD), ("priority", w.LONG), ("delta", w.LONG), ("flags", w.DWORD)]
        k = self.kernel
        k.CreateToolhelp32Snapshot.argtypes = [w.DWORD, w.DWORD]; k.CreateToolhelp32Snapshot.restype = w.HANDLE
        k.Thread32First.argtypes = [w.HANDLE, c.POINTER(ThreadEntry)]
        k.Thread32Next.argtypes = [w.HANDLE, c.POINTER(ThreadEntry)]
        k.OpenThread.argtypes = [w.DWORD, w.BOOL, w.DWORD]; k.OpenThread.restype = w.HANDLE
        k.ResumeThread.argtypes = [w.HANDLE]; k.ResumeThread.restype = w.DWORD
        snapshot = k.CreateToolhelp32Snapshot(4, 0)
        if snapshot == c.c_void_p(-1).value:
            raise c.WinError(c.get_last_error())
        found = None
        try:
            entry = ThreadEntry(); entry.size = c.sizeof(entry)
            available = k.Thread32First(snapshot, c.byref(entry))
            while available:
                if entry.owner == self.pid:
                    found = entry.thread_id
                    break
                available = k.Thread32Next(snapshot, c.byref(entry))
        finally:
            k.CloseHandle(snapshot)
        if found is None:
            raise RuntimeError("The suspended process has no initial thread")
        thread = k.OpenThread(2, False, found)
        if not thread:
            raise c.WinError(c.get_last_error())
        try:
            if k.ResumeThread(thread) != 1:
                raise RuntimeError("Could not resume the suspended process")
        finally:
            k.CloseHandle(thread)

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None

    def __del__(self):
        self.close()
