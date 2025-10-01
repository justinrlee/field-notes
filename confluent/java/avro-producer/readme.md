Very simple Java app that produces to Confluent Cloud using avro.

THIS IS TERRIBLE CODE DO NOT USE IT

Used to generate load with:
* String (UUID) key
* Avro value

Uses gradle

```bash
sudo apt-get update
sudo apt-get install openjdk-11-jdk-headless unzip -y

curl -LO https://services.gradle.org/distributions/gradle-8.0.2-bin.zip

unzip gradle-8.0.2-bin.zip
sudo mv gradle-8.0.2 /opt/gradle
export PATH=${PATH}:/opt/gradle/bin
echo 'export PATH=${PATH}:/opt/gradle/bin' >> ~/.bashrc
```

Need these two files (in whatever directory):
* `build.gradle`
* `src/main/java/examples/AvroProducer.java`
* `client.properties`

```bash
gradle shadowJar

jar -tvf build/libs/kafka-avro-producer-0.0.1.jar

java -cp build/libs/kafka-avro-producer-0.0.1.jar examples.AvroProducer client.properties
```

