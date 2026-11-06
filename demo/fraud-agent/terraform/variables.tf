# ---------------------------------------------------------------------------
# The ONLY four values a user must provide (in terraform.tfvars).
# Everything else (region, model, resource names, sizes) is fixed in locals
# below so running this demo requires no other decisions.
# ---------------------------------------------------------------------------

variable "confluent_cloud_api_key" {
  description = "Confluent Cloud API key (Cloud resource management)."
  type        = string
  sensitive   = true
}

variable "confluent_cloud_api_secret" {
  description = "Confluent Cloud API secret."
  type        = string
  sensitive   = true
}

variable "aws_access_key_id" {
  description = "AWS IAM user access key ID with Amazon Bedrock invoke permission."
  type        = string
  sensitive   = true
}

variable "aws_secret_access_key" {
  description = "AWS IAM user secret access key."
  type        = string
  sensitive   = true
}

variable "identifier" {
  description = "Environment identifier"
  type        = string
}

variable "region" {
  description = "AWS Region"
  type        = string
}

variable "bedrock_model_id" {
  description = "Bedrock Model ID"
  type        = string
  default     = "global.anthropic.claude-sonnet-4-5-20250929-v1:0"
}