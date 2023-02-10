#!/bin/bash
# SPDX-License-Identifier: MIT

# Do not exit on an error to continue ansible-doc and ansible-test.
set -euo pipefail

#uncomment if you use $ME - otherwise set in utils.sh
#ME=$(basename "$0")
SCRIPTDIR=$(readlink -f "$(dirname "$0")")

. "${SCRIPTDIR}/utils.sh"

# Run codeql against python codes in a role
CODEQLACTIONDIR=${CODEQLACTIONDIR:-"${HOME}/github.com/github/codeql-action"}
ROLE=${ROLE:-"$( basename $TOPDIR )"}
JQPATH=$( which jq 2> /dev/null )
if [ $? -ne 0 ]; then
    lsr_error "${ME}: jq is missing. Please install the package."
fi

# Go to the TOPDIR
cd "$TOPDIR"

# Install CodeQL
# https://docs.github.com/en/code-security/code-scanning/using-codeql-code-scanning-with-your-existing-ci-system/installing-codeql-cli-in-your-ci-system
CODEQLTARBALL=codeql-bundle-linux64.tar.gz
CODEQLURL=https://github.com/github/codeql-action/releases/latest/download/$CODEQLTARBALL
if [ ! -f "$LSR_TOX_ENV_TMP_DIR/$CODEQLTARBALL" ]; then
    curl -L -o "$LSR_TOX_ENV_TMP_DIR/$CODEQLTARBALL"  "$CODEQLURL"
fi
if [ ! -d "$LSR_TOX_ENV_TMP_DIR/codeql" ]; then
    tar xfz "$LSR_TOX_ENV_TMP_DIR/$CODEQLTARBALL" -C "$LSR_TOX_ENV_TMP_DIR"
fi
# codeql/codeql is a shell script which launches java, which  requires all the files in the 
PATH="$LSR_TOX_ENV_TMP_DIR/codeql":"$PATH"

# Checkout codeql-action
CODEQLACTIONDIR="$LSR_TOX_ENV_DIR/codeql-action"
if [ ! -d "$CODEQLACTIONDIR" ]; then
    git clone https://github.com/github/codeql-action "$CODEQLACTIONDIR"
fi

# Create a database dir:
DBDIR=$LSR_TOX_ENV_DIR/database
if [ ! -d "$DBDIR" ]; then
    mkdir $DBDIR
fi
RESULTS=$LSR_TOX_ENV_DIR/results
if [ ! -d "$RESULTS" ]; then
    mkdir $RESULTS
fi

# Load language configuration
codeql resolve queries python-code-scanning.qls --format=bylanguage

codeql resolve queries python-security-and-quality.qls --format=bylanguage

codeql resolve languages --format=betterjson --extractor-options-verbosity=4

# Setup Python dependencies
# $CODEQLACTIONDIR/python-setup/install_tools.sh
# Remove "--user" from "pip install" to workaround this error.
# ERROR: Can not perform a '--user' install. User site-packages are
# not visible in this virtualenv.
sed -e "s/pip install --user/pip install/" \
$CODEQLACTIONDIR/python-setup/install_tools.sh > "$LSR_TOX_ENV_TMP_DIR/install_tools.sh"
bash "$LSR_TOX_ENV_TMP_DIR/install_tools.sh"

if [ -d "$DBDIR/python" ]; then
    rm -rf $DBDIR/*
fi
codeql database init --db-cluster "$DBDIR" --source-root="$TOPDIR" \
    --language=python

# Setup environment variables
export CODEQL_WORKFLOW_STARTED_AT=$( date -Iseconds )
export CODEQL_RAM=5919
export CODEQL_THREADS=2

# Extracting python
codeql database trace-command "$DBDIR/python" -- \
    "$LSR_TOX_ENV_TMP_DIR/codeql/python/tools/autobuild.sh"

# Finalizing python
codeql database finalize --finalize-dataset --threads="$CODEQL_THREADS" \
    --ram="$CODEQL_RAM" "$DBDIR/python"

# Running queries for python
codeql database run-queries --ram="$CODEQL_RAM" --threads="$CODEQL_THREADS" \
    "$DBDIR/python" --min-disk-free=1024 \
    -v python-security-and-quality.qls

# Interpreting results for python
codeql database interpret-results --threads="$CODEQL_THREADS" \
    --format=sarif-latest -v --output=$RESULTS/python.sarif \
    --no-sarif-add-snippets --print-diagnostics-summary \
    --print-metrics-summary --sarif-group-rules-by-pack \
    --sarif-add-query-help --sarif-category /language:python \
    --sarif-add-baseline-file-info "$DBDIR/python" \
    python-security-and-quality.qls

codeql database print-baseline "$DBDIR/python"

codeql diagnostics export --format=sarif-latest --output=$RESULTS/codeql-failed-run.sarif --sarif-category /language:python

echo "CodeQL result file on $ROLE:"
echo " - failed: $RESULTS/codeql-failed-run.sarif"
echo " - all: $RESULTS/python.sarif"

JQPATH=$( which jq 2> /dev/null )
if [ $? -ne 0 ]; then
    echo "WARNING: please install jq package"
else
    fcnt=$( jq '.runs[0].results | length' "$RESULTS/codeql-failed-run.sarif" )
    wcnt=$( jq '.runs[0].results | length' "$RESULTS/python.sarif" )
    if [ "$fcnt" -gt 0 ]; then
        echo "CODEQL RESULT"
        jq '.runs[0].results' "$RESULTS/codeql-failed-run.sarif"
        lsr_error "${ME}: Found $wcnt findings; $fcnt of them is/are failure(s)."
    elif [ "$wcnt" -gt 0 ]; then
        echo "CODEQL RESULT"
        jq '.runs[0].results' "$RESULTS/python.sarif"
        echo "PASS: Found $wcnt items; none of them are failures."
    else
        echo "PASS: Found no security and quality issues."
    fi
fi
exit 0
