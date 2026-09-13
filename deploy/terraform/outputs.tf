output "gateway_ecr_url" {
  value = aws_ecr_repository.gateway.repository_url
}

output "console_ecr_url" {
  value = aws_ecr_repository.console.repository_url
}

output "cluster_name" {
  value = module.eks.cluster_name
}

output "cluster_endpoint" {
  value = module.eks.cluster_endpoint
}

output "cluster_certificate_authority_data" {
  description = "Base64-encoded public cluster CA certificate for Kubernetes clients."
  value       = module.eks.cluster_certificate_authority_data
}

output "oidc_provider_arn" {
  value = module.eks.oidc_provider_arn
}

output "region" {
  value = var.region
}

output "configure_kubectl" {
  description = "Run using an IAM identity granted EKS access; network access to the endpoint is also required."
  value       = "aws eks update-kubeconfig --region ${var.region} --name ${module.eks.cluster_name}"
}
