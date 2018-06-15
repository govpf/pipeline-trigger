#!/usr/bin/env python

import argparse
import sys
from time import sleep
from typing import Dict, List, Optional

import gitlab
import requests

finished_states = [
    'failed',
    'manual',
    'canceled',
    'success',
    'skipped'
]


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
    parser.add_argument('-r', '--ref', help='target ref (branch, tag, sha)')
    parser.add_argument('-s', '--sleep', type=int, default=5)
    parser.add_argument('-t', '--target-branch', help='target branch (deprecated: use -r instead)')
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
    assert r.status_code == 201, f'expected status code 200, was {r.status_code}'
    return r.json().get('id', None)


def trigger():
    args = parse_args(sys.argv[1:])

    assert args.pipeline_token, 'pipeline token must be set'
    assert args.project_id, 'project id must be set'
    assert args.host, 'host must be set'
    assert args.url_path, 'url path must be set'
    assert args.ref or args.target_branch, 'must provide either ref (-r) or target_branch (-t)'
    assert args.sleep > 0, 'sleep parameter must be > 0'

    ref = args.ref or args.target_branch
    proj_id = args.project_id
    pipeline_token = args.pipeline_token
    project_url = f"https://{args.host}{args.url_path}/{proj_id}"
    variables = {}
    if args.env is not None:
        variables = parse_env(args.env)

    print(f"Triggering pipeline for ref '{ref}' for project id: {proj_id})")

    pid = None

    retry = False
    if retry:
        pass
    else:
        pid = create_pipeline(project_url, pipeline_token, ref, variables)
        print(f'Pipeline created (id: {pid})')

    if args.detached:
        print('Detached mode: not monitoring pipeline status - exiting now.')
        sys.exit(0)

    assert pid is not None, 'must have a valid pipeline id'
    assert args.api_token, 'api token must be set (unless running in detached mode)'

    gl = gitlab.Gitlab(f'https://{args.host}', private_token=args.api_token)
    proj = gl.projects.get(proj_id)

    status = None
    max_retries = 5
    retries_left = max_retries

    while status not in finished_states:
        try:
            status = proj.pipelines.get(pid).status
            # reset retries_left if the status call succeeded (fail only on consecutive failures)
            retries_left = max_retries
        except Exception as e:
            print(f'Polling for status failed: {e}')
            retries_left -= 1
            if retries_left == 0:
                print(f'Polling failed {max_retries} consecutive times. Please verify the pipeline url:')
                print(f'   curl -s -X GET -H "PRIVATE-TOKEN: <private token>" {project_url}/pipelines/{pid}')
                print('check your api token, or check if there are connection issues.')
                print()
                sys.exit(2)

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
