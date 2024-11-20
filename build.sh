#!/bin/sh
docker build -t ks-harbor1.kentem.net/update-checker/main:"${1}" -f ./Dockerfile . --no-cache && \
docker push ks-harbor1.kentem.net/update-checker/main:"${1}"