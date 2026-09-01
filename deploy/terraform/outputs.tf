output "gateway_ecr_url" {
  value = aws_ecr_repository.gateway.repository_url
}

output "console_ecr_url" {
  value = aws_ecr_repository.console.repository_url
}
