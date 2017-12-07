FROM alpine:3.6

RUN apk add --no-cache \
    bash \
    curl \
    jq \
    && rm -rf /var/cache/apk/*

COPY trigger /usr/bin
CMD [ "trigger" ]
