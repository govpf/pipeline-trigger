#!/bin/sh
set -e

# vars
# PRIVATE_TOKEN
# PIPELINE_TOKEN
# TARGET_BRANCH
# PROJECT_ID

usage() { echo "Usage: $0 -a <api token> -p <pipeline token> <project id>" 1>&2; exit 1; }

while getopts ":a:p:t:" o; do
    case "${o}" in
        a)
            API_TOKEN=${OPTARG}
            ;;
        p)
            PIPELINE_TOKEN=${OPTARG}
            ;;
        t)
            TARGET_BRANCH=${OPTARG}
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


PROJ_URL=https://gitlab.com/api/v4/projects/${PROJECT_ID}

function pstatus {
    PIPELINE=$1
    curl -s -X GET -H "PRIVATE-TOKEN: $PRIVATE_TOKEN" ${PROJ_URL}/pipelines/$PIPELINE | jq -r '.status'
}

# pipeline states: running, pending, success, failed, canceled, skipped

echo "Triggering pipeline ..."

ID=$(curl -s -X POST -F token=$PIPELINE_TOKEN -F "ref=$TARGET_BRANCH" ${PROJ_URL}/trigger/pipeline | jq -r '.id')

echo Pipeline id: $ID

echo "Waiting for pipeline to finish ..."

until [[ \
  $( pstatus $ID ) = 'failed' \
  || $( pstatus $ID ) = 'warning' \
  || $( pstatus $ID ) = 'manual' \
  || $( pstatus $ID ) = 'cancelled' \
  || $( pstatus $ID ) = 'canceled' \  # docs indicate this spelling might exist
  || $( pstatus $ID ) = 'success' \
  || $( pstatus $ID ) = 'skipped' \
]]; do
    echo -n '.'
    sleep 1
done

echo
echo Done

[ $( pstatus $ID ) = 'success' ]
