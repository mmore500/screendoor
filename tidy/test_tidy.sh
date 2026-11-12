#!/bin/bash
set -e

cd "$(dirname "$0")/.."

# enforce use of GNU version of coreutils
# (ensuring GNU utils at startup reduces redundant verbosity)
. ./tidy/util/enforce_gnu_utils.sh

echo "Running tidyness enforcement tests..."
echo "(Each failing check names the tidy/impl/ script that fixes it.)"

./tidy/test_merge_conflict_markers.sh && echo "✔ conflict markers ok" || exit 1
./tidy/test_end_of_file_newlines.sh && echo "✔ EOF newlines ok" || exit 1
./tidy/test_tabs.sh && echo "✔ no tabs, indentation ok" || exit 1
./tidy/test_trailing_whitespace.sh && echo "✔ trailing whitespace ok" || exit 1
./tidy/test_filename_whitespace.sh && echo "✔ filename whitespace ok" || exit 1
./tidy/test_lint.sh && echo "✔ no lint violations" || exit 1
./tidy/test_style.sh && echo "✔ style ok" || exit 1
