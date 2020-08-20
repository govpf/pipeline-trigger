#!/usr/bin/env python
# %%

import argparse
import sys
import urllib.parse
from functools import lru_cache
from time import sleep
from typing import Dict, List, Optional

import gitlab
import requests

STATUS_FAILED = 'failed'
STATUS_MANUAL = 'manual'
STATUS_CANCELED = 'canceled'
STATUS_SUCCESS = 'success'
STATUS_SKIPPED = 'skipped'

ACTION_FAIL = 'fail'
ACTION_PASS = 'pass'
ACTION_PLAY = 'play'

# see https://docs.gitlab.com/ee/ci/pipelines.html for states
finished_states = [
    STATUS_FAILED,
    STATUS_MANUAL,
    STATUS_CANCELED,
    STATUS_SUCCESS,
    STATUS_SKIPPED,
]


class PipelineFailure(Exception):
    def __init__(self, return_code=None, pipeline_id=None):
        self.return_code = return_code
        self.pipeline_id = pipeline_id


@lru_cache(maxsize=None)
def get_gitlab(url, api_token, verifyssl):
    return gitlab.Gitlab(url, private_token=api_token, ssl_verify=verifyssl)


@lru_cache(maxsize=None)
def get_project(url, api_token, proj_id, verifyssl):
    return get_gitlab(url, api_token, verifyssl).projects.get(proj_id)


def parse_args(args: List[str]):
    parser = argparse.ArgumentParser(
        description='Tool to trigger and monitor a remote GitLab pipeline',
        add_help=False)
    parser.add_argument(
        '-a', '--api-token', help='personal access token (not required when running detached)')
    parser.add_argument('-d', '--detached', action='store_true', default=False)
    parser.add_argument('-e', '--env', action='append')
    parser.add_argument('-h', '--host', default='gitlab.com')
    parser.add_argument(
        '--help', action='help', help='show this help message and exit')
    parser.add_argument('--jobs', help='comma-separated list of manual jobs to run on `--on-manual play`')
    parser.add_argument('-o', '--output', action='store_true', default=False, help='Show triggered pipline job output upon completion')
    parser.add_argument('--on-manual', default=ACTION_FAIL, choices=[ACTION_FAIL, ACTION_PASS, ACTION_PLAY], help='action if "manual" status occurs')
    parser.add_argument('-p', '--pipeline-token', required=True, help='pipeline token')
    parser.add_argument('--pid', type=int, default=None, help='optional pipeline id of remote pipeline to be retried (implies -r)')
    parser.add_argument('-r', '--retry', action='store_true', default=False, help='retry latest pipeline for given TARGET_REF')
    parser.add_argument('-s', '--sleep', type=int, default=5)
    parser.add_argument('-t', '--target-ref', required=True, help='target ref (branch, tag, commit)')
    parser.add_argument('-u', '--url-path', default='/api/v4/projects')
    parser.add_argument('-v', '--verifyssl', type=str2bool, default=True, help='Activate the ssl verification, set false for Self-signed certificate')
    parser.add_argument('--verbose', action='store_true', default=False, help='verbose logging of responses')
    parser.add_argument('project_id')
    parsed_args = parser.parse_args(args)
    return parsed_args


def str2bool(v):
    if isinstance(v, bool):
        return v
    if v.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif v.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')


def parse_env(envs: List[str]) -> List[Dict]:
    res = {}
    for e in envs:
        k, v = e.split('=', 1)
        res[f'variables[{k}]'] = v
    return res


def create_pipeline(project_url, pipeline_token, ref, verifyssl, variables={}, verbose=False) -> Optional[int]:
    data = variables.copy()
    data.update(token=pipeline_token, ref=ref)
    r = requests.post(
        f'{project_url}/trigger/pipeline',
        data=data,
        verify=verifyssl
    )
    if verbose:
        print(f'Response create_pipeline: {r.text}')
    assert r.status_code == 201, f'Failed to create pipeline, api returned status code {r.status_code}'
    pid = r.json().get('id', None)
    print(f'Pipeline created (id: {pid})')
    return pid


def get_pipeline(project_url, api_token, pid, verifyssl, verbose=False):
    r = requests.get(
        f'{project_url}/pipelines/{pid}',
        headers={
            'PRIVATE-TOKEN': api_token
        },
        verify=verifyssl
    )
    if verbose:
        print(f'Response get_pipeline: {r.text}')
    assert r.status_code == 200, f'expected status code 200, was {r.status_code}'
    return r.json()


def get_last_pipeline(project_url, api_token, ref, verifyssl, verbose=False):
    r = requests.get(
        f'{project_url}/pipelines',
        headers={
            'PRIVATE-TOKEN': api_token
        },
        params=dict(
            ref=ref,
            order_by='id',
            sort='desc'
        ),
        verify=verifyssl
    )
    if verbose:
        print(f'Response get_last_pipeline: {r.text}')
    assert r.status_code == 200, f'expected status code 200, was {r.status_code}'
    res = r.json()
    assert len(res) > 0, f'expected to find at least one pipeline for ref {ref}'
    return res[0]


def get_pipeline_jobs(project_url, api_token, pipeline, verifyssl, verbose=False):
    r = requests.get(
        f'{project_url}/pipelines/{pipeline}/jobs',
        headers={
            'PRIVATE-TOKEN': api_token
        },
        verify=verifyssl
    )
    if verbose:
        print(f'Response get_pipeline_jobs: {r.text}')
    assert r.status_code == 200, f'expected status code 200, was {r.status_code}'
    res = r.json()
    return res


def get_job_trace(project_url, api_token, job, verifyssl, verbose=False):
    r = requests.get(
        f'{project_url}/jobs/{job}/trace',
        headers={
            'PRIVATE-TOKEN': api_token
        },
        verify=verifyssl
    )
    if verbose:
        print(f'Response get_job_trace: {r.text}')
    assert r.status_code == 200, f'expected status code 200, was {r.status_code}'
    r.encoding = 'utf-8'
    return r.text


def get_sha(project_url, api_token, ref, verifyssl, verbose=False) -> Optional[str]:
    """ Get the sha at the tip of ref
    """
    r = requests.get(
        f'{project_url}/repository/commits/{ref}',
        headers={
            'PRIVATE-TOKEN': api_token
        },
        verify=verifyssl
    )
    if verbose:
        print(f'Response get_sha: {r.text}')
    assert r.status_code == 200, f'expected status code 200, was {r.status_code}'
    return r.json().get('id')


def get_project_id(project_url, api_token, project_name, verifyssl, verbose=False):
    assert project_name is not None, 'expected TRIGGER_PROJECT_NAME defined'
    r = requests.get(
        f"{project_url}/{urllib.parse.quote(project_name, safe='')}",
        headers={
            'PRIVATE-TOKEN': api_token
        },
        verify=verifyssl
    )
    if verbose:
        print(f'Response get_project_id: {r.text}')
    assert r.status_code == 200, f'expected status code 200, was {r.status_code}'
    res = r.json()
    return str(res['id'])


def isint(x):
    try:
        int(x)
    except Exception:
        return False
    else:
        return True


def handle_manual_pipeline(args, pipeline, proj, status):
    defined_jobs = [item for item in args.jobs.split(',')] if args.jobs else []
    manual_jobs = []
    for job in pipeline.jobs.list(per_page=100):
        if job.status == STATUS_MANUAL:
            # pick the first manual job and exit the loop
            if len(defined_jobs) == 0:
                manual_jobs.append(job)
                break
            elif job.name in defined_jobs:
                manual_jobs.append(job)
    if len(manual_jobs) == 0:
        print('\nNo manual jobs found!')
    else:
        # wipe status, because the pipeline will continue after playing the manual job
        status = None
        if len(defined_jobs) > 0:
            # sort by name of --jobs argument to preserve the order of execution
            manual_jobs.sort(key=lambda j: defined_jobs.index(j.name))
        for manual_job in manual_jobs:
            print(f'\nPlaying manual job "{manual_job.name}" from stage "{manual_job.stage}"...')
            proj.jobs.get(manual_job.id, lazy=True).play()
    return status


def check_pipeline_status(args, pid, proj, project_url):
    pipeline = None
    status = None
    max_retries = 5
    retries_left = max_retries
    while retries_left >= 0:
        try:
            pipeline = proj.pipelines.get(pid)
            status = pipeline.status
            if status in [STATUS_MANUAL, STATUS_SKIPPED] and args.on_manual == ACTION_PLAY:
                status = handle_manual_pipeline(args, pipeline, proj, status)

            # reset retries_left if the status call succeeded (fail only on consecutive failures)
            retries_left = max_retries
            break
        except Exception as e:
            print(f'\nPolling for status failed: {e}')
            if retries_left == 0:
                print(f'Polling failed {max_retries} consecutive times. Please verify the pipeline url:')
                print(f'   curl -s -X GET -H "PRIVATE-TOKEN: <private token>" {project_url}/pipelines/{pid}')
                print('check your api token, or check if there are connection issues.')
                print()
                raise PipelineFailure(return_code=2, pipeline_id=pid)
            retries_left -= 1
    return pipeline, status


def trigger(args: List[str]) -> int:
    args = parse_args(args)

    assert args.pipeline_token, 'pipeline token must be set'
    assert args.project_id, 'project id must be set'
    assert args.host, 'host must be set'
    assert args.url_path, 'url path must be set'
    assert args.target_ref, 'must provide target ref'
    assert args.sleep > 0, 'sleep parameter must be > 0'

    ref = args.target_ref
    proj_id = args.project_id
    pipeline_token = args.pipeline_token
    verifyssl = args.verifyssl
    verbose = args.verbose

    if args.host.startswith('http://') or args.host.startswith('https://'):
        base_url = args.host
    else:
        base_url = f'https://{args.host}'

    if not isint(proj_id):
        assert args.api_token is not None, 'finding project id by name requires an api token (-a parameter missing)'
        proj_id = get_project_id(f"{base_url}{args.url_path}", args.api_token, proj_id, verifyssl, verbose)

    project_url = f"{base_url}{args.url_path}/{proj_id}"
    variables = {}
    if args.env is not None:
        variables = parse_env(args.env)

    if args.retry or args.pid is not None:
        assert args.api_token is not None, 'retry checks require an api token (-a parameter missing)'

        if args.pid is None:
            print(f"Looking for pipeline '{ref}' for project id {proj_id} ...")
            pipeline = get_last_pipeline(project_url, args.api_token, ref, verifyssl, verbose)
            pid = pipeline.get('id')
        else:
            pid = args.pid
            print(f"Fetching for pipeline '{pid}' for project id {proj_id} ...")
            pipeline = get_pipeline(project_url, args.api_token, pid, verifyssl, verbose)

        status = pipeline.get('status')
        assert pid, 'refresh pipeline id must not be none'
        assert status, 'refresh pipeline status must not be none'

        pipeline_sha = pipeline.get('sha')
        ref_tip_sha = get_sha(project_url, args.api_token, ref, verifyssl, verbose)
        outdated = pipeline_sha != ref_tip_sha

        outdated_str = 'outdated' if outdated else 'up to date'
        print(f"Found {outdated_str} pipeline {pid} with status '{status}'")

        if outdated:
            print(f"Pipeline {pid} for {ref} outdated (sha: {pipeline_sha[:6]}, tip is {ref_tip_sha[:6]}) - re-running ...")
            pid = create_pipeline(project_url, pipeline_token, ref, verifyssl, variables, verbose)
        elif status == STATUS_SUCCESS:
            print(f"Pipeline {pid} already in state 'success' - re-running ...")
            pid = create_pipeline(project_url, pipeline_token, ref, verifyssl, variables, verbose)
        else:
            print(f"Retrying pipeline {pid} ...")
            proj = get_project(base_url, args.api_token, proj_id, verifyssl)
            proj.pipelines.get(pid).retry()

    else:
        print(f"Triggering pipeline for ref '{ref}' for project id {proj_id}")
        pid = create_pipeline(project_url, pipeline_token, ref, verifyssl, variables, verbose)
        try:
            proj = get_project(base_url, args.api_token, proj_id, verifyssl)
            print(f"See pipeline at {proj.web_url}/pipelines/{pid}")
        except Exception:
            # get_projects can fail if no api_token has been provided
            # since we're only logging here we simply ignore this
            pass

    assert pid is not None, 'must have a valid pipeline id'

    if args.detached:
        if args.on_manual == ACTION_PLAY:  # detached for manual pipelines
            proj = get_project(base_url, args.api_token, proj_id, verifyssl)
            check_pipeline_status(args, pid, proj, project_url)
        print('Detached mode: not monitoring pipeline status - exiting now.')
        return pid

    # after this point (i.e. not running detached) we require api_token to be set
    api_token = args.api_token
    assert api_token is not None, 'pipeline status checks require an api token (-a parameter missing)'

    print(f"Waiting for pipeline {pid} to finish ...")

    status = None
    pipeline = None
    proj = get_project(base_url, api_token, proj_id, verifyssl)

    while status not in finished_states:
        pipeline, status = check_pipeline_status(args, pid, proj, project_url)

        print('.', end='', flush=True)
        sleep(args.sleep)

    print()
    if args.output:
        jobs = get_pipeline_jobs(project_url, api_token, pid, verifyssl, verbose)
        print(f'Pipeline {pid} job output:')
        for job in jobs:
            name = job['name']
            print(f'Job: {name}')
            print(get_job_trace(project_url, api_token, job['id'], verifyssl, verbose))
            print()

    if status == STATUS_SUCCESS:
        print('Pipeline succeeded')
        return pid
    elif status == STATUS_MANUAL and args.on_manual == ACTION_PASS:
        print('Pipeline status is "manual", action "pass"')
        return pid
    else:
        print(f"Pipeline failed! Check details at '{pipeline.web_url}'")
        raise PipelineFailure(return_code=1, pipeline_id=pid)


if __name__ == "__main__":  # pragma: nocover
    try:
        trigger(sys.argv[1:])
        sys.exit(0)
    except PipelineFailure as e:
        sys.exit(e.return_code)
