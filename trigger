#!/bin/bash
set -e

# vars
# API_TOKEN
# PIPELINE_TOKEN
# TARGET_BRANCH
# PROJECT_ID

TARGET_BRANCH="master"
HOST="gitlab.com"
URL_PATH="/api/v4/projects"
ENVS=()
RESPONSE=""
SLEEP=5

usage() { echo "Usage: $0 -a <api token> -p <pipeline token> [-e key=value] [-h <host (default: $HOST)>] [-t <target branch (default: $TARGET_BRANCH)>] [-u <url path (default: $URL_PATH)] [-s <sleep seconds (default: $SLEEP)>] <project id>" 1>&2; exit 1; }

while getopts ":a:e:h:p:t:u:s:" o; do
    case "${o}" in
        a)
            API_TOKEN="${OPTARG}"
            ;;
        e)
            ENVS+=("${OPTARG}")
            ;;
        h)
            HOST="${OPTARG}"
            ;;
        p)
            PIPELINE_TOKEN="${OPTARG}"
            ;;
        t)
            TARGET_BRANCH="${OPTARG}"
            ;;
        u)
            URL_PATH="${OPTARG}"
            ;;
        s)
            SLEEP="${OPTARG}"
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


PROJ_URL=https://${HOST}${URL_PATH}/${PROJECT_ID}

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

MAX_RETRIES=5
RETRIES_LEFT=$MAX_RETRIES

# see https://docs.gitlab.com/ee/ci/pipelines.html for states
until [[ \
    $RESPONSE = 'failed' \
    || $RESPONSE = 'warning' \
    || $RESPONSE = 'manual' \
    || $RESPONSE = 'canceled' \
    || $RESPONSE = 'success' \
    || $RESPONSE = 'skipped' \
]]
do
    RESPONSE=$( pstatus $ID )

    if [[ -z "$RES" || "$RES" == 'null' ]]; then
        # pstatus failed - maybe a 4xx or a gitlab hiccup (5xx)
        RETRIES_LEFT=$((RETRIES_LEFT-1))
        if [ $RETRIES_LEFT -eq 0 ]; then
            echo "Polling failed $MAX_RETRIES consecutive times. Please verify the pipeline url:"
            echo "    ${PROJ_URL}/pipelines/$PIPELINE"
            echo "check your api token, or check if there are connection issues."
            RESPONSE='failed'
        fi
    else
        # reset RETRIES_LEFT if the status call succeeded (fail only on consecutive failures)
        RETRIES_LEFT=$MAX_RETRIES
    fi

    echo -n '.'
    sleep $SLEEP
done

echo
echo Done

[ $( pstatus $ID ) = 'success' ]
