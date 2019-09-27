import contextlib
import unittest
from io import StringIO
from unittest import mock
from unittest.mock import MagicMock, Mock, PropertyMock

import pytest
import requests_mock

import trigger

GITLAB_HOST = 'example.com'


def some_gitlab(url, api_token, verifyssl, pipeline_behavior):
    gitlab = Mock(url=url, private_token=api_token, ssl_verify=verifyssl)
    project = Mock(web_url=f"{url}/project1")
    project.pipelines.get = pipeline_behavior
    gitlab.projects.get = MagicMock(return_value=project)
    return gitlab


def some_manual_jobs(manual_pipeline):
    prop_name_1 = PropertyMock(return_value='manual1')
    job_1 = Mock(status=trigger.STATUS_MANUAL, stage='stage1')
    type(job_1).name = prop_name_1

    prop_name_2 = PropertyMock(return_value='manual2')
    job_2 = Mock(status=trigger.STATUS_MANUAL, stage='stage2')
    type(job_2).name = prop_name_2
    manual_pipeline.jobs.list = MagicMock(return_value=[
        Mock(status=trigger.STATUS_SKIPPED),
        job_1,
        job_2
    ])
    return manual_pipeline


def some_manual_pipeline_behavior(final_status):
    pipeline_behavior = Mock()
    pipeline_behavior.side_effect = [
        some_manual_jobs(Mock(status=trigger.STATUS_SKIPPED)),
        Mock(status='running'),
        Mock(status=final_status),
    ]
    return pipeline_behavior


def some_invalid_manual_pipeline_behavior():
    pipeline_behavior = Mock()
    pipeline = Mock(status=trigger.STATUS_SKIPPED, web_url=f"https://{GITLAB_HOST}/project1")
    pipeline.jobs.list = MagicMock(return_value=[
        Mock(status=trigger.STATUS_SKIPPED),
        Mock(status=trigger.STATUS_CANCELED),
        Mock(status=trigger.STATUS_FAILED)
    ])
    pipeline_behavior.side_effect = [
        pipeline,
        Mock(status=trigger.STATUS_SKIPPED),
        Mock(status=trigger.STATUS_SKIPPED),
    ]
    return pipeline_behavior


class TriggerTest(unittest.TestCase):
    COMMON_ARGS = f"-h {GITLAB_HOST} -a api_token -p trigger_token --sleep 1 -t master 123"

    def run_trigger(self, cmd_args, mock_get_gitlab, behavior):
        gitlab = some_gitlab(f"https://{GITLAB_HOST}", 'api_token', True, behavior)
        mock_get_gitlab.return_value = gitlab
        temp_stdout = StringIO()
        with contextlib.redirect_stdout(temp_stdout), requests_mock.Mocker() as m:
            m.post(f"https://{GITLAB_HOST}/api/v4/projects/123/trigger/pipeline", text='{"id": "1"}', status_code=201)
            trigger.get_gitlab.cache_clear()
            trigger.get_project.cache_clear()
            pid = trigger.trigger(cmd_args.split(' '))
            assert m.called_once
            assert pid == '1'
        return temp_stdout

    def run_trigger_with_error(self, cmd_args, mock_get_gitlab, behavior):
        gitlab = some_gitlab(f"https://{GITLAB_HOST}", 'api_token', True, behavior)
        mock_get_gitlab.return_value = gitlab
        temp_stdout = StringIO()
        with contextlib.redirect_stdout(temp_stdout), self.assertRaises(trigger.PipelineFailure) as context, requests_mock.Mocker() as m:
            m.post(f"https://{GITLAB_HOST}/api/v4/projects/123/trigger/pipeline", text='{"id": "1"}', status_code=201)
            trigger.get_gitlab.cache_clear()
            trigger.get_project.cache_clear()
            pid = trigger.trigger(cmd_args.split(' '))
            assert m.called_once
            assert pid == '1'
        return (context, temp_stdout)

    def test_args_1(self):
        args = trigger.parse_args('-p ptok -t ref -e foo-1=bar2 -e foo2=bar3 proj'.split())
        assert args.pipeline_token == 'ptok'
        assert args.target_ref == 'ref'
        assert args.env == ['foo-1=bar2', 'foo2=bar3']
        assert args.project_id == 'proj'

    def test_args_2(self):
        with pytest.raises(SystemExit):
            trigger.parse_args('-a foo -e foo1=bar2 foo2=bar3 dangling'.split())

    def test_parse_args_retry(self):
        args = trigger.parse_args('-a foo -p bar -t ref proj'.split())
        assert args.retry is False
        assert args.pid is None
        args = trigger.parse_args('-a foo -p bar -t ref --pid 123 proj'.split())
        assert args.retry is False
        assert args.pid == 123
        args = trigger.parse_args('-a foo -p bar -t ref -r --pid 123 proj'.split())
        assert args.retry is True
        assert args.pid == 123

    def test_parse_env(self):
        envs = trigger.parse_env(['foo-1=bar2', 'foo2=bar3='])
        assert envs == {'variables[foo-1]': 'bar2', 'variables[foo2]': 'bar3='}

    @mock.patch('gitlab.Gitlab')
    def test_trigger_manual_play_no_jobs_specified(self, mock_get_gitlab):
        cmd_args = TriggerTest.COMMON_ARGS + " --on-manual play"
        temp_stdout = self.run_trigger(cmd_args, mock_get_gitlab, some_manual_pipeline_behavior(trigger.STATUS_SUCCESS))

        expected_output = """Triggering pipeline for ref 'master' for project id 123
Pipeline created (id: 1)
See pipeline at https://example.com/project1/pipelines/1
Waiting for pipeline 1 to finish ...

Playing manual job "manual1" from stage "stage1"...
...
Pipeline succeeded"""
        self.assertEqual(temp_stdout.getvalue().strip(), expected_output)

    @mock.patch('gitlab.Gitlab')
    def test_trigger_manual_play_one_job_specified(self, mock_get_gitlab):
        cmd_args = TriggerTest.COMMON_ARGS + " --on-manual play --jobs manual2"
        temp_stdout = self.run_trigger(cmd_args, mock_get_gitlab, some_manual_pipeline_behavior(trigger.STATUS_SUCCESS))

        expected_output = """Triggering pipeline for ref 'master' for project id 123
Pipeline created (id: 1)
See pipeline at https://example.com/project1/pipelines/1
Waiting for pipeline 1 to finish ...

Playing manual job "manual2" from stage "stage2"...
...
Pipeline succeeded"""
        self.assertEqual(temp_stdout.getvalue().strip(), expected_output)

    @mock.patch('gitlab.Gitlab')
    def test_trigger_manual_play_two_jobs_specified(self, mock_get_gitlab):
        cmd_args = TriggerTest.COMMON_ARGS + " --on-manual play --jobs manual2,manual1"
        temp_stdout = self.run_trigger(cmd_args, mock_get_gitlab, some_manual_pipeline_behavior(trigger.STATUS_SUCCESS))

        expected_output = """Triggering pipeline for ref 'master' for project id 123
Pipeline created (id: 1)
See pipeline at https://example.com/project1/pipelines/1
Waiting for pipeline 1 to finish ...

Playing manual job "manual2" from stage "stage2"...

Playing manual job "manual1" from stage "stage1"...
...
Pipeline succeeded"""
        self.assertEqual(temp_stdout.getvalue().strip(), expected_output)

    @mock.patch('gitlab.Gitlab')
    def test_trigger_manual_play_no_manual_jobs_in_pipeline(self, mock_get_gitlab):
        cmd_args = TriggerTest.COMMON_ARGS + " --on-manual play"

        (context, temp_stdout) = self.run_trigger_with_error(cmd_args, mock_get_gitlab, some_invalid_manual_pipeline_behavior())

        self.assertTrue(context.exception and context.exception.pipeline_id == '1')

        expected_output = """Triggering pipeline for ref 'master' for project id 123
Pipeline created (id: 1)
See pipeline at https://example.com/project1/pipelines/1
Waiting for pipeline 1 to finish ...

No manual jobs found!
.
Pipeline failed! Check details at 'https://example.com/project1'"""
        self.assertEqual(temp_stdout.getvalue().strip(), expected_output)
