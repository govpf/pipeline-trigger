import contextlib
import json
import unittest
from inspect import cleandoc
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


def some_auto_pipeline_behavior(final_status):
    pipeline_behavior = Mock()
    pipeline_behavior.side_effect = [
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
    COMMON_ARGS = f"-h {GITLAB_HOST} -a api_token -p trigger_token --sleep 1 -t master"

    def run_trigger(self, cmd_args, mock_get_gitlab, behavior, add_extra_mocks=[]):
        gitlab = some_gitlab(f"https://{GITLAB_HOST}", 'api_token', True, behavior)
        mock_get_gitlab.return_value = gitlab
        temp_stdout = StringIO()
        with contextlib.redirect_stdout(temp_stdout), requests_mock.Mocker() as m:
            m.post(f"https://{GITLAB_HOST}/api/v4/projects/123/trigger/pipeline", text='{"id": "1"}', status_code=201)
            for extra_mock in add_extra_mocks:
                extra_mock(gitlab, m)
            trigger.get_gitlab.cache_clear()
            trigger.get_project.cache_clear()
            pid = trigger.trigger(cmd_args.split(' '))
            assert str(pid) == '1'
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
        return context, temp_stdout

    def test_isint(self):
        assert trigger.isint(42)
        assert trigger.isint('42')
        assert not trigger.isint('something')
        assert not trigger.isint(None)

    def test_str2bool(self):
        assert trigger.str2bool(True)
        assert trigger.str2bool('True')
        assert trigger.str2bool('TRUE')
        assert trigger.str2bool('true')
        assert trigger.str2bool('t')
        assert trigger.str2bool('y')
        assert trigger.str2bool('1')
        assert not trigger.str2bool(False)
        assert not trigger.str2bool('False')
        assert not trigger.str2bool('FALSE')
        assert not trigger.str2bool('false')
        assert not trigger.str2bool('f')
        assert not trigger.str2bool('n')
        assert not trigger.str2bool('0')

    def test_args_1(self):
        args = trigger.parse_args('-p ptok -t ref -e foo-1=bar2 -e foo2=bar3 proj'.split())
        assert args.pipeline_token == 'ptok'
        assert args.target_ref == 'ref'
        assert args.env == ['foo-1=bar2', 'foo2=bar3']
        assert args.project_id == 'proj'

    def test_args_required(self):
        temp_stderr = StringIO()
        with contextlib.redirect_stderr(temp_stderr), self.assertRaises(SystemExit) as context:
            trigger.parse_args('-a foo -e foo1=bar2 foo2=bar3 dangling'.split())
        assert context.exception and isinstance(context.exception, SystemExit) and context.exception.code == 2
        assert 'the following arguments are required: -p/--pipeline-token, -t/--target-ref' in temp_stderr.getvalue().strip()

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

    def test_args_verify_ssl(self):
        args = trigger.parse_args("-p tok -t ref --verifyssl false 123".split())
        assert not args.verifyssl

    def test_args_verify_ssl_short(self):
        args = trigger.parse_args("-p tok -t ref -v true 123".split())
        assert args.verifyssl

    @requests_mock.mock()
    def test_get_pipeline(self, m):
        # happy path
        m.get(
            f"https://xxx/pipelines/123",
            text=json.dumps(dict(foo='bar'))
        )
        res = trigger.get_pipeline(
            f'https://xxx',
            api_token='ignored',
            pid='123',
            verifyssl=True)
        assert res == dict(foo='bar')
        # error path
        m.get(
            f"https://xxx/pipelines/123",
            status_code=404)
        with pytest.raises(AssertionError) as e:
            res = trigger.get_pipeline(
                f'https://xxx',
                api_token='ignored',
                pid='123',
                verifyssl=True)
            assert str(e) == 'AssertionError: expected status code 200, was 404'

    @requests_mock.mock()
    def test_get_pipeline_jobs(self, m):
        # happy path
        m.get(
            f"https://xxx/pipelines/123/jobs",
            text=json.dumps(dict(foo='bar'))
        )
        res = trigger.get_pipeline_jobs(
            f'https://xxx',
            api_token='ignored',
            pipeline='123',
            verifyssl=True)
        assert res == dict(foo='bar')
        # error path
        m.get(
            f"https://xxx/pipelines/123/jobs",
            status_code=404)
        with pytest.raises(AssertionError) as e:
            res = trigger.get_pipeline_jobs(
                f'https://xxx',
                api_token='ignored',
                pipeline='123',
                verifyssl=True)
            assert str(e) == 'AssertionError: expected status code 200, was 404'

    @requests_mock.mock()
    def test_get_job_trace(self, m):
        # happy path
        m.get(
            f"https://xxx/jobs/123/trace",
            text=json.dumps(dict(foo='bar'))
        )
        res = trigger.get_job_trace(
            f'https://xxx',
            api_token='ignored',
            job='123',
            verifyssl=True)
        assert res == '{"foo": "bar"}'
        # error path
        m.get(
            f"https://xxx/pipelines/123/jobs",
            status_code=404)
        with pytest.raises(AssertionError) as e:
            res = trigger.get_job_trace(
                f'https://xxx',
                api_token='ignored',
                job='123',
                verifyssl=True)
            assert str(e) == 'AssertionError: expected status code 200, was 404'

    def test_args_verify_ssl_invalid(self):
        temp_stderr = StringIO()
        with contextlib.redirect_stderr(temp_stderr), self.assertRaises(SystemExit) as context:
            trigger.parse_args("-p tok -t ref -v some_value 123".split())
        assert context.exception and isinstance(context.exception, SystemExit) and context.exception.code == 2
        assert 'argument -v/--verifyssl: Boolean value expected' in temp_stderr.getvalue().strip()

    @mock.patch('gitlab.Gitlab')
    def test_trigger_manual_play_no_jobs_specified(self, mock_get_gitlab):
        cmd_args = TriggerTest.COMMON_ARGS + " --on-manual play 123"
        temp_stdout = self.run_trigger(cmd_args, mock_get_gitlab, some_manual_pipeline_behavior(trigger.STATUS_SUCCESS))

        expected_output = cleandoc("""
            Triggering pipeline for ref 'master' for project id 123
            Pipeline created (id: 1)
            See pipeline at https://example.com/project1/pipelines/1
            Waiting for pipeline 1 to finish ...

            Playing manual job "manual1" from stage "stage1"...
            ...
            Pipeline succeeded
        """)
        self.assertEqual(temp_stdout.getvalue().strip(), expected_output)

    @mock.patch('gitlab.Gitlab')
    def test_trigger_manual_play_one_job_specified(self, mock_get_gitlab):
        cmd_args = TriggerTest.COMMON_ARGS + " --on-manual play --jobs manual2 123"
        temp_stdout = self.run_trigger(cmd_args, mock_get_gitlab, some_manual_pipeline_behavior(trigger.STATUS_SUCCESS))

        expected_output = cleandoc("""
            Triggering pipeline for ref 'master' for project id 123
            Pipeline created (id: 1)
            See pipeline at https://example.com/project1/pipelines/1
            Waiting for pipeline 1 to finish ...

            Playing manual job "manual2" from stage "stage2"...
            ...
            Pipeline succeeded
        """)
        self.assertEqual(temp_stdout.getvalue().strip(), expected_output)

    @mock.patch('gitlab.Gitlab')
    def test_trigger_manual_play_two_jobs_specified(self, mock_get_gitlab):
        cmd_args = TriggerTest.COMMON_ARGS + " --on-manual play --jobs manual2,manual1 123"
        temp_stdout = self.run_trigger(cmd_args, mock_get_gitlab, some_manual_pipeline_behavior(trigger.STATUS_SUCCESS))

        expected_output = cleandoc("""
            Triggering pipeline for ref 'master' for project id 123
            Pipeline created (id: 1)
            See pipeline at https://example.com/project1/pipelines/1
            Waiting for pipeline 1 to finish ...

            Playing manual job "manual2" from stage "stage2"...

            Playing manual job "manual1" from stage "stage1"...
            ...
            Pipeline succeeded
        """)
        self.assertEqual(temp_stdout.getvalue().strip(), expected_output)

    @mock.patch('gitlab.Gitlab')
    def test_trigger_manual_play_no_manual_jobs_in_pipeline(self, mock_get_gitlab):
        cmd_args = TriggerTest.COMMON_ARGS + " --on-manual play 123"

        (context, temp_stdout) = self.run_trigger_with_error(cmd_args, mock_get_gitlab, some_invalid_manual_pipeline_behavior())

        self.assertTrue(context.exception and context.exception.pipeline_id == '1')

        expected_output = cleandoc("""
            Triggering pipeline for ref 'master' for project id 123
            Pipeline created (id: 1)
            See pipeline at https://example.com/project1/pipelines/1
            Waiting for pipeline 1 to finish ...

            No manual jobs found!
            .
            Pipeline failed! Check details at 'https://example.com/project1'
        """)
        self.assertEqual(temp_stdout.getvalue().strip(), expected_output)

    @mock.patch('gitlab.Gitlab')
    def test_trigger_with_project_name(self, mock_get_gitlab):
        cmd_args = TriggerTest.COMMON_ARGS + " username/project_name"

        def extra_mock(gitlab, mock_request):
            mock_request.get(f"https://{GITLAB_HOST}/api/v4/projects/username%2Fproject_name", text='{"id": "123"}', status_code=200)

        temp_stdout = self.run_trigger(cmd_args, mock_get_gitlab, some_auto_pipeline_behavior(trigger.STATUS_SUCCESS), [extra_mock])

        expected_output = cleandoc("""
            Triggering pipeline for ref 'master' for project id 123
            Pipeline created (id: 1)
            See pipeline at https://example.com/project1/pipelines/1
            Waiting for pipeline 1 to finish ...
            ..
            Pipeline succeeded
        """)
        self.assertEqual(temp_stdout.getvalue().strip(), expected_output)

    @mock.patch('gitlab.Gitlab')
    def test_trigger_with_retry_failed(self, mock_get_gitlab):
        """
        Tests retrying a failed pipeline
        """
        project_id = 123
        cmd_args = TriggerTest.COMMON_ARGS + f" --retry {project_id}"

        temp_stdout = self.run_trigger(
            cmd_args,
            mock_get_gitlab,
            some_auto_pipeline_behavior(trigger.STATUS_SUCCESS),
            [
                mock_get_last_pipeline(
                    project_id,
                    [dict(id=1, status='failed', sha='deadbeef')]
                ),
                mock_get_sha(project_id, dict(id='deadbeef'))
            ],
        )

        expected_output = cleandoc("""
            Looking for pipeline 'master' for project id 123 ...
            Found up to date pipeline 1 with status 'failed'
            Retrying pipeline 1 ...
            Waiting for pipeline 1 to finish ...
            .
            Pipeline succeeded
        """)

        self.assertEqual(temp_stdout.getvalue().strip(), expected_output)

    @mock.patch('gitlab.Gitlab')
    def test_trigger_with_retry_outdated(self, mock_get_gitlab):
        """
        Tests retrying an outdated pipeline - we're retrying a pipeline
        but the tip of the branch has a new revision (different from
        the sha the pipeline was run with). We'll want to create a new
        pipeline in this case.
        """
        project_id = 123
        cmd_args = TriggerTest.COMMON_ARGS + f" --retry {project_id}"

        temp_stdout = self.run_trigger(
            cmd_args,
            mock_get_gitlab,
            some_auto_pipeline_behavior(trigger.STATUS_SUCCESS),
            [
                mock_get_last_pipeline(
                    project_id,
                    [dict(id=1, status='failed', sha='deadbeef')]
                ),
                mock_get_sha(project_id, dict(id='newrevision'))
            ],
        )

        expected_output = cleandoc("""
            Looking for pipeline 'master' for project id 123 ...
            Found outdated pipeline 1 with status 'failed'
            Pipeline 1 for master outdated (sha: deadbe, tip is newrev) - re-running ...
            Pipeline created (id: 1)
            Waiting for pipeline 1 to finish ...
            ..
            Pipeline succeeded
        """)

        self.assertEqual(temp_stdout.getvalue().strip(), expected_output)

    @mock.patch('gitlab.Gitlab')
    def test_trigger_with_retry_succeeded(self, mock_get_gitlab):
        """
        Tests retrying a successful pipeline. We'll want to create a new
        pipeline in this case. (Otherwise, once successful, jobs configured
        with --retry would never be able to re-run pipelines.)
        """
        project_id = 123
        cmd_args = TriggerTest.COMMON_ARGS + f" --retry {project_id}"

        temp_stdout = self.run_trigger(
            cmd_args,
            mock_get_gitlab,
            some_auto_pipeline_behavior(trigger.STATUS_SUCCESS),
            [
                mock_get_last_pipeline(
                    project_id,
                    [dict(id=1, status='success', sha='deadbeef')]
                ),
                mock_get_sha(project_id, dict(id='deadbeef'))
            ],
        )

        expected_output = cleandoc("""
            Looking for pipeline 'master' for project id 123 ...
            Found up to date pipeline 1 with status 'success'
            Pipeline 1 already in state 'success' - re-running ...
            Pipeline created (id: 1)
            Waiting for pipeline 1 to finish ...
            ..
            Pipeline succeeded
        """)

        self.assertEqual(temp_stdout.getvalue().strip(), expected_output)

    @mock.patch('gitlab.Gitlab')
    def test_trigger_with_retry_pid_only(self, mock_get_gitlab):
        """
        Tests retrying a pipeline with a give pid (implies --retry).
        """
        proj_id = 123
        pipeline_id = 1
        cmd_args = TriggerTest.COMMON_ARGS + f" --pid {pipeline_id} {proj_id}"

        temp_stdout = self.run_trigger(
            cmd_args,
            mock_get_gitlab,
            some_auto_pipeline_behavior(trigger.STATUS_SUCCESS),
            [
                mock_get_last_pipeline(
                    proj_id,
                    [dict(id=1, status='success', sha='deadbeef')]
                ),
                mock_get_sha(proj_id, dict(id='deadbeef')),
                mock_get_pipeline(
                    proj_id,
                    pipeline_id,
                    dict(status='failed', sha='deadbeef')
                )
            ],
        )

        expected_output = cleandoc("""
            Fetching for pipeline '1' for project id 123 ...
            Found up to date pipeline 1 with status 'failed'
            Retrying pipeline 1 ...
            Waiting for pipeline 1 to finish ...
            .
            Pipeline succeeded
        """)

        self.assertEqual(temp_stdout.getvalue().strip(), expected_output)

    @mock.patch('gitlab.Gitlab')
    def test_trigger_auto_detached(self, mock_get_gitlab):
        """
        Tests retrying a failed pipeline
        """
        project_id = 123
        cmd_args = TriggerTest.COMMON_ARGS + f" --detached {project_id}"

        temp_stdout = self.run_trigger(
            cmd_args,
            mock_get_gitlab,
            some_auto_pipeline_behavior(trigger.STATUS_SUCCESS),
        )

        expected_output = cleandoc("""
            Triggering pipeline for ref 'master' for project id 123
            Pipeline created (id: 1)
            See pipeline at https://example.com/project1/pipelines/1
            Detached mode: not monitoring pipeline status - exiting now.
        """)

        self.assertEqual(expected_output, temp_stdout.getvalue().strip())

    @mock.patch('gitlab.Gitlab')
    def test_trigger_manual_detached(self, mock_get_gitlab):
        """
        Tests retrying a failed pipeline
        """
        project_id = 123
        cmd_args = TriggerTest.COMMON_ARGS + f" --on-manual play --detached {project_id}"

        temp_stdout = self.run_trigger(
            cmd_args,
            mock_get_gitlab,
            some_manual_pipeline_behavior(trigger.STATUS_SUCCESS),
        )

        expected_output = cleandoc("""
            Triggering pipeline for ref 'master' for project id 123
            Pipeline created (id: 1)
            See pipeline at https://example.com/project1/pipelines/1

            Playing manual job "manual1" from stage "stage1"...
            Detached mode: not monitoring pipeline status - exiting now.
        """)

        self.assertEqual(expected_output, temp_stdout.getvalue().strip())

    @mock.patch('gitlab.Gitlab')
    def test_trigger_verbose(self, mock_get_gitlab):
        """
        """
        project_id = 123
        cmd_args = TriggerTest.COMMON_ARGS + f" --verbose {project_id}"

        temp_stdout = self.run_trigger(
            cmd_args,
            mock_get_gitlab,
            some_auto_pipeline_behavior(trigger.STATUS_SUCCESS),
        )

        expected_output = cleandoc("""
            Triggering pipeline for ref 'master' for project id 123
            Response create_pipeline: {"id": "1"}
            Pipeline created (id: 1)
            See pipeline at https://example.com/project1/pipelines/1
            Waiting for pipeline 1 to finish ...
            ..
            Pipeline succeeded
        """)

        self.assertEqual(expected_output, temp_stdout.getvalue().strip())


def mock_get_last_pipeline(project_id: int, response: dict, status_code: int = 200):
    def req_mock(gitlab, mock_request):
        mock_request.get(
            f"https://{GITLAB_HOST}/api/v4/projects/{project_id}/pipelines?ref=master&order_by=id&sort=desc",
            text=json.dumps(response),
            status_code=status_code
        )

    return req_mock


def mock_get_sha(project_id: int, response: dict, status_code: int = 200):
    def req_mock(gitlab, mock_request):
        mock_request.get(
            f"https://{GITLAB_HOST}/api/v4/projects/{project_id}/repository/commits/master",
            text=json.dumps(response),
            status_code=status_code
        )

    return req_mock


def mock_get_pipeline(project_id: int, pipeline_id: int, response: dict, status_code: int = 200):
    def req_mock(gitlab, mock_request):
        mock_request.get(
            f"https://{GITLAB_HOST}/api/v4/projects/{project_id}/pipelines/{pipeline_id}",
            text=json.dumps(response),
            status_code=status_code
        )

    return req_mock
