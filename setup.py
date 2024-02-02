#!/usr/bin/python3
#                                                         -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
#
"""Setup for tox-lsr."""

import io

from setuptools import find_packages, setup

# pylint: disable=R1732
setup(
    name="tox-lsr",
    version="3.2.2",
    url="https://github.com/linux-system-roles/tox-lsr",
    description="A tox plugin for testing Linux system roles",
    long_description_content_type="text/markdown",
    long_description=io.open("README.md", encoding="utf-8").read(),
    author="Linux System Roles Team",
    author_email="systemroles@lists.fedorahosted.org",
    classifiers=[
        "Development Status :: 1 - Planning",
        "Environment :: Console",
        "Environment :: Plugins",
        "Framework :: tox",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Topic :: Software Development :: Testing",
    ],
    license="MIT",
    zip_safe=False,
    packages=find_packages("src"),
    package_dir={"": "src"},
    scripts=[
        "src/tox_lsr/test_scripts/lsr_ci_preinstall",
        "src/tox_lsr/test_scripts/lsr_ci_runtox",
    ],
    package_data={"": ["config_files/*", "test_scripts/*",
                       "osbuild-manifests/**"]},
    entry_points={
        "tox": ["lsr = tox_lsr.hooks"],
    },
    python_requires=">=2.6, !=3.0.*, !=3.1.*, !=3.2.*, !=3.3.*, !=3.4.*",
    install_requires=["tox", "configparser"],
)
