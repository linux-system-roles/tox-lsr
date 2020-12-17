#                                                         -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
#
# Copyright (c) 2020 Red Hat, Inc.
#
# Calls the coveralls.io API with the arguments used by
# linux-system-roles
"""Run coveralls with our custom arguments."""

import os

import coveralls


def main():
    """Run coveralls with our custom arguments."""

    cov_alls = coveralls.api.Coveralls(
        service_name="github",
        repo_token=os.environ["GITHUB_TOKEN"],
        service_job_id=None,
    )
    result = cov_alls.wear()
    print("coveralls result: {}".format(str(result)))


if __name__ == "__main__":
    main()
