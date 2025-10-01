Based on this:

```
mvn archetype:generate                               \
      -DarchetypeGroupId=org.apache.flink              \
      -DarchetypeArtifactId=flink-quickstart-java      \
      -DarchetypeVersion=1.9.3
```

build
```bash
mvn package
```

grab the file (`./target/kafka-helloworld-1.0-SNAPSHOT.jar`), put it on the dataproc master

run (on dataproc, with yarn feature enabled)
```bash
flink run -m yarn-cluster kafka-helloworld-1.0-SNAPSHOT.jar
```

produce to the topic

look at the job logs:

```
2> this is a test test
2> this is another test test
2> a
2> test
2> y
2> good bye
2> this is a test
2> another one
1> another one
1> x
1> test
1> hello world
1> another one
1> another one
1> hi hi hi
1> z
```