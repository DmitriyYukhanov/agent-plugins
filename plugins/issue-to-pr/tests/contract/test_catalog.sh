#!/usr/bin/env bash

test_catalog_and_shared_workflow_contracts() {
  local repo_root
  repo_root=$(cd "$ITP_SCRIPTS/../../.." && pwd) || return
  python "$repo_root/scripts/tests/test_catalog.py" &&
    python "$repo_root/docs/tests/test_development_workflows.py" &&
    python "$repo_root/plugins/tg-voice/scripts/test_transcribe_voice.py"
}
