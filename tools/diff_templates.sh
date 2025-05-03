#!/usr/bin/bash

set -euo pipefail

SCRIPT_DIR=$(dirname "$0")

function usage()
{
  echo "$(basename "$0") --borgmatic"
}

function do_borgmatic_diff()
{
  new_config="${SCRIPT_DIR}"/borgmatic-config-new.yaml
  current_config="${SCRIPT_DIR}"/../src/automatic-backup/templates/borgmatic-config.yaml
  borgmatic config generate --overwrite --destination "${new_config}"
  diff -b "${new_config}" "${current_config}"
}

if [[ $# -ne 1 ]]; then
  usage
  exit 1
fi
if [[ "$1" = "--borgmatic" ]]; then
  do_borgmatic_diff
fi
