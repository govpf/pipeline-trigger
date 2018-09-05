#!/bin/sh

API_TOKEN=$1
PROJ_ID=$2
JSON_FILE=$3

curl -s -X POST -H "PRIVATE-TOKEN: $API_TOKEN" -H "Content-Type: application/json" --data "@$JSON_FILE" "https://gitlab.com/api/v4/projects/$PROJ_ID/repository/commits"
