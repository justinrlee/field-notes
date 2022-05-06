# Introduction to Terraform (with AWS)

This is primarily intended as a teaching tool; it should introduce good(ish) behaviors around authenticating to AWS and doing Terraform stuff.

It's really only built for Mac.  Sorry.

I assume you have some familiarity with the terminal, and also know how to use a text editor.

# Prereqs
Install the AWS CLI

```bash
curl "https://awscli.amazonaws.com/AWSCLIV2.pkg" -o "AWSCLIV2.pkg"
sudo installer -pkg AWSCLIV2.pkg -target /
```

Install Homebrew: https://brew.sh/

Install Terraform
    
```bash
brew tap hashicorp/tap
brew install hashicorp/tap/terraform
brew update
brew upgrade hashicorp/tap/terraform
```

Install `gimme-aws-creds`
    
```bash
brew install gimme-aws-creds
````

_If you already have aws creds stored on your laptop, back them up_:

```
if [[ -f ~/.aws/credentials ]];
then
sed -i.bak 's/default/default_old/g' ~/.aws/credentials
fi
```


Configure gimme-aws-creds
```
tee ~/.okta_aws_login_config <<-EOF

[DEFAULT]
# Set your Okta username here or in the OKTA_USERNAME environment variable.
okta_username = ${USER}@confluent.io

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
app_url = https://confluent.okta.com/home/amazon_aws/0oa1l6l54gWFvmDEO357/272
okta_auth_server = 
client_id = 
gimme_creds_server = appurl
aws_appname = 
write_aws_creds = True
cred_profile = default
resolve_aws_alias = True
include_path = False
remember_device = True
aws_default_duration = 3600
device_token = 
output_format = 
EOF
```

Register your laptop
```bash
gimme-aws-creds --action-register-device
```

Wait at least 30 seconds for a new Okta token, then generate creds:
```
gimme-aws-creds
```

Validate that you have credentials:
```
aws sts get-caller-identity
```

# Terraform infra

Create a directory to work in (some working directory that isn't completely ephemeral)

In this directory, make these two files:
* `providers.tf`
* `variables.tf`

Update 'owner' in `terraform.tfvars` with your own name.

`providers.tf`
```tf
provider "aws" {
  region = var.region
}
```

`variables.tf`
```tf
variable "region" {
  default = "us-east-1"
}

variable "owner" {
  default = "somebody"
}
```

`terraform.tfvars`
```tf
owner = "JustinLee"
```

Initialize terraform in this directory
```
terraform init
```

This will download the `aws` Terraform provider and prepare the directory.

Terraform objects are defined in `.tf` files; when you run Terraform actions, all `.tf` files in the directory are combined into one big dependency graph ('terraform template'), and applied.  Valid Terraform objects include:

* `provider`: A particular resource provider in which resources are managed (with a set of configs); for example, AWS
* `resource`: A resource that can be managed by TF
* `local`: basically, an internal variable
* `variable`: an _input variable_ to a Terraform template
* `output`: an _output value` from a Terraform template
* `module`: A reference to another Terraform template that will be used by this template

There's also a default input variable file `terraform.tfvars`; this populates variables

# VPC

Create a VPC with Terraform.  Create this file:

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

Run `terraform plan`; this will generate a plan that is effectively 'here is what would be changed if you ran terraform

Run `terraform apply`; this will create the resources (it will prompt for confirmation)

Log into the AWS console and navigate to us-east-1 region; you should see a created VPC, with an Internet Gateway and a default route

Take a look at the files in `.terraform`.  Also, take a look at `terraform.tfstate`

Run `terraform apply -var owner=test`; (and accept the confirmation); see how your resources change.  Notes:

* We have a **string** variable `owner` with a default value of `somebody`
* Every time we have `var.owner` in one of the Terraform templates, it replaces it with the value.
* In the default terraform variable file, we have owner set to `JustinLee` (or, ideally, your username)
* You can, at runtime, override variables in one of two ways:
  * With a `-var x=y` flag to override a single variable
  * With a `-var-file <x>.tfvars` to override the input file

Run `terraform apply` again to revert the override.  Notes:

* Terraform will generally try to update resources to match the desired state; it will generally only destroy resources if they cannot be changed inline.
* Terraform uses HCL (Hashicorp configuration language)
* The definition of a resource generally looks like this:

```tf
resource "resource_type" "resource_name" {
  # These are regular arguments
  string_argument = "hello"
  numerical_argument = 15.5
  boolean_argument = true
  null_argument = null

  # This is a map/object argument
  map_argument = { 
    string_argument = "foo"
    numerical_argument = 123
  }

  # This is a list/tuple argument (think array; note that unlike JSON, trailing commas are okay)
  list_argument = [
    "hello",
    "goodbye",
    "foo",
  ]
}
```

* Each resource managed by Terraform has a resource identifier.  In our case, we have an AWS VPC with an (internal to the TF template) Terraform resource id of `aws_vpc.lab`.  This resource has arguments (inputs) and attributes (outputs) (you can see the reference for the `aws_vpc` resource type here: https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/vpc)
* Attributes from one resource can be used in other resources; for example, once Terraform creates a VPC, we then uses the attribute `id` from that VPC (fully qualified identifier of `aws_vpc.lab.id` to create an Internet Gateway in that VPC, which is referenced in the arguments for the IGW.

# Add subnets

Let's add some subnets to our VPC.  Create this file:

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

Run `terraform apply`.  It should create a bunch of subnets (log into the AWS console to see this)

# Redo subnets, with a loop:

In the above, we explciitly defined 6 subnets in our AWS VPC.  Now let's do a for loop to create them as a single resource.  Update `subnets.tf` to look like this:

`subnets.tf`
```tf

variable "subnet_mappings" {
  default = {
    "az1" = {
      "subnet" = 11,
      "az"     = "1d",
    },
    "az2" = {
      "subnet" = 12,
      "az"     = "1a",
    },
    "az3" = {
      "subnet" = 13,
      "az"     = "1e",
    },
    "az4" = {
      "subnet" = 14,
      "az"     = "1b",
    },
    "az5" = {
      "subnet" = 15,
      "az"     = "1f",
    },
    "az6" = {
      "subnet" = 16,
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

Note that this will actually remove the old subnets and create new ones, for two reasons:
* We have different CIDR blocks (you can't change the CIDR block on an AWS subnet)
* We have different Terraform resource identifiers (e.g. we changed from `aws_subnet.lab_az1` to `aws_subnet.lab["az1"]`)

# Add tags and variables

Update your `providers.tf` with this:

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

  tags = local.tf_tags
}
```

Terraform locals: (https://www.terraform.io/language/values/locals) (like a variable, but not variable)

Create a new terraform file with a set of locals to define tags for all resources managed by your TF template:

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

Update these files, as well:

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
date_updated = "2022-05-05"
```

Do a `terraform apply`

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

Create `ec2.tf`:

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
  subnet_ids = [for subnet in aws_subnet.lab: subnet.id]

  # EKS Managed Node Group(s)
  eks_managed_node_group_defaults = {
    disk_size      = 50
    instance_types = ["m6i.large", "m5.large", "m5n.large", "m5zn.large", "t3.large"]
  }

  eks_managed_node_groups = {
    blue = {}
    green = {
      min_size     = 1
      max_size     = 10
      desired_size = 1

      instance_types = ["t3.large"]
      # capacity_type  = "SPOT"
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