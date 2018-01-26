#!/bin/bash
set -e

# vars
# API_TOKEN
# PIPELINE_TOKEN
# TARGET_BRANCH
# PROJECT_ID

TARGET_BRANCH="master"
ENVS=()

usage() { echo "Usage: $0 -a <api token> -p <pipeline token> [-e key=value] [-t <target branch (default: master)>] <project id>" 1>&2; exit 1; }

while getopts ":a:e:p:t:" o; do
    case "${o}" in
        a)
            API_TOKEN="${OPTARG}"
            ;;
        e)
            ENVS+=("${OPTARG}")
            ;;
        p)
            PIPELINE_TOKEN="${OPTARG}"
            ;;
        t)
            TARGET_BRANCH="${OPTARG}"
            ;;
        *)
            usage
            ;;
    esac
done
shift $((OPTIND-1))

PROJECT_ID="$@"


if [ -z "$API_TOKEN" ]; then
    echo "api token (or personal token) not set"
    usage
    exit 1
fi

if [ -z "$PIPELINE_TOKEN" ]; then
    echo "pipeline token not set"
    usage
    exit 1
fi

if [ -z "$TARGET_BRANCH" ]; then
    echo "target branch not set"
    usage
    exit 1
fi

if [ -z "$PROJECT_ID" ]; then
    echo "project id not set"
    usage
    exit 1
fi

VAR_ARGS=()
for env in "${ENVS[@]}"; do
    IFS='=' read -r -a envs <<< "$env"
    if [ ${#envs[@]} -ne 2 ]; then
        echo Not a key value pair: $env
        continue
    fi
    VAR_ARGS+=("variables[${envs[0]}]=${envs[1]}")
done


PROJ_URL=https://gitlab.com/api/v4/projects/${PROJECT_ID}

function pstatus {
    PIPELINE=$1
    curl -s -X GET -H "PRIVATE-TOKEN: $API_TOKEN" ${PROJ_URL}/pipelines/$PIPELINE | jq -r '.status'
}

echo "Triggering pipeline ..."

cmd=(curl -s -X POST -F token=$PIPELINE_TOKEN -F "ref=$TARGET_BRANCH")
for var_arg in ${VAR_ARGS[@]}; do
    cmd+=(-F "$var_arg")
done
cmd+=(${PROJ_URL}/trigger/pipeline)
ID=$("${cmd[@]}" | jq -r '.id')

if [ "$ID" == 'null' ]; then
    echo "Triggering pipeline failed"
    echo "Please verify your parameters by running the following command manually:"
    echo "${cmd[@]}"
    exit 1
fi

echo Pipeline id: $ID

echo "Waiting for pipeline to finish ..."

# see https://docs.gitlab.com/ee/ci/pipelines.html for states
until [[ \
    $( pstatus $ID ) = 'failed' \
    || $( pstatus $ID ) = 'warning' \
    || $( pstatus $ID ) = 'manual' \
    || $( pstatus $ID ) = 'canceled' \
    || $( pstatus $ID ) = 'success' \
    || $( pstatus $ID ) = 'skipped' \
]]
do
    echo -n '.'
    sleep 5
done

echo
echo Done

[ $( pstatus $ID ) = 'success' ]
