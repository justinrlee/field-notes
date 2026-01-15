# Project initialization

```bash
uv init . --python 3.11

uv add confluent_kafka
uv add "confluent_kafka[avro,schemaregistry]"

uv tree
```


# Run

```bash
uv run producer.py
```
