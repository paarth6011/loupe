terraform {
  required_version = ">= 1.5"

  # State holds secrets in plaintext: the generated JWT signing key and DB
  # password, plus the admin password. With the default *local* backend that
  # lands in terraform.tfstate on disk (git-ignored, but unencrypted). For any
  # shared/real deployment use an encrypted, access-controlled remote backend so
  # reading the state can't hand someone the JWT secret (and thus forged admin
  # tokens). Example (uncomment and set your bucket):
  #
  # backend "gcs" {
  #   bucket = "my-tfstate-bucket" # CMEK-encrypted, uniform bucket-level access,
  #   prefix = "loupe"             # least-privilege IAM, versioning on
  # }

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}
