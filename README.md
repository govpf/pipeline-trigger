# Pipeline-trigger

Pipeline-trigger allows you to trigger and wait for the results of another GitLab pipeline.

## Background

GitLab's pipelines are a great tool to set up a CI process within projects. There's a relatively straight-forward way of triggering another project's pipeline from a parent project.

However, this process is a fire-and-forget one: you will trigger the project with an HTTP request to the other project but this call will return upon registering the trigger on the other end and not wait for that pipeline to finish, let alone tell you how it went.

For instance, imagine you want to set up the following pipeline with a parent project triggering builds in other projects - A and B - and waiting for their results:

![Screen_Shot_2017-11-25_at_10.37.00](/uploads/2fef9bc62bda643f32129e55b128bfe4/Screen_Shot_2017-11-25_at_10.37.00.png)

This is impossible to configure out of the box with GitLab.

However, thanks to the GitLab API and docker, it's actually quite simple to set up a reusable docker image which can be used as a building block.

## How to set it up

Here's what the `.gitlab-ci.yml` looks like for the above pipeline:

```
image: busybox:latest

variables:
  # PERSONAL_ACCESS_TOKEN set via secret variables
  API_TOKEN: $PERSONAL_ACCESS_TOKEN
  PTRIGGER: "registry.gitlab.com/finestructure/pipeline-trigger"
  PROJ_A_ID: 4624510
  PROJ_A_PIPELINE_TOKEN: "bf2c2803db650b8cc473dd1c790c97"
  PROJ_B_ID: 4624517
  PROJ_B_PIPELINE_TOKEN: "56f4e2d904958e064c7436d932f490"
  TARGET_BRANCH: master

stages:
  - deploy_dev
  - test_dev
  - deploy_qa

deploy dev:
  stage: deploy_dev
  script:
    - echo "deploying to dev"

test proj a:
  stage: test_dev
  image: $PTRIGGER
  script: 
    - /trigger -a $API_TOKEN -p $PROJ_A_PIPELINE_TOKEN -t $TARGET_BRANCH $PROJ_A_ID

test proj b:
  stage: test_dev
  image: $PTRIGGER
  script: 
    - /trigger -a $API_TOKEN -p $PROJ_B_PIPELINE_TOKEN -t $TARGET_BRANCH $PROJ_B_ID

deploy_qa:
  stage: deploy_qa
  script:
    - echo "deploying to qa"

```

Apart from configuring the typical variables needed, the essential part is to set up a trigger job for each dependency:

```
test proj a:
  stage: test_dev
  image: $PTRIGGER
  script: 
    - /trigger -a $API_TOKEN -p $PROJ_A_PIPELINE_TOKEN -t $TARGET_BRANCH $PROJ_A_ID
```

This runs the `trigger` command which is part of the `pipeline-trigger` image with the specified parameters. This script will trigger the pipeline in the given project and then poll the pipeline status for its result. The exit code will be `0` in case of `success` and that way integate in your parent project's pipeline like any other build job - just that it's run on another project's pipeline.

## Get in touch

- http://finestructure.co
- https://twitter.com/_sa_s
