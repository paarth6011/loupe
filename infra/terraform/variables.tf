variable "project_id" {
  type        = string
  description = "GCP project ID to deploy into."
}

variable "region" {
  type        = string
  description = "GCP region for all regional resources."
  default     = "us-central1"
}

variable "name_prefix" {
  type        = string
  description = "Prefix for all resource names."
  default     = "cloudops"
}

variable "db_name" {
  type    = string
  default = "cloudops"
}

variable "db_user" {
  type    = string
  default = "cloudops"
}

variable "backend_image" {
  type        = string
  description = "Full Artifact Registry image ref for the backend (built + pushed first)."
}

variable "frontend_image" {
  type        = string
  description = "Full Artifact Registry image ref for the frontend (built with VITE_API_URL=backend URL)."
}

variable "admin_username" {
  type    = string
  default = "admin"
}

variable "admin_password" {
  type        = string
  description = "Dashboard admin password (stored in Secret Manager)."
  sensitive   = true
}

variable "anthropic_api_key" {
  type        = string
  description = "Anthropic API key for LLM summaries; empty uses the template fallback."
  default     = ""
  sensitive   = true
}

variable "cors_origins" {
  type        = string
  description = "Comma-separated allowed CORS origins. Set to the frontend URL after first deploy."
  default     = "http://localhost:5173"
}
