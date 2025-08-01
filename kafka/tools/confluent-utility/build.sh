export DATE=$(date +%Y-%m-%d-%H-%M-%S)
export IMAGE=justinrlee/confluent-utility

time docker build -t ${IMAGE}:${DATE}-amd64 --platform linux/amd64 --build-arg ARCH=amd64 -f Dockerfile.amd64 .
time docker build -t ${IMAGE}:${DATE}-arm64v8 --platform linux/arm64/v8 --build-arg ARCH=arm64/v8 -f Dockerfile.arm64v8 .

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