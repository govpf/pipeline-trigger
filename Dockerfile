FROM alpine:3.6

ARG VERSION

RUN apk add --no-cache \
    curl \
    jq \
    && rm -rf /var/cache/apk/*

COPY trigger /
CMD [ "/trigger" ]
