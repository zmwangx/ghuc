#!/usr/bin/env python3

import argparse
import collections
import getpass
import json
import logging
import logging.config
import mimetypes
import os
import pathlib
import re
import sys
import tempfile
import urllib.parse

import pyotp
import xdgappdirs as appdirs
from selenium.webdriver import Chrome, Firefox
from selenium.common.exceptions import (
    WebDriverException,
    NoSuchElementException,
    JavascriptException,
)
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from urllib3 import PoolManager, ProxyManager, Timeout
from urllib3.exceptions import HTTPError

try:
    import magic
except ImportError:
    magic = None

try:
    from urllib3.contrib.socks import SOCKSProxyManager
except ImportError:
    SOCKSProxyManager = None


ISSUE_URL = "https://www.github.com/login?return_to=%2Fmojombo%2Fgrit%2Fissues%2F1"

logging.config.dictConfig(
    {
        "version": 1,
        "formatters": {
            "brief": {
                "format": "%(asctime)s [%(levelname)s] %(message)s",
                "datefmt": "%H:%M:%S",
            }
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "brief",
                "level": "INFO",
            }
        },
        "loggers": {"ghuc": {"level": "INFO", "handlers": ["console"]}},
    }
)
logger = logging.getLogger("ghuc")

# Global configs
repository_id = 1
proxy = None
headless = True
container = False

data_dir = appdirs.user_data_dir("ghuc", "org.zhimingwang", roaming=True, as_path=True)
data_dir.mkdir(exist_ok=True, parents=True)
cookie_file = data_dir / "cookies"
token_file = data_dir / "token"

# credentials_fresh is initialized as False, and set to True once
# refresh_cookie_and_token is run. Used to make sure we don't blame
# /upload/policies/assets failure on stale credentials twice in a single
# session.
credentials_fresh = False
cookies = []
cookie_header = None
token = None

__version__ = "0.1"


class ExtractionError(Exception):
    pass


class UploadError(Exception):
    pass


def load_cookie_and_token():
    global cookies
    global cookie_header
    global token

    try:
        logger.debug("loading token from %s ...", token_file)
        with token_file.open() as fp:
            token = fp.read().strip()
    except OSError:
        token = None

    try:
        logger.debug("loading cookies from %s ...", cookie_file)
        cookies = []
        with cookie_file.open() as fp:
            cookies = json.load(fp)
    except (OSError, json.JSONDecodeError):
        pass
    try:
        cookie_header = "; ".join(
            "%s=%s" % (cookie["name"], cookie["value"]) for cookie in cookies
        )
    except (TypeError, KeyError):
        logger.warning("corruption in cookie jar detected; ignoring persisted cookies")
        cookies = []
        cookie_header = None

    if not token or not cookie_header:
        logger.warning("persisted cookie and/or token not found or invalid")
        refresh_cookie_and_token()
    else:
        logger.debug("persisted cookie and token loaded")


def launch_firefox_driver():
    logger.debug("loading geckodriver...")
    options = FirefoxOptions()
    options.headless = headless
    return Firefox(options=options)


def launch_chrome_driver():
    logger.debug("loading chromedriver...")
    options = ChromeOptions()
    options.headless = headless
    if container:
        options.add_argument("--no-sandbox")
    return Chrome(options=options)


def write_page_source_and_report_error(source, msg):
    fd, temp_path = tempfile.mkstemp(suffix=".html", prefix="ghuc-")
    with os.fdopen(fd, "w") as fp:
        fp.write(source)
    logger.error("%s (page source written to %s)", msg, temp_path)
    raise ExtractionError


def secure_file_permissions(path):
    if path.stat().st_mode & 0o7777 != 0o0600:
        try:
            path.chmod(0o0600)
        except OSError:
            logger.warning("%s: failed to chmod to 0600", path)


def refresh_cookie_and_token():
    global credentials_fresh
    global cookies
    global cookie_header
    global token

    driver = None
    for launcher in (launch_firefox_driver, launch_chrome_driver):
        try:
            driver = launcher()
            break
        except WebDriverException as e:
            logger.debug(e)
    if driver is None:
        raise RuntimeError(
            "cannot load suitable webdriver; "
            "please install Chrome/Chromium and chromedriver, or Firefox and geckodriver"
        )

    logger.info("refreshing cookie and token...")
    try:
        if cookies:
            logger.info("preparing browser session with persisted cookies...")
            # Web driver requires navigating to the domain before adding cookies.
            driver.get("https://github.com/404")
            try:
                for cookie in cookies:
                    driver.add_cookie(cookie)
            except WebDriverException:
                logger.warning(
                    "corruption in cookie jar detected; ignoring some persisted cookies"
                )
        logger.info("logging in...")
        driver.get(ISSUE_URL)
        try:
            username_field = driver.find_element_by_css_selector("input[name=login]")
            password_field = driver.find_element_by_css_selector("input[name=password]")
            submit_button = driver.find_element_by_css_selector("input[type=submit]")
            username = os.getenv("GITHUB_USERNAME")
            if username:
                logger.info("using username '%s' from GITHUB_USERNAME", username)
            else:
                username = input("GitHub username: ")
            password = os.getenv("GITHUB_PASSWORD")
            if password:
                logger.info("using password from GITHUB_PASSWORD")
            else:
                password = getpass.getpass("Password (never stored): ")
            username_field.send_keys(username)
            password_field.send_keys(password)
            submit_button.click()
        except NoSuchElementException:
            pass
        try:
            totp_field = driver.find_element_by_css_selector("input[name=otp]")
            submit_button = driver.find_element_by_css_selector("button[type=submit]")
            totp_secret = os.getenv("GITHUB_TOTP_SECRET")
            if totp_secret:
                totp = pyotp.TOTP(totp_secret).now()
                logger.info("using TOTP %s derived from GITHUB_TOTP_SECRET", totp)
            else:
                totp = input("TOTP: ")
            totp_field.send_keys(totp)
            submit_button.click()
        except NoSuchElementException:
            pass
        try:
            # For rarely used accounts, one could be presented with a
            # confirmation page for account recovery settings.
            remind_me_later = driver.find_element_by_css_selector(
                "button[type=submit][value=postponed]"
            )
            remind_me_later.click()
        except NoSuchElementException:
            pass
        logger.info("issue page loaded")

        try:
            token = driver.execute_script(
                "return document.querySelector('file-attachment').dataset.uploadPolicyAuthenticityToken;"
            )
        except JavascriptException as e:
            write_page_source_and_report_error(
                driver.page_source, "JavaScript exception: %s" % e
            )
        if not token:
            write_page_source_and_report_error(
                driver.page_source, "failed to extract uploadPolicyAuthenticityToken"
            )
        logger.info("extracted authenticity token: %s", token)
        logger.debug("persisting token to %s ...", token_file)
        with token_file.open("w") as fp:
            print(token, file=fp)
        secure_file_permissions(token_file)

        cookies = driver.get_cookies()
        cookie_header = "; ".join(
            "%s=%s" % (cookie["name"], cookie["value"]) for cookie in cookies
        )
        logger.debug("extracted cookie: %s", cookie_header)
        logger.debug("persisting cookies to %s ...", cookie_file)
        with cookie_file.open("w") as fp:
            json.dump(cookies, fp, indent=2)
        secure_file_permissions(cookie_file)

        logger.info("cookie and token refreshed")
        credentials_fresh = True
    finally:
        driver.quit()


def detect_mime_type(path):
    path = str(path)
    if magic:
        return magic.from_file(path, mime=True)
    else:
        return mimetypes.guess_type(path)[0]


def upload_asset(http_client, path):
    if not path.is_file():
        logger.error("%s: does not exist", path)
        raise UploadError
    name = path.name
    size = path.stat().st_size
    content_type = detect_mime_type(path)
    if not content_type:
        logger.error("%s: cannot detect or guess MIME type", path)
        raise UploadError

    try:
        while True:
            logger.debug("%s: retrieving asset upload credentials...", path)
            r = http_client.request(
                "POST",
                "https://github.com/upload/policies/assets",
                headers={"Accept": "application/json", "Cookie": cookie_header},
                fields={
                    "name": name,
                    "size": size,
                    "content_type": content_type,
                    "authenticity_token": token,
                    "repository_id": repository_id,
                },
            )
            data = r.data.decode("utf-8")
            logger.debug("/upload/policies/assets: HTTP %d: %s", r.status, data)
            if r.status == 422:
                if r.headers["Content-Type"].startswith("text/html"):
                    if credentials_fresh:
                        logger.error(
                            "%s: unexpected 422 text/html response from /upload/policies/assets",
                            path,
                        )
                        raise UploadError
                    else:
                        logger.warning("cookie and/or token appear stale")
                        refresh_cookie_and_token()
                        continue
                if (
                    r.headers["Content-Type"].startswith("application/json")
                    and "content_type" in data
                ):
                    logger.error("%s: unsupported MIME type %s", path, content_type)
                else:
                    logger.error(
                        "%s: 422 response from /upload/policies/assets: %s", path, data
                    )
                raise UploadError
            assert r.status == 201, (
                "/upload/policies/assets: expected HTTP 201, got %d" % r.status
            )
            obj = json.loads(data, object_pairs_hook=collections.OrderedDict)
            asset_url = obj["asset"]["href"]

            logger.debug("%s: uploading...", path)
            upload_url = obj["upload_url"]
            form = obj["form"]
            with path.open("rb") as fp:
                content = fp.read()
            form["file"] = (name, content)
            r = http_client.request(
                "POST", upload_url, fields=form, timeout=Timeout(connect=3.0)
            )
            logger.debug(
                "%s: HTTP %d: %s", upload_url, r.status, r.data.decode("utf-8")
            )
            assert r.status == 204, "%s: expected HTTP 204, got %d" % (
                upload_url,
                r.status,
            )

            logger.debug("%s: registering asset...", path)
            register_url = obj["asset_upload_url"]
            absolute_register_url = urllib.parse.urljoin(
                "https://github.com/", register_url
            )
            r = http_client.request(
                "PUT",
                absolute_register_url,
                headers={"Accept": "application/json", "Cookie": cookie_header},
                fields={"authenticity_token": obj["asset_upload_authenticity_token"]},
            )
            logger.debug(
                "%s: HTTP %d: %s", register_url, r.status, r.data.decode("utf-8")
            )
            assert r.status == 200, "%s: expected HTTP 200, got %d" % (
                register_url,
                r.status,
            )

            logger.debug("%s: upload success", path)
            print(asset_url)
            return
    except (HTTPError, AssertionError) as e:
        logger.error("%s: %s", path, e)
        raise UploadError


def main():
    parser = argparse.ArgumentParser(
        description="Uploads images/documents to GitHub as issue attachments.\n"
        "See https://github.com/zmwangx/ghuc for detailed documentation."
    )
    parser.add_argument(
        "-r",
        "--repository-id",
        type=int,
        default=1,
        help="id of repository to upload from (defaults to 1)",
    )
    parser.add_argument("-x", "--proxy", help="HTTP or SOCKS proxy")
    parser.add_argument(
        "-q", "--quiet", action="store_true", help="set logging level to ERROR"
    )
    parser.add_argument(
        "--debug", action="store_true", help="set logging level to DEBUG"
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="disable headless mode when running browser sessions through Selenium WebDriver",
    )
    parser.add_argument(
        "--container",
        action="store_true",
        help="add extra browser options to work around problems in containers",
    )
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("paths", type=pathlib.Path, nargs="+", metavar="PATH")
    args = parser.parse_args()

    if args.debug:
        custom_level = logging.DEBUG
    elif args.quiet:
        custom_level = logging.ERROR
    else:
        custom_level = None
    if custom_level is not None:
        logger.setLevel(custom_level)
        logger.handlers[0].setLevel(custom_level)

    global repository_id
    global proxy
    global headless
    global container

    repository_id = args.repository_id
    proxy = args.proxy or os.getenv("https_proxy")
    if proxy and not re.match(r"^(https?|socks(4a?|5h?))://", proxy):
        proxy = "http://%s" % proxy
    if proxy:
        logger.debug("using proxy %s", proxy)
    headless = not args.gui
    container = args.container

    common_http_options = dict(cert_reqs="CERT_REQUIRED", timeout=3.0)
    if not proxy:
        http_client = PoolManager(**common_http_options)
    elif proxy.startswith("http"):
        http_client = ProxyManager(proxy, **common_http_options)
    elif proxy.startswith("socks"):
        if SOCKSProxyManager:
            http_client = SOCKSProxyManager(proxy, **common_http_options)
        else:
            logger.critical("your urllib3 installation does not support SOCKS proxies")
            sys.exit(1)
    else:
        logger.critical("unrecognized proxy type %s", proxy)
        sys.exit(1)

    try:
        load_cookie_and_token()
        count = len(args.paths)
        num_errors = 0
        for path in args.paths:
            try:
                upload_asset(http_client, path)
            except UploadError:
                num_errors += 1
        if count > 1 and num_errors > 0:
            logger.warning("%d failed uploads", num_errors)
        sys.exit(0 if num_errors == 0 else 1)
    except ExtractionError:
        logger.critical("aborting due to inability to extract credentials")
        sys.exit(1)


if __name__ == "__main__":
    main()
