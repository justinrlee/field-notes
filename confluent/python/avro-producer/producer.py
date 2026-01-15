
import argparse
import configparser
import os
import json
import traceback
from uuid import uuid4

# from six.moves import input

from confluent_kafka import Producer
from confluent_kafka.admin import AdminClient, NewTopic
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer
from confluent_kafka.serialization import MessageField, SerializationContext, StringSerializer

def dict_to_dict(input, ctx):
    """
    Placeholder function to convert a dictionary to a dictionary. There's gotta be a better way to do this.
    """
    return input

def event_id_to_dict(event_id, ctx):
    """
    Returns a dict representation of a EventId instance for serialization.
    """
    return dict(eventId=event_id)

def transform_flink_json_to_avro(data):
    """
    Transform Flink-style JSON (with type wrappers) to standard Avro-compatible format.
    
    Flink JSON format has multiple wrapping levels:
    1. Arrays: {"array": [...]} → [...]
    2. Records: {"org.apache.flink.avro.generated.record.xxx": {...}} → {...}
    3. Primitives: {"string": "value"} → "value", {"int": 123} → 123
    """
    if isinstance(data, dict):
        # Check if this is an array wrapper FIRST
        if len(data) == 1 and "array" in data:
            # Unwrap array: {"array": [...]} → [...]
            return transform_flink_json_to_avro(data["array"])
        
        # Check if this is a type-wrapped primitive value
        type_keys = {"string", "int", "long", "boolean", "float", "double", "null"}
        if len(data) == 1 and any(key in type_keys for key in data.keys()):
            # This is a type-wrapped value, unwrap it
            value = list(data.values())[0]
            if value is None:
                # For null values wrapped as {"string": null}, convert to empty string
                # since most string fields in Avro are non-nullable
                if "string" in data:
                    return ""  # Convert null strings to empty string
                return None
            # Recursively transform the unwrapped value
            return transform_flink_json_to_avro(value)
        
        # Check if this is a record type wrapper (has a long qualified name as key)
        if len(data) == 1:
            key = list(data.keys())[0]
            # If the key looks like a fully qualified record type name
            if "." in key and "record" in key.lower():
                # Unwrap the record: {"org.apache.flink...": {...}} → {...}
                return transform_flink_json_to_avro(data[key])
        
        # Regular dict, transform each value
        return {k: transform_flink_json_to_avro(v) for k, v in data.items()}
    elif isinstance(data, list):
        # Transform each item in the list
        return [transform_flink_json_to_avro(item) for item in data]
    else:
        # Primitive value, return as-is
        return data

def delivery_report(err, msg):
    """
    Reports the failure or success of a message delivery.

    Args:
        err (KafkaError): The error that occurred, or None on success.

        msg (Message): The message that was produced or failed.

    Note:
        In the delivery report callback the Message.key() and Message.value()
        will be the binary format as encoded by any configured Serializers and
        not the same object that was passed to produce().
        If you wish to pass the original object(s) for key and value to delivery
        report callback we recommend a bound callback or lambda where you pass
        the objects along.
    """

    if err is not None:
        print("Delivery failed for User record {}: {}".format(msg.key(), err))
        return
    print(
        'User record {} successfully produced to {} [{}] at offset {}'.format(
            msg.key(), msg.topic(), msg.partition(), msg.offset()
        )
    )


def get_message_dict(input_file):
    with open(input_file, 'r') as f:
        input = f.read()
        i_d = json.loads(input)
        print("Input")
        print(i_d)
        transformed = transform_flink_json_to_avro(i_d)
        print("Transformed")
        print(transformed)
        return transformed

def create_topic_if_not_exists(kafka_client_conf, topic):
    admin_client = AdminClient(kafka_client_conf)
    try:
        topic_metadata = admin_client.list_topics()
        print(f"Topic metadata: {topic_metadata}")
        if topic not in topic_metadata.topics:
            ct_futures = admin_client.create_topics([NewTopic(topic=topic, num_partitions=1, replication_factor=3)])
            for topic, f in ct_futures.items():
                try:
                    f.result()  # The result itself is None
                    print("Topic {} created".format(topic))
                except Exception as e:
                    print("Failed to create topic {}: {}".format(topic, e))
            
        return True
    except Exception as e:
        print(f"Error creating topic {topic}: {e}")
        return False

def load_config(config_file):
    """
    Load configuration from an INI file.
    
    Args:
        config_file (str): Path to the configuration file.
        
    Returns:
        configparser.ConfigParser: Parsed configuration object.
    """
    config = configparser.ConfigParser()
    if os.path.exists(config_file):
        config.read(config_file)
    else:
        raise FileNotFoundError(f"Config file not found: {config_file}")
    return config

def main(args):
    if args.config_file:
        config = load_config(args.config_file)
    else:
        sys.exit("Error: config file is required")

    print(dict(config))
    
    kafka_client_conf = dict(config['kafka_client'])
    schema_registry_conf = dict(config['schema_registry'])

    if args.topic:
        topic = args.topic
    else:
        topic = config['general']['topic']

    if not create_topic_if_not_exists(kafka_client_conf, topic):
        print(f"Error creating topic {topic}")
        exit(1)


    with open(config['general']['value_schema'], 'r') as f:
        value_schema_str = f.read()

    with open(config['general']['key_schema'], 'r') as f:
        key_schema_str = f.read()

    with SchemaRegistryClient(schema_registry_conf) as schema_registry_client:
        key_serializer = AvroSerializer(schema_registry_client, key_schema_str, event_id_to_dict)
        # value_serializer = AvroSerializer(schema_registry_client, value_schema_str, user_to_dict)
        message_serializer = AvroSerializer(schema_registry_client, value_schema_str, dict_to_dict)

        # Producer does not support context manager protocol, so create it directly
        producer = Producer(kafka_client_conf)
        try:
            print("Producing user records to topic {}. ^C to exit.".format(topic))

            directory = config['general']['sample_data_directory']

            for f in os.listdir(directory):
                input_file = os.path.join(directory, f)
                print(f"Processing file: {input_file}")
                try:
                    message_dict = get_message_dict(input_file)
                    event_id = str(uuid4())
                    print(f"Producing record with eventId: {event_id}")
                    producer.produce(
                        topic=topic,
                        key=key_serializer(event_id, SerializationContext(topic, MessageField.KEY)),
                        value=message_serializer(message_dict, SerializationContext(topic, MessageField.VALUE)),
                        on_delivery=delivery_report,
                    )
                except KeyboardInterrupt:
                    break
                except ValueError as e:
                    print(f"ValueError: {e}")
                    print(f"Error type: {type(e).__name__}")
                    traceback.print_exc()
                    print("Invalid input, discarding record...")
                    continue
            # while True:
            # for i in range(10):
            #     # Serve on_delivery callbacks from previous calls to produce()
            #     producer.poll(0.0)
            #     try:
            #         input_file = f"input/vik/{i}.json"
            #         message_dict = get_message_dict(input_file)
            #         event_id = str(uuid4())
            #         print(f"Producing record with eventId: {event_id}")
            #         producer.produce(
            #             topic=topic,
            #             key=key_serializer(event_id, SerializationContext(topic, MessageField.KEY)),
            #             value=message_serializer(message_dict, SerializationContext(topic, MessageField.VALUE)),
            #             on_delivery=delivery_report,
            #         )
            #     except KeyboardInterrupt:
            #         break
            #     except ValueError as e:
            #         print(f"ValueError: {e}")
            #         print(f"Error type: {type(e).__name__}")
            #         traceback.print_exc()
            #         print("Invalid input, discarding record...")
            #         continue
        finally:
            # Flush any remaining messages before exiting
            producer.flush()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AvroSerializer example")
    parser.add_argument(
        '-c', '--config-file', dest="config_file", default=None,
        help="Path to configuration file (INI format)"
    )
    parser.add_argument(
        '-t', dest="topic", default=None,
        help="Topic name. Overrides config file value."
    )
    parser.add_argument(
        '-p', dest="specific", default=None,
        help="Avro specific record. Overrides config file value."
    )
    args = parser.parse_args()
    main(args)
