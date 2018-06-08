#!/usr/bin/env python

import argparse
import sys
from typing import Dict, List

import gitlab


def parse_args(args):
    parser = argparse.ArgumentParser(
        description='Tool to trigger and monitor a remote GitLab pipeline',
        add_help=False)
    parser.add_argument(
        '-a', '--api-token', required=True, help='personal access token')
    parser.add_argument('-d', '--detached', action='store_true', default=False)
    parser.add_argument('-e', '--env', action='append')
    parser.add_argument('-h', '--host', default='https://gitlab.com')
    parser.add_argument(
        '--help', action='help', help='show this help message and exit')
    parser.add_argument('-t', '--target-branch')
    parser.add_argument('-u', '--url-path')
    parser.add_argument('-s', '--sleep', type=int)
    parser.add_argument('project_id')
    return parser.parse_args(args)


def parse_envs(envs: List[str]) -> List[Dict]:
    res = []
    for e in envs:
        k, v = e.split('=')
        res.append(dict(key=k, value=v))
    return res


def trigger():
    args = parse_args(sys.argv[1:])

    assert args.api_token
    assert args.project_id
    assert args.host

    print('Project id:', args.project_id)

    gl = gitlab.Gitlab(args.host, private_token=args.api_token)
    proj = gl.projects.get(args.project_id)
    print(f'Project name: {proj.name}')


if __name__ == "__main__":
    trigger()
