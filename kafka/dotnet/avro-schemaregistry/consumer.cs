using Confluent.Kafka;
using Confluent.Kafka.SyncOverAsync;
using Confluent.SchemaRegistry;
using Confluent.SchemaRegistry.Serdes;
using System;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Configuration;

class Consumer {

    static void Main(string[] args)
    {
        if (args.Length != 3) {
            Console.WriteLine("Usage: dotnet run --project consumer.csproj c:\\path\\to\\kafka.properties c:\\path\\to\\schemaregistry.properties <topicname>");
            Environment.Exit(1);
        }

        IConfiguration kafkaConfig = new ConfigurationBuilder()
            .AddIniFile(args[0])
            .Build();
            
        IConfiguration srConfig = new ConfigurationBuilder()
            .AddIniFile(args[1])
            .Build();
            
        string topic = args[2];

        kafkaConfig["group.id"] = Guid.NewGuid().ToString();
        kafkaConfig["auto.offset.reset"] = "earliest";


        CancellationTokenSource cts = new CancellationTokenSource();
        Console.CancelKeyPress += (_, e) => {
            e.Cancel = true; // prevent the process from terminating.
            cts.Cancel();
        };

        using (var schemaRegistry = new CachedSchemaRegistryClient(srConfig.AsEnumerable()))

        using (var consumer = 
            new ConsumerBuilder<String, MessageTypes.LogMessage>(kafkaConfig.AsEnumerable())
                .SetValueDeserializer(new AvroDeserializer<MessageTypes.LogMessage>(schemaRegistry).AsSyncOverAsync())
                .Build())
        {
            consumer.Subscribe(topic);

            try {
                while (true) {
                    var consumeResult = consumer.Consume(cts.Token);

                    Console.WriteLine(
                        consumeResult.Message.Timestamp.UtcDateTime.ToString("yyyy-MM-dd HH:mm:ss")
                        + $": [{consumeResult.Message.Value.Severity}] {consumeResult.Message.Value.Message}");

                }
            }
            catch (OperationCanceledException) {
                // Ctrl-C was pressed.
            }
            finally{
                consumer.Close();
            }
        }
    }
}