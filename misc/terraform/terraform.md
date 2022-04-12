
# Prereqs
Assumption: Homebrew installed

Install:
* gimme-aws-creds 
    
    ```bash
    brew install gimme-aws-creds
    ````

* terraform
    
    ```bash
    brew tap hashicorp/tap
    brew install hashicorp/tap/terraform
    brew update
    brew upgrade hashicorp/tap/terraform
    ```

* AWS CLI: https://docs.aws.amazon.com/cli/v1/userguide/install-macos.html (or equivalent)


Set up gimme-aws-creds

`~/.okta_aws_login_config`

```conf
[DEFAULT]
# Set your Okta username here or in the OKTA_USERNAME environment variable.
okta_username = 

# Your prefered MFA method:
#  * push                - Okta Verify or DUO app
#  * token:software:totp - OTP using the Okta Verify App or Google Authenticator
#  * token:hardware      - OTP using hardware like Yubikey
preferred_mfa_type = token:software:totp

# AWS Roles to fetch credentials for. Can be a comma-delimited list of role ARNs
# or 'all' to fetch all credentials available to you (may be slow).
aws_rolename = all

# Required settings
okta_org_url = https://confluent.okta.com
app_url = 
okta_auth_server = 
client_id = 
gimme_creds_server = appurl
aws_appname = 
write_aws_creds = True
cred_profile = default # Change this
resolve_aws_alias = True
include_path = False
remember_device = True
aws_default_duration = 3600
device_token = 
output_format = 
```

```bash
gimme-aws-creds --action-register-device

gimme-aws-creds
```

# Terraform infra

Create a directory to work in (some working directory that isn't completely ephemeral)

`providers.tf`
```tf
provider "aws" {
  region = var.region
}
```

Init

`variables.tf`
```tf
variable "region" {
  default = "us-east-1"
}

variable "owner" {
  default = "justin"
}
```

# VPC

`vpc.tf`

```tf

resource "aws_vpc" "lab" {
  cidr_block = "10.0.0.0/16"

  tags = {
    Name = "${var.owner}-Managed"
  }
}

resource "aws_internet_gateway" "lab" {
  vpc_id = aws_vpc.lab.id

  tags = {
    Name = "${var.owner}-Managed"
  }
}

# Attach route to route table: `aws_vpc.justin.default_route_table_id`
resource "aws_route" "lab_default_route" {
  route_table_id         = aws_vpc.lab.default_route_table_id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.lab.id
}
```

^ Create VPC (also, IGW and route)

# Add subnets

`subnets.tf`
```
resource "aws_subnet" "lab_az1" {
  vpc_id = aws_vpc.lab.id

  map_public_ip_on_launch = true

  cidr_block = "10.0.1.0/24"

  availability_zone_id = "use1-az1"

  tags = {
    Name = "${var.owner}-Managed-az1"
  }
}

resource "aws_subnet" "lab_az2" {
  vpc_id = aws_vpc.lab.id

  map_public_ip_on_launch = true

  cidr_block = "10.0.2.0/24"

  availability_zone_id = "use1-az2"

  tags = {
    Name = "${var.owner}-Managed-az2"
  }
}

resource "aws_subnet" "lab_az3" {
  vpc_id = aws_vpc.lab.id

  map_public_ip_on_launch = true

  cidr_block = "10.0.3.0/24"

  availability_zone_id = "use1-az3"

  tags = {
    Name = "${var.owner}-Managed-az3"
  }
}

resource "aws_subnet" "lab_az4" {
  vpc_id = aws_vpc.lab.id

  map_public_ip_on_launch = true

  cidr_block = "10.0.4.0/24"

  availability_zone_id = "use1-az4"

  tags = {
    Name = "${var.owner}-Managed-az4"
  }
}

resource "aws_subnet" "lab_az5" {
  vpc_id = aws_vpc.lab.id

  map_public_ip_on_launch = true

  cidr_block = "10.0.5.0/24"

  availability_zone_id = "use1-az5"

  tags = {
    Name = "${var.owner}-Managed-az5"
  }
}

resource "aws_subnet" "lab_az6" {
  vpc_id = aws_vpc.lab.id

  map_public_ip_on_launch = true

  cidr_block = "10.0.6.0/24"

  availability_zone_id = "use1-az6"

  tags = {
    Name = "${var.owner}-Managed-az6"
  }
}
```

^ Create Subnets

# Redo subnets, with a loop:

`subnets.tf`
```tf

variable "subnet_mappings" {
  default = {
    "az1" = {
      "subnet" = 1,
      "az"     = "1d",
    },
    "az2" = {
      "subnet" = 2,
      "az"     = "1a",
    },
    "az3" = {
      "subnet" = 3,
      "az"     = "1e",
    },
    "az4" = {
      "subnet" = 4,
      "az"     = "1b",
    },
    "az5" = {
      "subnet" = 5,
      "az"     = "1f",
    },
    "az6" = {
      "subnet" = 6,
      "az"     = "1c",
    },
  }
}

resource "aws_subnet" "lab" {
  for_each = var.subnet_mappings

  vpc_id = aws_vpc.lab.id

  map_public_ip_on_launch = true

  cidr_block = "10.0.${each.value.subnet}.0/24"

  availability_zone_id = "use1-${each.key}"

  tags = {
    Name = "${var.owner}-Managed-${each.value.subnet}"
  }
}
```

This uses `for_each` (https://www.terraform.io/language/meta-arguments/for_each) cause it allows for dictionaries, but there's also a `count` meta-argument (https://www.terraform.io/language/meta-arguments/count)

^ Looped Terraform for Subnets

# Add tags and variables

`providers.tf`
```tf
provider "aws" {
  region = var.region

  ignore_tags {
    key_prefixes = [
      "divvy",
      "confluent-infosec"
    ]
  }
}
```

^ Add tags to ignore

Terraform locals: (https://www.terraform.io/language/values/locals) (like a variable, but not variable)

`local-labels.tf`
```tf
locals {
  tf_tags = {
    "tf_owner"         = "Justin Lee",
    "tf_owner_email"   = "jlee@confluent.io",
    "tf_provenance"    = "github.com/justinrlee/private-terraform/aws/${var.region}",
    "tf_last_modified" = "${var.date_updated}",
    "Owner"            = "Justin Lee",
  }
}
```

Update all tags with something like this (https://www.terraform.io/language/functions/merge):

```tf
  tags = merge(
    {
      Name = "something"
    },
    local.tf_tags
  )
```

`variables.tf`
```tf
variable "region" {
  default = "us-east-1"
}

variable "owner" {
  default = "justin"
}

variable "date_updated" {
}
```

`terraform.tfvars`
```tf
date_updated = "2022-04-12"
```

^ Add tags to all resources (exercise for reader)

 # EC2 Instance

Update `variables.tf` to add this:
```tf

variable "build_count" {
  default = 0
}

# Ubuntu 20.04 (2022-01-30)
variable "ami" {
  default = "ami-09e67e426f25ce0d7"
}

variable "whitelist_ips" {
  default = [""]
}

variable "key" {

}
```

```tf
resource "aws_instance" "build" {
  count = var.build_count
  ami   = var.ami

  instance_type = "t3.xlarge"

  key_name                    = "${var.key}"
  associate_public_ip_address = true
  iam_instance_profile        = "Justin-Secrets"
  subnet_id                   = aws_subnet.justin[keys(var.subnet_mappings)[count.index]].id

  vpc_security_group_ids = [aws_security_group.all_traffic.id ]

  root_block_device {
    volume_size = 40
    tags =  merge({
      Name = "${var.owner}-build-workstation"
      },
    local.tf_tags)
  }

  tags = merge({
    Name = "${var.owner}-build-workstation"
    },
  local.tf_tags)
}

output "build" {
  value = {
    ip  = aws_instance.build[*].public_ip,
    dns = aws_instance.build[*].public_dns,
  }
}
```

`terraform apply -var build_count=1`

# Module!  With EKS!

```tf
module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 18.0"

  cluster_name    = "my-cluster"
  cluster_version = "1.21"

  cluster_endpoint_private_access = true
  cluster_endpoint_public_access  = true

  vpc_id     = aws_vpc.lab.id
  subnet_ids = ["subnet-abcde012", "subnet-bcde012a", "subnet-fghi345a"]

  # EKS Managed Node Group(s)
  eks_managed_node_group_defaults = {
    disk_size      = 50
    instance_types = ["m6i.large", "m5.large", "m5n.large", "m5zn.large"]
  }

  eks_managed_node_groups = {
    blue = {}
    green = {
      min_size     = 1
      max_size     = 10
      desired_size = 1

      instance_types = ["t3.large"]
      capacity_type  = "SPOT"
    }
  }

  # aws-auth configmap
  manage_aws_auth_configmap = true

  aws_auth_roles = [
    {
      rolearn  = "arn:aws:iam::66666666666:role/role1"
      username = "role1"
      groups   = ["system:masters"]
    },
  ]

  tags = {
    Environment = "dev"
    Terraform   = "true"
  }
}
```