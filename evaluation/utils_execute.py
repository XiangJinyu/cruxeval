import contextlib
import faulthandler
import io
import multiprocessing
import os
import platform
import tempfile
from threading import Timer
import traceback
import sys
import shutil


class TimeoutException(Exception):
    pass


class WriteOnlyStringIO(io.StringIO):
    def read(self, *args, **kwargs):
        raise OSError

    def readline(self, *args, **kwargs):
        raise OSError

    def readlines(self, *args, **kwargs):
        raise OSError

    def readable(self, *args, **kwargs):
        return False


class redirect_stdin(contextlib._RedirectStream):
    _stream = "stdin"


@contextlib.contextmanager
def create_tempdir():
    with tempfile.TemporaryDirectory() as dirname:
        with chdir(dirname):
            yield dirname


@contextlib.contextmanager
def chdir(root):
    if root == ".":
        yield
        return
    cwd = os.getcwd()
    os.chdir(root)
    try:
        yield
    except BaseException as exc:
        raise exc
    finally:
        os.chdir(cwd)


@contextlib.contextmanager
def swallow_io():
    stream = WriteOnlyStringIO()
    with contextlib.redirect_stdout(stream):
        with contextlib.redirect_stderr(stream):
            with redirect_stdin(stream):
                yield


def reliability_guard(maximum_memory_bytes=None):
    if maximum_memory_bytes is not None and platform.system() != "Windows":
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (maximum_memory_bytes, maximum_memory_bytes))
        resource.setrlimit(resource.RLIMIT_DATA, (maximum_memory_bytes, maximum_memory_bytes))
        if platform.system() != "Darwin":
            resource.setrlimit(resource.RLIMIT_STACK, (maximum_memory_bytes, maximum_memory_bytes))

    faulthandler.disable()

    import builtins
    builtins.exit = None
    builtins.quit = None

    os.environ["OMP_NUM_THREADS"] = "1"

    os.kill = None
    os.system = None
    os.putenv = None
    os.remove = None
    os.removedirs = None
    os.rmdir = None
    os.fchdir = None
    os.setuid = None
    os.fork = None
    os.forkpty = None
    os.killpg = None
    os.rename = None
    os.renames = None
    os.truncate = None
    os.replace = None
    os.unlink = None
    os.fchmod = None
    os.fchown = None
    os.chmod = None
    os.chown = None
    os.chroot = None
    os.lchflags = None
    os.lchmod = None
    os.lchown = None
    os.getcwd = None
    os.chdir = None

    shutil.rmtree = None
    shutil.move = None
    shutil.chown = None

    import subprocess
    subprocess.Popen = None

    __builtins__["help"] = None

    import sys
    sys.modules["ipdb"] = None
    sys.modules["joblib"] = None
    sys.modules["resource"] = None
    sys.modules["psutil"] = None
    sys.modules["tkinter"] = None


def unsafe_execute(code, result, timeout):
    try:
        exec(code)
        result.append("passed")
    except SyntaxError as e:
        error_class = e.__class__.__name__
        detail = e.args[0]
        line_number = e.lineno
        result.append("failed: {} at line {}: {}".format(error_class, line_number, detail))
        result.append("Offending line: {}".format(code.split('\n')[line_number - 1]))
    except Exception as e:
        error_class = e.__class__.__name__
        detail = str(e)
        _, _, tb = sys.exc_info()
        line_number = traceback.extract_tb(tb)[-1][1]
        result.append("failed: {} at line {}: {}".format(error_class, line_number, detail))
        if line_number <= len(code.split('\n')):
            result.append("Offending line: {}".format(code.split('\n')[line_number - 1]))


def check_correctness(check_program, timeout=3):
    manager = multiprocessing.Manager()
    result = manager.list()

    p = multiprocessing.Process(target=unsafe_execute, args=(check_program, result, timeout))
    p.start()

    timer = Timer(timeout, p.terminate)
    timer.start()

    p.join()

    timer.cancel()

    if not result:
        result.append("timed out")

    print(result)

    return result[0] == "passed"


if __name__ == "__main__":
    # Test the code execution tool
    test_codes = [
        # Test 1: Simple addition (should pass)
        """
def add(a, b):
    return a + b

result = add(5, 3)
assert result == 8, f"Expected 8, but got {result}"
print("Addition test passed")
        """,

        # Test 2: Syntax error (should fail)
        """
def broken_function()
    return "This has a syntax error"

print(broken_function())
        """,

        # Test 3: Runtime error (should fail)
        """
def divide(a, b):
    return a / b

result = divide(10, 0)
print(result)
        """,

        # Test 4: Timeout test (should timeout)
        """
import time

def long_running_function():
    time.sleep(5)
    return "This should timeout"

print(long_running_function())
        """
    ]

    for i, code in enumerate(test_codes, 1):
        print(f"\nRunning Test {i}:")
        result = check_correctness(code)
        print(f"Test {i} {'passed' if result else 'failed'}")

    print("\nAll tests completed.")