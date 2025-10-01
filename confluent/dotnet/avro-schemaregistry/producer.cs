using Confluent.Kafka;
using Confluent.SchemaRegistry;
using Confluent.SchemaRegistry.Serdes;
using System;
using System.Collections.Generic;
using Microsoft.Extensions.Configuration;
using System.IO;
using System.Threading;
using System.Threading.Tasks;

class Producer {

    static async Task Main(string[] args)
    {

        if (args.Length != 3) {
            Console.WriteLine("Usage: dotnet run --project producer.csproj c:\\path\\to\\kafka.properties c:\\path\\to\\schemaregistry.properties <topicname>");
            Environment.Exit(1);
        }

        IConfiguration kafkaConfig = new ConfigurationBuilder()
            .AddIniFile(args[0])
            .Build();
            
        IConfiguration srConfig = new ConfigurationBuilder()
            .AddIniFile(args[1])
            .Build();

        string topic = args[2];

        using (var schemaRegistry = new CachedSchemaRegistryClient(srConfig.AsEnumerable()))

        using (var producer = 
            new ProducerBuilder<string, MessageTypes.LogMessage>(kafkaConfig.AsEnumerable())
                .SetValueSerializer(new AvroSerializer<MessageTypes.LogMessage>(schemaRegistry))
                .Build()
            )
        {
                await producer.ProduceAsync(topic,
                    new Message<string, MessageTypes.LogMessage>
                    {
                        Value = new MessageTypes.LogMessage
                        {
                            IP = "192.168.0.1",
                            Message = "test message from device " + Guid.NewGuid().ToString(),
                            Severity = MessageTypes.LogLevel.Info,
                            Tags = new Dictionary<string, string> { { "location", "CA" } }
                        }
                    });

                producer.Flush(TimeSpan.FromSeconds(30));
        }

        Console.WriteLine("Successfully produced message to " + topic);
    }
}