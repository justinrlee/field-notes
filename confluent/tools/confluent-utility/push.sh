#!/bin/bash

# Requires that user be logged as relevant docker user

# Will push
# * justinrlee/confluent-utility:<timestamp>-amd64
# * justinrlee/confluent-utility:<timestamp>-arm64

# Will also combine into a multiarch manifest, with two tags:
# * justinrlee/confluent-utility:<timestamp>
# * justinrlee/confluent-utility:latest

export DATE=$(cat tag)

time docker push ${IMAGE}:${DATE}-amd64
time docker push ${IMAGE}:${DATE}-arm64v8

time docker manifest rm docker.io/${IMAGE}:${DATE}-multiarch
time docker manifest create \
    ${IMAGE}:${DATE}-multiarch \
    --amend ${IMAGE}:${DATE}-amd64 \
    --amend ${IMAGE}:${DATE}-arm64v8

time docker manifest push ${IMAGE}:${DATE}-multiarch

time docker manifest rm docker.io/${IMAGE}:latest
time docker manifest create \
    ${IMAGE}:latest \
    --amend ${IMAGE}:${DATE}-amd64 \
    --amend ${IMAGE}:${DATE}-arm64v8

time docker manifest push ${IMAGE}:latest