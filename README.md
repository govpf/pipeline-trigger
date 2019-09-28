[![pipeline status](https://gitlab.com/finestructure/pipeline-trigger/badges/master/pipeline.svg)](https://gitlab.com/finestructure/pipeline-trigger/commits/master)
[![coverage report](https://gitlab.com/finestructure/pipeline-trigger/badges/master/coverage.svg)](https://finestructure.gitlab.io/pipeline-trigger/)
[![Twitter](https://img.shields.io/badge/twitter-@__sa__s-blue.svg?logo=twitter)](https://twitter.com/_sa_s)

# Pipeline-trigger

Pipeline-trigger allows you to trigger and wait for the results of another GitLab pipeline.

## Background

GitLab's pipelines are a great tool to set up a CI process within projects. There's a relatively straight-forward way of triggering another project's pipeline from a parent project.

However, this process is "fire and forget": you will trigger the project with an HTTP request but this call will return upon registering the trigger on the other end and not wait for that pipeline to finish, let alone tell you how it went.

For instance, imagine you want to set up the following pipeline with a parent project triggering builds in other projects - A and B - and waiting for their results:

![Screen_Shot_2017-11-30_at_08.21.42](/uploads/c906618303dcf0124185b97f56d3fe97/Screen_Shot_2017-11-30_at_08.21.42.png)

This is impossible to configure out of the box with GitLab.

However, thanks to the GitLab API and docker, it's actually quite simple to set up a reusable docker image which can be used as a building block.

## How to set it up

Here's what the `.gitlab-ci.yml` looks like for the above pipeline (straight from on older version of this project's [gitlab-ci.yml](https://gitlab.com/finestructure/pipeline-trigger/blob/a052c9f47d7f0fdafb9641ccb9ef831b8e1ad49a/.gitlab-ci.yml)):

```
variables:
  IMAGE: $CI_REGISTRY_IMAGE:$CI_COMMIT_SHA
  # set via secret variables
  API_TOKEN: $PERSONAL_ACCESS_TOKEN
  PROJ_A_ID: $PROJ_A_ID
  PROJ_A_PIPELINE_TOKEN: "$PROJ_A_PIPELINE_TOKEN"
  PROJ_B_ID: $PROJ_B_ID
  PROJ_B_PIPELINE_TOKEN: $PROJ_B_PIPELINE_TOKEN
  TARGET_BRANCH: master

stages:
  - build
  - test
  - release

build-sha:
  # details skipped

test proj a:
  stage: test
  image: $IMAGE
  script: 
    - trigger -a "$API_TOKEN" -p "$PROJ_A_PIPELINE_TOKEN" -t $TARGET_BRANCH $PROJ_A_ID

test proj b:
  stage: test
  image: $IMAGE
  script: 
    - trigger -a "$API_TOKEN" -p "$PROJ_B_PIPELINE_TOKEN" -t $TARGET_BRANCH $PROJ_B_ID

release-tag:
  # details skipped
```

Apart from configuring the typical variables needed, the essential part is to set up a trigger job for each dependency:

```
test proj a:
  stage: test_dev
  image: $PTRIGGER
  script: 
    - trigger -a "$API_TOKEN" -p "$PROJ_A_PIPELINE_TOKEN" -t $TARGET_BRANCH $PROJ_A_ID
```

This runs the `trigger` command which is part of the `pipeline-trigger` image with the specified parameters. This script will trigger the pipeline in the given project and then poll the pipeline status for its result. The exit code will be `0` in case of `success` and that way integate in your parent project's pipeline like any other build job - just that it's run on another project's pipeline.

## Trigger variables

GitLab pipeline triggers accept variables being passed along with the trigger command. In the `curl` version these are constructed as follows:

```
curl ... -F variables[foo]=bar ...
```

`pipeline-trigger` supports this as well via the `-e` switch (`e` for environment variable):

```
trigger ... -e foo=bar
```

## Retries

Sometimes the remote pipeline triggered via pipeline-trigger is complex and/or consists of long-running steps. Because pipeline-trigger by default simply triggers a new remote pipeline (like you would in the pipeline UI), having to re-run a full pipeline just because one stage failed can be annoying.

Starting with pipeline-trigger `2.0.0` it is possible to retry the remote pipeline via the `--retry` (or `-r`) parameter.

Pipeline-trigger will look for the last pipeline that has been run for the given `ref` and inspect its status. If the pipeline was successful, it will create a new pipeline for the `ref`. If it had another status it will retry the pipeline.

The reason `-r` will create a new pipeline successful pipelines is to allow you to configure your pipelines with `-r` in general. If pipeline-trigger did not create new pipelines in case of success you would not be able to trigger further pipelines once a `ref`'s pipeline has succeeded.

Starting with pipeline-trigger `2.1.0` you can also pass in a pipeline id to be retried specifically using the `--pid` parameter. This is useful if you have kept ids around for retries and want to avoid having pipeline-trigger perform lookups. Note that `--pid` implies `-r`.

Other than using the provided pipeline id instead of looking up the latest pipeline for a given reference, pipeline-trigger behaves the same as for retries without the `--pid` parameter. Notably, if the pipeline for the given pipeline id was already in `success` state, a new pipeline will be created.

Starting with pipeline-trigger `2.6.0` you can also pass in a project path instead of project id, e.g. `finestructure/pipeline-trigger`:

```
trigger-downstream:
  #  # polyfill for a GitLab EE feature https://docs.gitlab.com/ee/ci/multi_project_pipelines.html
  #  trigger:
  #    project: finestructure/pt-proj-b
  #    branch: masters
  image: registry.gitlab.com/finestructure/pipeline-trigger:2.6.0
  script:
    - trigger -a "$API_TOKEN" -p "$PROJ_B_PIPELINE_TOKEN" -t master finestructure/pt-proj-b

```


## Self-hosted domains

If you're self-hosting gitlab on your own domain, you will need to configure the urls being used for the API calls. You can use the `-h` and `-u` flags for this as follows:

```
trigger -h gitlab.com -u /api/v4/projects ...
```

where `gitlab.com` and `/api/v4/projects` are also the default values used.

If you're self-hosting gitlab use a SelfSigned SSL certificate you can use the `-v` flag as follows:

```
trigger -h gitlab.com -u /api/v4/projects -v false ...
```

Typically you will only need to override the `host` but `-u` to change the url path is there if you need it.

## Triggering pipelines with manual stages

Pipelines with manual stages are taken as `allow_failure = true` by default in Gitlab. When triggered by pipeline-trigger, these pipelines will be read as passed but will not play their action and therefore the progress of the remote pipeline will stop at the manual stage.

By passing the flag `--on-manual play`, remote pipelines' actions will be played by pipeline-trigger. Please note that this flag will apply to all manual stages.

By passing the flag `--jobs <comma-separated-job-names>` certain manual jobs will play in downstream pipeline, e.g. `--jobs build_1,build_2`. NB: jobs will all start at once.

If the manual pipeline is configured as `allow_failure = false` but you want to treat it as passed when triggering it without playing the action, use the flag `--on-manual pass`.

## Get in touch

- https://finestructure.co
- https://twitter.com/_sa_s
