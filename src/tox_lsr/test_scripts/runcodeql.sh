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
WORKDIR=$( mktemp -d /var/tmp/CODEQL_DB_${ROLE}_XXX )

# Go to the TOPDIR
cd "$TOPDIR"

# Install CodeQL
# https://docs.github.com/en/code-security/code-scanning/using-codeql-code-scanning-with-your-existing-ci-system/installing-codeql-cli-in-your-ci-system
CODEQLTARBALL=codeql-bundle-linux64.tar.gz
CODEQLURL=https://github.com/github/codeql-action/releases/latest/download/$CODEQLTARBALL
CODEQLPATH=$( which codeql 2> /dev/null )
if [ $? -ne 0 ]; then
    wget "$CODEQLURL"
    tar -xzf ./"$CODEQLTARBALL"
    # Set $( pwd )/codeql to PATH
    PATH=$( pwd )/codeql:$PATH
else
    # Set parentdir of $CODEQLPATH to PATH
    PATH=$( dirname "$CODEQLPATH" ):$PATH
fi

# Checkout codeql-action
GITHUBDIR="${HOME}/github.com/github"
CODEQLACTIONDIR=${CODEQLACTIONDIR:-"${GITHUBDIR}/codeql-action"}
if [ ! -d $CODEQLACTIONDIR ]; then
    if [ ! -d $GITHUBDIR ]; then
        mkdir -p $GITHUBDIR
    fi
    (cd $GITHUBDIR; gh repo clone github/codeql-action)
fi

# Create a database dir:
DBDIR=$WORKDIR/database
mkdir $DBDIR
RESULTS=$WORKDIR/results
mkdir $RESULTS

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
$CODEQLACTIONDIR/python-setup/install_tools.sh > $WORKDIR/install_tools.sh
bash -x $WORKDIR/install_tools.sh

codeql database init --db-cluster $DBDIR --source-root=$TOPDIR \
    --language=python

# Setup environment variables
export CODEQL_WORKFLOW_STARTED_AT=$( date -Iseconds )
export CODEQL_RAM=5919
export CODEQL_THREADS=2

# Extracting python
codeql database trace-command $DBDIR/python -- \
    $( dirname "$CODEQLPATH" )/python/tools/autobuild.sh

# Finalizing python
codeql database finalize --finalize-dataset --threads=$CODEQL_THREADS \
    --ram=$CODEQL_RAM $DBDIR/python

# Running queries for python
codeql database run-queries --ram=$CODEQL_RAM --threads=$CODEQL_THREADS \
    $DBDIR/python --min-disk-free=1024 \
    -v python-security-and-quality.qls

# Interpreting results for python
codeql database interpret-results --threads=$CODEQL_THREADS \
    --format=sarif-latest -v --output=$RESULTS/python.sarif \
    --no-sarif-add-snippets --print-diagnostics-summary \
    --print-metrics-summary --sarif-group-rules-by-pack \
    --sarif-add-query-help --sarif-category /language:python \
    --sarif-add-baseline-file-info $DBDIR/python \
    python-security-and-quality.qls

codeql database print-baseline $DBDIR/python

echo "CodeQL result file on $ROLE: $RESULTS/python.sarif"

JQPATH=$( which jq 2> /dev/null )
if [ $? -ne 0 ]; then
    echo "WARNING: please install jq package"
else
    rcnt=$( jq '.runs[0].results | length' $RESULTS/python.sarif )
	if [ $rcnt -gt 0 ]; then
        echo "CODEQL RESULT"
        jq '.runs[0].results' $RESULTS/python.sarif
        lsr_error "${ME}: Found $rcnt security issues."
    else
        echo "PASS: Found no security issues."
	fi
fi
exit 0
