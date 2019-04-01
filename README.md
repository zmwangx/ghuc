# ghuc

[![PyPI](https://img.shields.io/pypi/v/ghuc.svg?maxAge=3600)](https://pypi.org/project/ghuc)
![Python 3.5, 3.6, 3.7](https://img.shields.io/badge/python-3.5,%203.6,%203.7-blue.svg?maxAge=86400)
![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg?maxAge=86400)
[![CircleCI status](https://img.shields.io/circleci/project/github/zmwangx/ghuc.svg)](https://circleci.com/gh/zmwangx/workflows/ghuc)

`ghuc` (derived from `githubusercontent` and pronounced *gee&middot;huck*) is a command line tool for uploading images/documents to GitHub as issue attachments. Images are then available at `https://user-images.githubusercontent.com`, and documents are available as `https://github.com/<user>/<repo>/files/...`. It automates the traditional flow of navigating to a repo -> opening an issue -> uploading an image -> copying the URL, which is very cumbersome. With the constant deterioration of Imgur, one-stop upload to user-images.githubusercontent.com is the next best thing for the occasional image embeds in docs or comment section/forum posts.

`ghuc` is partially powered by Selenium WebDriver. Tested and supported on macOS, Linux, and Windows.

*Please respect GitHub's ToS and do NOT abuse this tool.*

<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->
## Contents

- [Installation](#installation)
  - [Non-Python dependencies](#non-python-dependencies)
    - [Optional dependencies](#optional-dependencies)
- [Usage](#usage)
  - [Environment variables](#environment-variables)
- [How it works](#how-it-works)
- [FAQ](#faq)
- [TODO](#todo)
- [License](#license)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

## Installation

```
pip install ghuc
```

Isolated installation through [pipx](https://github.com/pipxproject/pipx) is recommended.

### Non-Python dependencies

Since `ghuc` uses Selenium WebDriver, one of the following browser and driver combos is required:

- Firefox with [`geckodriver`](https://github.com/mozilla/geckodriver/releases);
- Chrome/Chromium with [`chromedriver`](http://chromedriver.chromium.org/downloads).

#### Optional dependencies

- `libmagic` is needed for accurate MIME type detection; otherwise, MIME types are guessed based on file extensions.

## Usage

```console
$ ghuc -h
usage: ghuc [-h] [-r REPOSITORY_ID] [-x PROXY] [-q] [--debug] [--gui]
            [--container] [--version]
            PATH [PATH ...]

Uploads images/documents to GitHub as issue attachments. See
https://github.com/zmwangx/ghuc for detailed documentation.

positional arguments:
  PATH

optional arguments:
  -h, --help            show this help message and exit
  -r REPOSITORY_ID, --repository-id REPOSITORY_ID
                        id of repository to upload from (defaults to 1)
  -x PROXY, --proxy PROXY
                        HTTP or SOCKS proxy
  -q, --quiet           set logging level to ERROR
  --debug               set logging level to DEBUG
  --gui                 disable headless mode when running browser sessions
                        through Selenium WebDriver
  --container           add extra browser options to work around problems in
                        containers
  --version             show program's version number and exit
  ```

  Notes:

  - Not all file types are supported by GitHub. At the moment of writing the following, I quote, are supported:

    > GIF, JPEG, JPG, PNG, DOCX (*seriously?*), GZ, LOG, PDF, PPTX, TXT, XLSX, and ZIP.

  - The first time you use `ghuc`, you'll be prompted for your GitHub credentials to log in (see [*How it works*](#how-it-works); you may use environment variables documented below to bypass interactive prompts). Your cookies will be cached but your credentials are never stored. Subsequent runs may phone GitHub for a new token once in a while, but ideally you should not need to log in again.

  - `--repository-id`: determines what repo shows up the URL of uploaded documents. E.g., with the default `1`, the URL may be https://github.com/mojombo/grit/files/3027504/random.pdf; when set to `36502`, one may get https://github.com/git/git/files/3027505/random.pdf instead. This option is cosmetic as long as a repository exists by the id. This option has no effect on image uploads as far as I can tell.

  - `--proxy`: HTTP and SOCKS (4/4a/5/5h) proxies are supported, i.e., the following protocol prefixes are recognized: `http://`, `https://`, `socks4://`, `socks4a://`, `socks5://`, `socks5h://`. If no protocol is specified, `http://` is assumed. The `https_proxy` environment variable is also honored.

  - `--gui` and `--container`: these are mostly development/testing options; end users don't need to touch them. `--container` in particular may not be secure for end user systems.

### Environment variables

- `GITHUB_USERNAME`, `GITHUB_PASSWORD` and `GITHUB_TOTP_SECRET`: interactive prompts for credentials are suppressed when these are provided. `GITHUB_TOTP_SECRET` is needed only if you use TOTP for two-factor authentication. If you only use text messages for 2FA (highly discouraged), the login flow might work but there's no guarantee (since I don't have a setup like this; contribution welcome). If you only use FIDO U2F for 2FA, you're out of luck.
- `https_proxy`: see `--proxy`.

## How it works

Uploading files as issue attachments requires two levels of authentication: GitHub session cookies and an `uploadPolicyAuthenticityToken` (CSRF token of sort). `uploadPolicyAuthenticityToken` can be found on any GitHub page with a comment box while logged in, and each one is valid for quite a while (without dedicated testing it's hard to say how long, but the validity period is at least more than a day).

`ghuc` logs into GitHub through Selenium WebDriver and caches session cookies as well as the token. It then performs all uploads with the cached values and doesn't touch the browser anymore (so normal uploads should be pretty fast) until the token is stale, at which point it attempts to restore the previous browser session and fetch a new token.

## FAQ

- *Why not Puppeteer?*

  Puppeteer is way more flexible than Selenium WebDriver from a developer's point of view, but having to download a bundled, ~100MB, non-auto-updating copy of Chromium for every install that's already outdated the next time you use it is really user-hostile. I'm also not a fan of the Node/npm ecosystem. Finally, synchronous is good for this project.

## TODO

- Respect proxy option in selenium invocations (currently browsers use system proxy settings);
- Page loads: wait for `DOMContentLoaded` instead of `load` (selenium default, wastes a lot time on slow connections);
- Handle authentication failures and allow retries (currently we assume all credentials are correct).

## License

Copyright &copy; 2019 Zhiming Wang <i@zhimingwang.org>. The MIT License.
