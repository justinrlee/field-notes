export DATE=$(date +%Y-%m-%d)

time docker build -t justinrlee/confluent-utility:${DATE}-amd64 --platform linux/amd64 --build-arg ARCH=amd64 -f Dockerfile.amd64 .
time docker build -t justinrlee/confluent-utility:${DATE}-arm64v8 --platform linux/arm64/v8 --build-arg ARCH=arm64/v8 -f Dockerfile.arm64v8 .

time docker push justinrlee/confluent-utility:${DATE}-amd64
time docker push justinrlee/confluent-utility:${DATE}-arm64v8

time docker manifest rm docker.io/justinrlee/confluent-utility:${DATE}-multiarch
time docker manifest create \
    justinrlee/confluent-utility:${DATE}-multiarch \
    --amend justinrlee/confluent-utility:${DATE}-amd64 \
    --amend justinrlee/confluent-utility:${DATE}-arm64v8

time docker manifest push justinrlee/confluent-utility:${DATE}-multiarch

time docker manifest rm docker.io/justinrlee/confluent-utility:latest
time docker manifest create \
    justinrlee/confluent-utility:latest \
    --amend justinrlee/confluent-utility:${DATE}-amd64 \
    --amend justinrlee/confluent-utility:${DATE}-arm64v8

time docker manifest push justinrlee/confluent-utility:latest