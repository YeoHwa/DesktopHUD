"""Windows 런타임(WinRT) API 를 .NET Framework(pythonnet) 으로 호출하는 도우미.

winrt 파이썬 패키지의 네이티브 파일(_winrt.pyd)은 Windows 11 '스마트 앱 컨트롤'에 막히는 경우가 있어,
이미 HUD 창(pywebview)에 쓰이고 있는 .NET Framework 를 통해 같은 API 를 쓴다.
"""
import threading

_lock = threading.Lock()
_ready = False
_as_task = None


def _init():
    global _ready, _as_task
    with _lock:
        if _ready:
            return
        import clr
        clr.AddReference("System.Runtime.WindowsRuntime")
        from System import WindowsRuntimeSystemExtensions
        for m in clr.GetClrType(WindowsRuntimeSystemExtensions).GetMethods():
            ps = m.GetParameters()
            if m.Name == "AsTask" and m.IsGenericMethod and len(ps) == 1 and ps[0].ParameterType.Name.startswith("IAsyncOperation`"):
                _as_task = m
                break
        _ready = True


def winrt_type(full_name: str, assembly: str):
    """예: winrt_type('Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager', 'Windows.Media.Control')"""
    _init()
    from System import Type
    t = Type.GetType(f"{full_name}, {assembly}, ContentType=WindowsRuntime")
    if t is None:
        raise RuntimeError(f"WinRT 형식을 찾지 못했습니다: {full_name}")
    return t


def wait(op, result_type, timeout_ms: int = 4000):
    """IAsyncOperation<T> 를 기다려 결과를 돌려준다."""
    _init()
    task = _as_task.MakeGenericMethod(result_type).Invoke(None, [op])
    if not task.Wait(timeout_ms):
        raise TimeoutError("WinRT 작업 시간 초과")
    return task.Result


def read_stream_ref(stream_ref, timeout_ms: int = 3000) -> bytes:
    """IRandomAccessStreamReference (예: 앨범 이미지) → bytes"""
    _init()
    from System.IO import MemoryStream, WindowsRuntimeStreamExtensions
    rtype = winrt_type("Windows.Storage.Streams.IRandomAccessStreamWithContentType", "Windows.Storage.Streams")
    stream = wait(stream_ref.OpenReadAsync(), rtype, timeout_ms)
    net = WindowsRuntimeStreamExtensions.AsStreamForRead(stream)
    ms = MemoryStream()
    net.CopyTo(ms)
    data = bytes(ms.ToArray())
    net.Dispose()
    return data
