terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.region
}

# Container registry for the two images the platform ships.
resource "aws_ecr_repository" "gateway" {
  name                 = "${var.project}-gateway"
  image_tag_mutability = "IMMUTABLE"
  image_scanning_configuration { scan_on_push = true }
}

resource "aws_ecr_repository" "console" {
  name                 = "${var.project}-console"
  image_tag_mutability = "IMMUTABLE"
  image_scanning_configuration { scan_on_push = true }
}

# Managed Kubernetes for deploy/k8s manifests.
module "eks" {
  source          = "terraform-aws-modules/eks/aws"
  version         = "~> 20.0"
  cluster_name    = "${var.project}-${var.environment}"
  cluster_version = "1.30"
  vpc_id          = var.vpc_id
  subnet_ids      = var.subnet_ids

  eks_managed_node_groups = {
    default = {
      instance_types = [var.node_instance_type]
      min_size       = 2
      max_size       = 6
      desired_size   = 2
    }
  }
}
