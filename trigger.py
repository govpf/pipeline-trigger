#!/usr/bin/env python

import argparse
import sys

import gitlab


def trigger():
    parser = argparse.ArgumentParser(description='Tool to trigger and monitor a remote GitLab pipeline', add_help=False)
    parser.add_argument(
        '-a', '--api-token', help='api token to query status')
    parser.add_argument('-d', '--detached', action='store_true', default=False)
    parser.add_argument('-e', '--env')
    parser.add_argument('-h', '--host', default='https://gitlab.com')
    parser.add_argument('--help', action='help', help='show this help message and exit')
    parser.add_argument('-p', '--pipeline-token', required=True)
    parser.add_argument('-t', '--target-branch')
    parser.add_argument('-u', '--url-path')
    parser.add_argument('-s', '--sleep', type=int)
    parser.add_argument('project_id')
    args = parser.parse_args()

    assert args.pipeline_token
    assert args.project_id
    assert args.host

    print('Pipeline token:', args.pipeline_token)
    print('Project id:', args.project_id)

    gl = gitlab.Gitlab(args.host, private_token=args.pipeline_token)
    proj_b = gl.projects.get(4624517)
    print(f'Project name: {proj_b.name}')


if __name__ == "__main__":
    trigger()
