variable "subscription_id" {
  description = "Azure subscription ID"
  type        = string
}

variable "location" {
  description = "Azure deployment region"
  type        = string
  default     = "centralus"
}

variable "project_name" {
  type    = string
  default = "azure-finops"
}

variable "environment" {
  type    = string
  default = "dev"
}

variable "owner" {
  type    = string
  default = "platform-team"
}

variable "cost_center" {
  type    = string
  default = "CC-1001"
}
