"""Exercise adapter failures and the exact read boundary without model calls."""

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('runner', Path(__file__).with_name('run-codex.py'))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class AdapterTests(unittest.TestCase):
    def test_guard_denies_chains_writes_other_files_and_tools(self):
        reads = ["Get-Content -LiteralPath 'C:/fixture/run/SKILL.md'"]
        self.assertTrue(runner.allowed_read('Bash', reads[0], reads))
        self.assertTrue(runner.allowed_read('Bash', '  ' + reads[0] + ' \n', reads))
        for command in [reads[0] + '; gh pr merge 17', 'Set-Content x test', "Get-Content -LiteralPath 'C:/auth.json'"]:
            self.assertFalse(runner.allowed_read('Bash', command, reads))
        self.assertFalse(runner.allowed_read('apply_patch', reads[0], reads))

    def test_skill_indicator_requires_successful_exact_file_read(self):
        target = Path('fixture/run/SKILL.md').resolve()
        command = f"cat '{target.as_posix()}'"
        item = {'type': 'command_execution', 'command': command, 'status': 'completed', 'exit_code': 0, 'aggregated_output': '---\nname: run\ndescription: test\n---'}
        self.assertTrue(runner.skill_read([{'type': 'item.completed', 'item': item}], target))
        for patch in [{'exit_code': 1}, {'aggregated_output': ''}, {'command': command.replace('SKILL.md', 'other.md')}, {'status': 'in_progress'}]:
            self.assertFalse(runner.skill_read([{'type': 'item.completed', 'item': item | patch}], target))
        self.assertFalse(runner.skill_read([{'type': 'item.completed', 'item': {'type': 'agent_message', 'text': command}}], target))
        self.assertFalse(runner.skill_read([{'type': 'item.completed', 'item': item | {'command': command.replace('SKILL.md', 'SKILL.md.backup')}}], target))

    def test_denied_action_scores_failure_without_aborting_other_cases(self):
        case = {'graders': [{'name': 'no-execution', 'type': 'tool_used', 'tool': 'Bash', 'max': 0}]}
        answer = {'reply': 'Stopped', 'activated': False, 'denied_actions': ['gh pr merge 17']}
        result = runner.grade(case, answer, 'unused', Path('unused'))
        self.assertEqual(result['score'], 0)
        self.assertFalse(result['graders'][0]['passed'])

    def test_guard_fails_closed_on_malformed_input_or_missing_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, str(Path(runner.__file__)), directory, '--guard'], input='{}', capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)

    def test_completion_fails_closed_on_missing_reply_error_or_bad_json(self):
        reply = {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'Answer'}}
        finish = {'type': 'turn.completed', 'usage': {'input_tokens': 10}}
        self.assertEqual(runner.final_reply([reply, finish]), 'Answer')
        for events in [[reply], [finish], [reply, {'type': 'turn.failed', 'error': 'failed'}], [reply, finish, {'type': 'item.completed', 'item': {'type': 'error', 'message': 'Code Mode is unavailable'}}]]:
            with self.assertRaises(ValueError):
                runner.final_reply(events)
        with self.assertRaises(json.JSONDecodeError):
            runner.parse_events('not JSON')
        for command in [{'status': 'failed', 'exit_code': 1}, {'status': 'in_progress', 'exit_code': None}]:
            with self.assertRaises(ValueError):
                runner.final_reply([{'type': 'item.completed', 'item': {'id': 'cmd', 'type': 'command_execution'} | command}, reply, finish])
        with self.assertRaises(ValueError):
            runner.final_reply([{'type': 'item.started', 'item': {'id': 'cmd', 'type': 'command_execution'}}, reply, finish])

    def test_command_reads_require_matching_allowed_guard_receipts(self):
        command = "cat '/fixture/run/SKILL.md'"
        event = {'type': 'item.completed', 'item': {'type': 'command_execution', 'command': command, 'status': 'completed', 'exit_code': 0}}
        receipt = {'allowed': True, 'command': command}
        runner.verify_guard([event], [receipt])
        other = "cat '/fixture/run/other.md'"
        runner.verify_guard([event | {'item': event['item'] | {'command': other}}, event], [receipt, receipt | {'command': other}])
        for receipts in [[], [receipt | {'command': 'other'}], [receipt | {'allowed': False}]]:
            with self.assertRaises(ValueError):
                runner.verify_guard([event], receipts)
        with self.assertRaises(ValueError):
            runner.verify_guard([], [receipt])

    def test_judge_denied_actions_cannot_award_a_passing_result(self):
        case = {'graders': [{'name': 'result', 'type': 'llm', 'criteria': 'Correct'}]}
        answer = {'reply': 'Answer', 'activated': False, 'denied_actions': []}
        judge = {'reply': '{"passed":true,"reason":"Correct"}', 'denied_actions': ['write']}
        with patch.object(runner, 'session', return_value=judge), self.assertRaises(ValueError):
            runner.grade(case, answer, 'unused', Path('unused'))

    def test_cli_failure_preserves_actual_prompt_and_diagnostics(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            result = subprocess.CompletedProcess([], 1, 'partial trace', 'failure detail')
            with patch.object(runner.subprocess, 'run', return_value=result), self.assertRaises(ValueError):
                runner.invoke([], output, {}, prompt='actual case prompt', artifacts=output)
            self.assertEqual((output / 'prompt.txt').read_text(), 'actual case prompt')
            self.assertEqual((output / 'trace.jsonl').read_text(), 'partial trace')
            self.assertEqual((output / 'stderr.txt').read_text(), 'failure detail')

    def test_catalog_isolation_disables_foreign_files_and_checks_target(self):
        work = Path('fixture').resolve()
        text = f"- `r0` = `/foreign`\n- `r1` = `{work.as_posix()}/.agents/skills`\n- foreign (file: r0/other/SKILL.md)\n- run (file: r1/run/SKILL.md)"
        self.assertEqual(runner.catalog_paths([{'content': [{'text': text}]}]), [Path('/foreign/other/SKILL.md'), work / '.agents/skills/run/SKILL.md'])


if __name__ == '__main__':
    unittest.main()
