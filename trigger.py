#!/usr/bin/env python
# %%

import argparse
import sys
from functools import lru_cache
from time import sleep
from typing import Dict, List, Optional

import gitlab
import requests

# see https://docs.gitlab.com/ee/ci/pipelines.html for states
finished_states = [
    'failed',
    'manual',
    'canceled',
    'success',
    'skipped'
]


class PipelineFailure(Exception):
    def __init__(self, return_code=None, pipeline_id=None):
        self.return_code = return_code
        self.pipeline_id = pipeline_id


@lru_cache(maxsize=None)
def get_gitlab(url, api_token):
    return gitlab.Gitlab(url, private_token=api_token)


@lru_cache(maxsize=None)
def get_project(url, api_token, proj_id):
    return get_gitlab(url, api_token).projects.get(proj_id)


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
    parser.add_argument('-o', '--output', action='store_true', default=False, help='Show triggered pipline job output upon completion')
    parser.add_argument('-p', '--pipeline-token', required=True, help='pipeline token')
    parser.add_argument('--pid', type=int, default=None, help='optional pipeline id of remote pipeline to be retried (implies -r)')
    parser.add_argument('-r', '--retry', action='store_true', default=False, help='retry latest pipeline for given TARGET_REF')
    parser.add_argument('-s', '--sleep', type=int, default=5)
    parser.add_argument('-t', '--target-ref', required=True, help='target ref (branch, tag, commit)')
    parser.add_argument('-u', '--url-path', default='/api/v4/projects')
    parser.add_argument('project_id')
    return parser.parse_args(args)


def parse_env(envs: List[str]) -> List[Dict]:
    res = {}
    for e in envs:
        k, v = e.split('=')
        res[f'variables[{k}]'] = v
    return res


def create_pipeline(project_url, pipeline_token, ref, variables={}) -> Optional[int]:
    data = variables.copy()
    data.update(token=pipeline_token, ref=ref)
    r = requests.post(
        f'{project_url}/trigger/pipeline',
        data=data
    )
    assert r.status_code == 201, f'Failed to create pipeline, api returned status code {r.status_code}'
    pid = r.json().get('id', None)
    print(f'Pipeline created (id: {pid})')
    return pid


def get_pipeline(project_url, api_token, pid):
    r = requests.get(
        f'{project_url}/pipelines/{pid}',
        headers={
            'PRIVATE-TOKEN': api_token
        }
    )
    assert r.status_code == 200, f'expected status code 200, was {r.status_code}'
    return r.json()


def get_last_pipeline(project_url, api_token, ref):
    r = requests.get(
        f'{project_url}/pipelines',
        headers={
            'PRIVATE-TOKEN': api_token
        },
        params=dict(
            ref=ref,
            order_by='id',
            sort='desc'
        )
    )
    assert r.status_code == 200, f'expected status code 200, was {r.status_code}'
    res = r.json()
    assert len(res) > 0, f'expected to find at least one pipeline for ref {ref}'
    return res[0]


def get_pipeline_jobs(project_url, api_token, pipeline):
    r = requests.get(
        f'{project_url}/pipelines/{pipeline}/jobs',
        headers={
            'PRIVATE-TOKEN': api_token
        }
    )
    assert r.status_code == 200, f'expected status code 200, was {r.status_code}'
    res = r.json()
    return res


def get_job_trace(project_url, api_token, job):
    r = requests.get(
        f'{project_url}/jobs/{job}/trace',
        headers={
            'PRIVATE-TOKEN': api_token
        }
    )
    assert r.status_code == 200, f'expected status code 200, was {r.status_code}'
    r.encoding = 'utf-8'
    return r.text


def get_sha(project_url, api_token, ref) -> Optional[str]:
    """ Get the sha at the tip of ref
    """
    r = requests.get(
        f'{project_url}/repository/commits/{ref}',
        headers={
            'PRIVATE-TOKEN': api_token
        }
    )
    assert r.status_code == 200, f'expected status code 200, was {r.status_code}'
    return r.json().get('id')


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
    if args.host.startswith('http://') or args.host.startswith('https://'):
        base_url = args.host
    else:
        base_url = f'https://{args.host}'
    project_url = f"{base_url}{args.url_path}/{proj_id}"
    variables = {}
    if args.env is not None:
        variables = parse_env(args.env)

    if args.retry or args.pid is not None:
        assert args.api_token is not None, 'retry checks require an api token (-a parameter missing)'

        if args.pid is None:
            print(f"Looking for pipeline '{ref}' for project id {proj_id} ...")
            pipeline = get_last_pipeline(project_url, args.api_token, ref)
            pid = pipeline.get('id')
        else:
            pid = args.pid
            print(f"Fetching for pipeline '{pid}' for project id {proj_id} ...")
            pipeline = get_pipeline(project_url, args.api_token, pid)

        status = pipeline.get('status')
        assert pid, 'refresh pipeline id must not be none'
        assert status, 'refresh pipeline status must not be none'

        pipeline_sha = pipeline.get('sha')
        ref_tip_sha = get_sha(project_url, args.api_token, ref)
        outdated = pipeline_sha != ref_tip_sha

        outdated_str = 'outdated' if outdated else 'up to date'
        print(f"Found {outdated_str} pipeline {pid} with status '{status}'")

        if outdated:
            print(f"Pipeline {pid} for {ref} outdated (sha: {pipeline_sha[:6]}, tip is {ref_tip_sha[:6]}) - re-running ...")
            pid = create_pipeline(project_url, pipeline_token, ref, variables)
        elif status == 'success':
            print(f"Pipeline {pid} already in state 'success' - re-running ...")
            pid = create_pipeline(project_url, pipeline_token, ref, variables)
        else:
            print(f"Retrying pipeline {pid} ...")
            proj = get_project(base_url, args.api_token, proj_id)
            proj.pipelines.get(pid).retry()

    else:
        print(f"Triggering pipeline for ref '{ref}' for project id {proj_id}")
        pid = create_pipeline(project_url, pipeline_token, ref, variables)
        try:
            proj = get_project(base_url, args.api_token, proj_id)
            print(f"See pipeline at {proj.web_url}/pipelines/{pid}")
        except Exception:
            # get_projects can fail if no api_token has been provided
            # since we're only logging here we simply ignore this
            pass

    assert pid is not None, 'must have a valid pipeline id'

    if args.detached:
        print('Detached mode: not monitoring pipeline status - exiting now.')
        return pid

    # after this point (i.e. not running detached) we require api_token to be set
    api_token = args.api_token
    assert api_token is not None, 'pipeline status checks require an api token (-a parameter missing)'

    print(f"Waiting for pipeline {pid} to finish ...")

    status = None
    max_retries = 5
    retries_left = max_retries

    while status not in finished_states:
        try:
            proj = get_project(base_url, api_token, proj_id)
            status = proj.pipelines.get(pid).status
            # reset retries_left if the status call succeeded (fail only on consecutive failures)
            retries_left = max_retries
        except Exception as e:
            print(f'Polling for status failed: {e}')
            if retries_left == 0:
                print(f'Polling failed {max_retries} consecutive times. Please verify the pipeline url:')
                print(f'   curl -s -X GET -H "PRIVATE-TOKEN: <private token>" {project_url}/pipelines/{pid}')
                print('check your api token, or check if there are connection issues.')
                print()
                raise PipelineFailure(return_code=2, pipeline_id=pid)
            retries_left -= 1

        print('.', end='', flush=True)
        sleep(args.sleep)

    print()
    if args.output:
        jobs = get_pipeline_jobs(project_url, api_token, pid)
        print(f'Pipeline {pid} job output:')
        for job in jobs:
            name = job['name']
            print(f'Job: {name}')
            print(get_job_trace(project_url, api_token, job['id']))
            print()

    if status == 'success':
        print('Pipeline succeeded')
        return pid
    else:
        raise PipelineFailure(return_code=1, pipeline_id=pid)


if __name__ == "__main__":
    try:
        trigger(sys.argv[1:])
        sys.exit(0)
    except PipelineFailure as e:
        sys.exit(e.return_code)
