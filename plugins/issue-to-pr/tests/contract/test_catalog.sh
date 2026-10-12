#!/usr/bin/env bash

test_catalog_and_shared_workflow_contracts() {
  local repo_root python_cmd
  repo_root=$(cd "$ITP_SCRIPTS/../../.." && pwd) || return
  python_cmd=$(command -v python || command -v python3) || return
  "$python_cmd" "$repo_root/scripts/tests/test_catalog.py" &&
    "$python_cmd" "$repo_root/docs/tests/test_development_workflows.py" &&
    "$python_cmd" "$repo_root/plugins/tg-voice/scripts/test_transcribe_voice.py"
}
