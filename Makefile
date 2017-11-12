.PHONY: build run kill enter tag push

VERSION=0.2
NAME=pipeline-trigger
REGISTRY=registry.gitlab.com/finestructure
IMG=$(REGISTRY)/$(NAME):$(VERSION)

build:
	docker build --rm -t $(IMG) --build-arg VERSION=$(VERSION) .

enter:
	docker run --rm -it --entrypoint sh $(IMG)

push:
	docker push $(IMG)
