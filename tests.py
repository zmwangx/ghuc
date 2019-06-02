import hashlib
import os
import random
import pathlib
import subprocess
import sys
import tempfile
import time

import pytest
import urllib3
from PIL import Image


HERE = pathlib.Path(__file__).parent.resolve()
GHUC = HERE / "ghuc.py"

http = urllib3.PoolManager(cert_reqs="CERT_REQUIRED", timeout=3.0)


class ImageFile:
    def __init__(self, image, format):
        fd, self.path = tempfile.mkstemp(suffix=".%s" % format)
        with os.fdopen(fd, "w+b") as fp:
            image.save(fp, format=format)
            fp.seek(0)
            self.sha256 = hashlib.sha256(fp.read()).hexdigest()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        try:
            os.unlink(self.path)
        except OSError:
            pass


@pytest.fixture(scope="session", autouse=True)
def execution_env():
    if sys.platform == "win32":
        pytest.skip("xdgappdirs does not respect XDG_* on win32; tests disabled")

    # Credentials must be specified in env vars.
    for env_var in ("GITHUB_USERNAME", "GITHUB_PASSWORD", "GITHUB_TOTP_SECRET"):
        if not os.getenv(env_var):
            pytest.fail("%s required" % env_var)

    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["XDG_CONFIG_HOME"] = tmpdir
        os.environ["XDG_DATA_HOME"] = tmpdir
        os.environ["XDG_CACHE_HOME"] = tmpdir
        yield


@pytest.fixture(scope="session")
def random_image():
    return Image.frombytes(
        "L", (100, 100), bytes(random.randrange(256) for i in range(10000))
    )


@pytest.fixture(scope="session")
def png_file(random_image):
    with ImageFile(random_image, "png") as f:
        yield f


@pytest.fixture(scope="session")
def jpeg_file(random_image):
    with ImageFile(random_image, "jpeg") as f:
        yield f


@pytest.fixture(scope="session")
def pdf_file(random_image):
    with ImageFile(random_image, "pdf") as f:
        yield f


@pytest.fixture(scope="session")
def webp_file(random_image):
    with ImageFile(random_image, "webp") as f:
        yield f


# ghuc.py is not reentrant (in that refresh_cookie_and_token being
# called after a 422 can only happen once), so instead of importing the
# module and calling the main function, we have to run it in a
# subprocess.
def run_ghuc_and_verify(good_files, bad_files):
    cmdline = [str(GHUC)]
    if os.getenv("CONTAINER"):
        cmdline.append("--container")
    cmdline.extend(f.path for f in good_files)
    cmdline.extend(f.path for f in bad_files)
    p = subprocess.Popen(
        cmdline,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        bufsize=1,
    )
    # tee captured stderr
    stderr_data = ""
    for line in p.stderr:
        sys.stderr.write(line)
        stderr_data += line
    returncode = p.wait()
    stdout_data = p.stdout.read()
    sys.stdout.write(stdout_data)
    assert returncode == (1 if bad_files else 0)

    urls = stdout_data.splitlines()
    assert len(good_files) == len(urls)
    for f, url in zip(good_files, urls):
        while True:
            url_sha256 = hashlib.sha256(http.request("GET", url).data).hexdigest()
            if (
                url_sha256
                == "0019dfc4b32d63c1392aa264aed2253c1e0c2fb09216f8e2cc269bbfb8bb49b5"
            ):
                # This is the SHA-256 checksum for "Not Found".
                time.sleep(1)
                continue
            assert url_sha256 == f.sha256, (
                "SHA-256 mismatch for %s: expected %s, got %s"
                % (url, f.sha256, url_sha256)
            )
            break

    if bad_files:
        assert "unsupported MIME type" in stderr_data


def test_ghuc(png_file, jpeg_file, pdf_file, webp_file):
    print("[1] initial run", file=sys.stderr)
    run_ghuc_and_verify([png_file, jpeg_file, pdf_file], [])

    print("[2] subsequent run", file=sys.stderr)
    run_ghuc_and_verify([png_file, jpeg_file, pdf_file], [])

    print("[3] expected failure", file=sys.stderr)
    run_ghuc_and_verify([png_file], [webp_file])

    print("[4] tempered token", file=sys.stderr)
    data_dir = pathlib.Path(os.environ["XDG_DATA_HOME"])
    # Invalidate the cached token by changing its first character.
    with data_dir.joinpath("ghuc/token").open("r+") as fp:
        first_char = fp.read(1)
        fp.seek(0)
        fp.write("b" if first_char == "a" else "a")
    run_ghuc_and_verify([png_file], [])
