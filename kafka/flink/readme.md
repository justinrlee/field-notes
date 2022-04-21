build
```bash
mvn package
```

grab the file (`./target/kafka-helloworld-1.0-SNAPSHOT.jar`), put it on the dataproc master

run (on dataproc, with yarn feature enabled)
```bash
flink run -m yarn-cluster kafka-helloworld-1.0-SNAPSHOT.jar
```