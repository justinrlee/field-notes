# Justin's field notes
Miscellaneous samples.

Structure:
* confluent
    * assets - various assets for personal automation (pre-generated testing CA certificate, SSL generation configs, etc.)
    * flink - small scripts to start up small Flink clusters with Confluent
    * mini - small scripts to start up small CP clusters (out of date)
    * notes - miscellaneous text notes
* kafka - things that interact with Kafka, in various languages and frameworks
* misc
    * mtls-validator - used to verify a given set of client certificates work against a given CA certificate (doesn't currently work)
    * terraform - quick introduction to Terraform (using AWS)
    * tools - cleanup scripts (most of which have been moved to `github.com/ifnesi/aws-cleanup`)