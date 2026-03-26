# Input variables

variable "project_name" {
  description = "Project name"
  type        = string
  default     = "test-project"
}

variable "environment" {
  description = "Environment"
  type        = string
  default     = "dev"
}
