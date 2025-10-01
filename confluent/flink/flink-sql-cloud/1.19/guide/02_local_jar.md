# Part 2: Build a JAR to be run against the Kafka cluster

Create a new directory.

Determine a "group" to be used for your job. I like to use `io.justinrlee.something.something`; for this, I used `io.justinrlee.kafka.flink`
Determine an application name. For this demo, I used `flink-cloud-sql`

Run this in the directory to generate the directory structure using maven archetype

Note that this will create a new directory in your directory

```
mvn archetype:generate \
  -DgroupId=io.justinrlee.kafka.flink \
  -DartifactId=flink-cloud-sql \
  -DarchetypeArtifactId=maven-archetype-quickstart \
  -DarchetypeVersion=1.5 \
  -DinteractiveMode=false
```

You'll end up with a directory structure that looks roughly like this

```
flink-cloud-sql/
├── pom.xml
├── .mvn/
│   ├── jvm.config
│   └── maven.config
└── src/
    ├── main/java/.../App.java
    └── test/java/.../AppTest.java
```

... I don't build tests for this, so I just kinda delete that.

Then update your POM to look roughly like the one in this repo, update App.java, and create a separate classes for parsing and handling configuration and for generating the connector config
TODO: Explain the POM

Then... write the application code.

TODO: write simplified application code, with hardcoded credentials
TODO: explain how to read credentials from a file
TODO: expand application code to include lifecycle hooks
TODO: explain splitting application code into

Build the package using maven:

```
mvn clean package
```

Will generate a JAR

You can run that JAR with this:

```bash
flink run <path-to-JAR>
```