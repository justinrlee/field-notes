#!/bin/bash

# Will build (but not push):
# * justinrlee/confluent-utility:<timestamp>-amd64
# * justinrlee/confluent-utility:<timestamp>-arm64

export TAG=${TAG:-$(date +%Y-%m-%d-%H-%M-%S)}
export IMAGE=justinrlee/confluent-utility

echo $TAG > latest

time docker build -t ${IMAGE}:${TAG}-amd64 --platform linux/amd64 --build-arg ARCH=amd64 -f Dockerfile.amd64 .
time docker build -t ${IMAGE}:${TAG}-arm64v8 --platform linux/arm64/v8 --build-arg ARCH=arm64/v8 -f Dockerfile.arm64v8 .
