# SPDX-FileCopyrightText: 2021 ladyada for Adafruit Industries
#
# SPDX-License-Identifier: MIT

from setuptools import setup


setup(
    name="pyatecc",
    version='1.0.0-beta.1',
    description="Driver for Microchip's ATECC508/ATECC608 cryptographic co-processors with secure hardware-based key storage",
    long_description_content_type="text/markdown",
    url="https://github.com/ccrisan/pyatecc",
    install_requires=[
        "smbus2"
    ],
    license="MIT",
    packages=["pyatecc"],
)
