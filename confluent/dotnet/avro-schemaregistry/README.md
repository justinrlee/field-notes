Hello world app for dotnet w/ Schema Registry w/ authentication

Based on https://github.com/confluentinc/confluent-kafka-dotnet/tree/master/examples/AvroBlogExamples

Written to be run on Windows.  I don't know Windows that well.

# Steps:

## Install prereqs

Install both .NET Core 3.x and 5.x (or at least 3.x; you don't necessarily need 5.x but you'll need to modify the csproj files)

## Install the avrogen tool

Note the use of the Apache version of this, instead of the Confluent one; we've deprecated the Confluent one in favor of Apache

```bash
dotnet tool install -g Apache.Avro.Tools
```

(Will install globally)

## Use avrogen on LogMessage.asvc to generate a set of .cs classes for the "LogMessage" message class (requires .NET 3.x)

```bash
avrogen -s .\LogMessage.asvc .
```

Should result in two .cs files:
* `.\MessageTypes\LogLevel.cs`
* `.\MessageTypes\LogMessages.cs`

## Get a PEM file with the root certificate used by your Confluent cluster (should be a plain text file that starts with ---- BEGIN CERTIFICATE----)

If you're using Confluent Cloud, this may work (`ISRG Root X1`, filename ca.pem)

```pem
-----BEGIN CERTIFICATE-----
MIIFazCCA1OgAwIBAgIRAIIQz7DSQONZRGPgu2OCiwAwDQYJKoZIhvcNAQELBQAw
TzELMAkGA1UEBhMCVVMxKTAnBgNVBAoTIEludGVybmV0IFNlY3VyaXR5IFJlc2Vh
cmNoIEdyb3VwMRUwEwYDVQQDEwxJU1JHIFJvb3QgWDEwHhcNMTUwNjA0MTEwNDM4
WhcNMzUwNjA0MTEwNDM4WjBPMQswCQYDVQQGEwJVUzEpMCcGA1UEChMgSW50ZXJu
ZXQgU2VjdXJpdHkgUmVzZWFyY2ggR3JvdXAxFTATBgNVBAMTDElTUkcgUm9vdCBY
MTCCAiIwDQYJKoZIhvcNAQEBBQADggIPADCCAgoCggIBAK3oJHP0FDfzm54rVygc
h77ct984kIxuPOZXoHj3dcKi/vVqbvYATyjb3miGbESTtrFj/RQSa78f0uoxmyF+
0TM8ukj13Xnfs7j/EvEhmkvBioZxaUpmZmyPfjxwv60pIgbz5MDmgK7iS4+3mX6U
A5/TR5d8mUgjU+g4rk8Kb4Mu0UlXjIB0ttov0DiNewNwIRt18jA8+o+u3dpjq+sW
T8KOEUt+zwvo/7V3LvSye0rgTBIlDHCNAymg4VMk7BPZ7hm/ELNKjD+Jo2FR3qyH
B5T0Y3HsLuJvW5iB4YlcNHlsdu87kGJ55tukmi8mxdAQ4Q7e2RCOFvu396j3x+UC
B5iPNgiV5+I3lg02dZ77DnKxHZu8A/lJBdiB3QW0KtZB6awBdpUKD9jf1b0SHzUv
KBds0pjBqAlkd25HN7rOrFleaJ1/ctaJxQZBKT5ZPt0m9STJEadao0xAH0ahmbWn
OlFuhjuefXKnEgV4We0+UXgVCwOPjdAvBbI+e0ocS3MFEvzG6uBQE3xDk3SzynTn
jh8BCNAw1FtxNrQHusEwMFxIt4I7mKZ9YIqioymCzLq9gwQbooMDQaHWBfEbwrbw
qHyGO0aoSCqI3Haadr8faqU9GY/rOPNk3sgrDQoo//fb4hVC1CLQJ13hef4Y53CI
rU7m2Ys6xt0nUW7/vGT1M0NPAgMBAAGjQjBAMA4GA1UdDwEB/wQEAwIBBjAPBgNV
HRMBAf8EBTADAQH/MB0GA1UdDgQWBBR5tFnme7bl5AFzgAiIyBpY9umbbjANBgkq
hkiG9w0BAQsFAAOCAgEAVR9YqbyyqFDQDLHYGmkgJykIrGF1XIpu+ILlaS/V9lZL
ubhzEFnTIZd+50xx+7LSYK05qAvqFyFWhfFQDlnrzuBZ6brJFe+GnY+EgPbk6ZGQ
3BebYhtF8GaV0nxvwuo77x/Py9auJ/GpsMiu/X1+mvoiBOv/2X/qkSsisRcOj/KK
NFtY2PwByVS5uCbMiogziUwthDyC3+6WVwW6LLv3xLfHTjuCvjHIInNzktHCgKQ5
ORAzI4JMPJ+GslWYHb4phowim57iaztXOoJwTdwJx4nLCgdNbOhdjsnvzqvHu7Ur
TkXWStAmzOVyyghqpZXjFaH3pO3JLF+l+/+sKAIuvtd7u+Nxe5AW0wdeRlN8NwdC
jNPElpzVmbUq4JUagEiuTDkHzsxHpFKVK7q4+63SM1N95R1NbdWhscdCb+ZAJzVc
oyi3B43njTOQ5yOf+1CceWxG1bQVs5ZufpsMljq4Ui0/1lvh+wjChP4kqKOJ2qxq
4RgqsahDYVvTH9w7jXbyLeiNdd8XM2w9U/t7y0Ff/9yi0GE44Za4rF2LN9d11TPA
mRGunUHBcnWEvgJBQl9nJEiU0Zsnvgc/ubhPgXRR4Xq37Z0j4r7g1SgEEzwxA57d
emyPxgcYxn/eR44/KJ4EBs+lVDR3veyJm+kXQ99b21/+jh5Xos1AnX5iItreGCc=
-----END CERTIFICATE-----
```

## Update kafka.properties and schemaregistry.properties with endpoints and credentials for Kafka and Schema Registry

## Build the two projects
    
```bash
dotnet build producer.csproj

dotnet build consumer.csproj
```

## Create the kafka topic

Go into the Confluent UI (Confluent Control Center or Confluent Cloud) and create a kafka topic that you have permissions for

## Run the producer

Each time you run the program, it'll produce one message.  Usage looks like this:

```bash
dotnet run --project producer.csproj <full-path-to-kafka.properties> <full-path-to-schema-registry.properties> <topic-name>
```

For example:

```
dotnet run --project producer.csproj C:\Users\helloworld\dotnet-avro-schemaregistry\kafka.properties C:\Users\helloworld\dotnet-avro-schemaregistry\schemaregistry.properties justin-demo
```

Produce a couple of messages, try modifying the code to produce multiple messages, etc.

## Explore messages in the Confluent UI

Explore schemas, look at messages, see if you can see how different topics work

## Run the consumer (dotnet run --project consumer.csproj c:\\path\to\kafka.properties) so you can see data on the consumption side

Each time you run the program, it'll read all messages from the topic, from the beginning.  Usage looks like this:

```bash
dotnet run --project consumer.csproj <full-path-to-kafka.properties> <full-path-to-schema-registry.properties> <topic-name>
```

For example:

```
dotnet run --project consumer.csproj C:\Users\helloworld\dotnet-avro-schemaregistry\kafka.properties C:\Users\helloworld\dotnet-avro-schemaregistry\schemaregistry.properties justin-demo
```

See if you can figure out how to:
* Consume only messages that come in while the program is running
* Consume only from the last time the program was run