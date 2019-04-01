#!/usr/bin/env python3

import pathlib

import setuptools


HERE = pathlib.Path(__file__).parent.resolve()
with HERE.joinpath("README.md").open(encoding="utf-8") as fp:
    long_description = fp.read()

setuptools.setup(
    name="ghuc",
    version="0.1",
    description="Upload images/documents to GitHub as issue attachments",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/zmwangx/ghuc",
    author="Zhiming Wang",
    author_email="i@zhimingwang.org",
    python_requires=">=3.4",
    license="MIT",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.5",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3 :: Only",
        "Programming Language :: Python :: Implementation :: CPython",
        "Topic :: Internet",
        "Topic :: Multimedia",
        "Topic :: Utilities",
    ],
    keywords="github image upload headless browser",
    py_modules=["ghuc"],
    entry_points={"console_scripts": ["ghuc=ghuc:main"]},
    install_requires=[
        "pyotp",
        "python-magic",
        "selenium",
        "urllib3[secure,socks]",
        "xdgappdirs>=1.4.5",
    ],
    extras_require={"test": ["Pillow", "pytest"]},
)
