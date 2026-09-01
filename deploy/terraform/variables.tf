variable "project" {
  type    = string
  default = "llm-serving-platform"
}

variable "environment" {
  description = "dev | staging | production"
  type        = string
  default     = "dev"
}

variable "region" {
  type    = string
  default = "us-west-2"
}

variable "vpc_id" {
  type = string
}

variable "subnet_ids" {
  type = list(string)
}

variable "node_instance_type" {
  type    = string
  default = "m6i.large"
}
