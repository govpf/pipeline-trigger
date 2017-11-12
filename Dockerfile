FROM alpine:3.6

RUN apk add --no-cache \
    curl \
    jq \
    && rm -rf /var/cache/apk/*

COPY trigger /
CMD [ "/trigger" ]
