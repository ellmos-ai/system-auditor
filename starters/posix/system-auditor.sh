#!/usr/bin/env bash
set -euo pipefail
# Optional: SA_LANG=de|en, TASKPLAN_WORKDIR, TASKPLAN_TRUSTED_AUTOMATION.
python3 -c 'import taskplan' >/dev/null 2>&1 || {
  printf '%s\n' 'TASKPLAN is missing. Install it: python3 -m pip install taskplan' >&2
  exit 2
}
starter_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
role_prompt="$starter_dir/../../prompts/AUDITOR.${SA_LANG:-de}.md"
if [[ ! -f "$role_prompt" ]]; then
  printf '%s\n' 'Role prompt is missing. SA_LANG must be de or en.' >&2
  exit 2
fi
exec python3 -m taskplan launch --label system-auditor --prompt-file "$role_prompt" --request 'Start as SYSTEM-AUDITOR. Complete preflight steps (a0) and (a) from the role prompt, and confirm the audit scope with the user before the sweep.' --interactive "$@"
