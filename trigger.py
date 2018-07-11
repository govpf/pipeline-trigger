#!/usr/bin/env python

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


@lru_cache(maxsize=None)
def get_gitlab(url, api_token):
    return gitlab.Gitlab(url, private_token=api_token)


@lru_cache(maxsize=None)
def get_project(url, api_token, proj_id):
    return get_gitlab(url, api_token).projects.get(proj_id)


def parse_args(args):
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
    parser.add_argument('-p', '--pipeline-token', required=True, help='pipeline token')
    parser.add_argument('-r', '--retry', action='store_true', default=False, help='retry pipeline')
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


def trigger():
    args = parse_args(sys.argv[1:])

    assert args.pipeline_token, 'pipeline token must be set'
    assert args.project_id, 'project id must be set'
    assert args.host, 'host must be set'
    assert args.url_path, 'url path must be set'
    assert args.target_ref, 'must provide target ref'
    assert args.sleep > 0, 'sleep parameter must be > 0'

    ref = args.target_ref
    proj_id = args.project_id
    pipeline_token = args.pipeline_token
    base_url = f'https://{args.host}'
    project_url = f"{base_url}{args.url_path}/{proj_id}"
    variables = {}
    if args.env is not None:
        variables = parse_env(args.env)

    if args.retry:
        assert args.api_token is not None, 'retry checks require an api token (-a parameter missing)'
        print(f"Looking for pipeline '{ref}' for project id {proj_id} ...")
        pipeline = get_last_pipeline(project_url, args.api_token, ref)
        pid = pipeline.get('id')
        status = pipeline.get('status')
        assert pid is not None, 'last pipeline id must not be none'
        assert status is not None, 'last pipeline status must not be none'
        print(f"Found pipeline {pid} with status '{status}'")
        if status == 'success':
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

    if args.detached:
        print('Detached mode: not monitoring pipeline status - exiting now.')
        sys.exit(0)

    assert pid is not None, 'must have a valid pipeline id'

    print("Waiting for pipeline to finish ...")

    status = None
    max_retries = 5
    retries_left = max_retries

    while status not in finished_states:
        try:
            assert args.api_token is not None, 'pipeline status checks require an api token (-a parameter missing)'
            proj = get_project(base_url, args.api_token, proj_id)
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
                sys.exit(2)
            retries_left -= 1

        print('.', end='', flush=True)
        sleep(args.sleep)

    print()

    if status == 'success':
        ret = 0
        print('Pipeline succeeded')
    else:
        ret = 1
        print(f'Pipeline failed with status: {status}')

    sys.exit(ret)


if __name__ == "__main__":
    trigger()
