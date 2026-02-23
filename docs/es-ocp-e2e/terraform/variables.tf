# Input variables

variable "project_name" {
  description = "Project name"
  type        = string
  default     = "es-ocp-e2e"
}

variable "environment" {
  description = "Environment"
  type        = string
  default     = "dev"
}
