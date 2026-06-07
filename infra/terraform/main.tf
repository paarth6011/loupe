locals {
  # Cloud SQL connection name: project:region:instance
  sql_connection = google_sql_database_instance.pg.connection_name
  database_url = format(
    "postgresql+psycopg://%s:%s@/%s?host=/cloudsql/%s",
    var.db_user,
    random_password.db.result,
    var.db_name,
    local.sql_connection,
  )
  redis_url = "redis://${google_redis_instance.cache.host}:${google_redis_instance.cache.port}/0"
}

# ----------------------------------------------------------------------------
# Enable required APIs
# ----------------------------------------------------------------------------
resource "google_project_service" "apis" {
  for_each = toset([
    "run.googleapis.com",
    "sqladmin.googleapis.com",
    "redis.googleapis.com",
    "secretmanager.googleapis.com",
    "artifactregistry.googleapis.com",
    "vpcaccess.googleapis.com",
    "compute.googleapis.com",
  ])
  service            = each.value
  disable_on_destroy = false
}

# ----------------------------------------------------------------------------
# Networking: VPC + Serverless VPC Access connector (so Cloud Run reaches Redis)
# ----------------------------------------------------------------------------
resource "google_compute_network" "vpc" {
  name                    = "${var.name_prefix}-vpc"
  auto_create_subnetworks = false
  depends_on              = [google_project_service.apis]
}

resource "google_vpc_access_connector" "connector" {
  name          = "${var.name_prefix}-conn"
  region        = var.region
  network       = google_compute_network.vpc.name
  ip_cidr_range = "10.8.0.0/28"
  depends_on    = [google_project_service.apis]
}

# ----------------------------------------------------------------------------
# Artifact Registry (Docker images)
# ----------------------------------------------------------------------------
resource "google_artifact_registry_repository" "images" {
  location      = var.region
  repository_id = "${var.name_prefix}-images"
  format        = "DOCKER"
  depends_on    = [google_project_service.apis]
}

# ----------------------------------------------------------------------------
# Cloud SQL (Postgres) — replaces the local Postgres container
# ----------------------------------------------------------------------------
resource "google_sql_database_instance" "pg" {
  name                = "${var.name_prefix}-pg"
  database_version    = "POSTGRES_16"
  region              = var.region
  deletion_protection = false

  settings {
    tier              = "db-f1-micro"
    availability_type = "ZONAL"
    disk_size         = 10
    disk_autoresize   = true
  }

  depends_on = [google_project_service.apis]
}

resource "google_sql_database" "db" {
  name     = var.db_name
  instance = google_sql_database_instance.pg.name
}

resource "random_password" "db" {
  length  = 24
  special = false
}

resource "google_sql_user" "user" {
  name     = var.db_user
  instance = google_sql_database_instance.pg.name
  password = random_password.db.result
}

# ----------------------------------------------------------------------------
# Memorystore (Redis) — replaces the local Redis container
# ----------------------------------------------------------------------------
resource "google_redis_instance" "cache" {
  name               = "${var.name_prefix}-redis"
  tier               = "BASIC"
  memory_size_gb     = 1
  region             = var.region
  redis_version      = "REDIS_7_0"
  authorized_network = google_compute_network.vpc.id
  depends_on         = [google_project_service.apis]
}

# ----------------------------------------------------------------------------
# Secrets (Secret Manager) — never baked into images or committed
# ----------------------------------------------------------------------------
resource "random_password" "jwt" {
  length  = 48
  special = false
}

resource "google_secret_manager_secret" "database_url" {
  secret_id = "${var.name_prefix}-database-url"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "database_url" {
  secret      = google_secret_manager_secret.database_url.id
  secret_data = local.database_url
}

resource "google_secret_manager_secret" "jwt_secret" {
  secret_id = "${var.name_prefix}-jwt-secret"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "jwt_secret" {
  secret      = google_secret_manager_secret.jwt_secret.id
  secret_data = random_password.jwt.result
}

resource "google_secret_manager_secret" "admin_password" {
  secret_id = "${var.name_prefix}-admin-password"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "admin_password" {
  secret      = google_secret_manager_secret.admin_password.id
  secret_data = var.admin_password
}

resource "google_secret_manager_secret" "anthropic_api_key" {
  secret_id = "${var.name_prefix}-anthropic-api-key"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "anthropic_api_key" {
  secret      = google_secret_manager_secret.anthropic_api_key.id
  secret_data = var.anthropic_api_key == "" ? " " : var.anthropic_api_key
}

# ----------------------------------------------------------------------------
# Runtime service account + IAM
# ----------------------------------------------------------------------------
resource "google_service_account" "run" {
  account_id   = "${var.name_prefix}-run"
  display_name = "Cloud Run runtime SA for ${var.name_prefix}"
}

resource "google_project_iam_member" "sql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.run.email}"
}

resource "google_project_iam_member" "secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.run.email}"
}

# ----------------------------------------------------------------------------
# Cloud Run — backend
# ----------------------------------------------------------------------------
resource "google_cloud_run_v2_service" "backend" {
  name                = "${var.name_prefix}-backend"
  location            = var.region
  deletion_protection = false
  ingress             = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.run.email

    vpc_access {
      connector = google_vpc_access_connector.connector.id
      egress    = "PRIVATE_RANGES_ONLY"
    }

    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [local.sql_connection]
      }
    }

    containers {
      image = var.backend_image
      ports {
        container_port = 8080
      }

      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }

      env {
        name  = "ENVIRONMENT"
        value = "production"
      }
      env {
        name  = "REDIS_URL"
        value = local.redis_url
      }
      env {
        name  = "CORS_ORIGINS"
        value = var.cors_origins
      }
      env {
        name  = "ADMIN_USERNAME"
        value = var.admin_username
      }
      env {
        name = "DATABASE_URL"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.database_url.secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "JWT_SECRET"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.jwt_secret.secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "ADMIN_PASSWORD"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.admin_password.secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "ANTHROPIC_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.anthropic_api_key.secret_id
            version = "latest"
          }
        }
      }

      startup_probe {
        http_get {
          path = "/health"
        }
        initial_delay_seconds = 5
        period_seconds        = 5
        failure_threshold     = 10
      }
      liveness_probe {
        http_get {
          path = "/health"
        }
      }
    }
  }

  depends_on = [
    google_project_iam_member.secret_accessor,
    google_secret_manager_secret_version.database_url,
  ]
}

# ----------------------------------------------------------------------------
# Cloud Run — frontend (static SPA via nginx)
# ----------------------------------------------------------------------------
resource "google_cloud_run_v2_service" "frontend" {
  name                = "${var.name_prefix}-frontend"
  location            = var.region
  deletion_protection = false
  ingress             = "INGRESS_TRAFFIC_ALL"

  template {
    containers {
      image = var.frontend_image
      ports {
        container_port = 8080
      }
    }
  }

  depends_on = [google_project_service.apis]
}

# ----------------------------------------------------------------------------
# Allow unauthenticated access to both services (public dashboard + API)
# ----------------------------------------------------------------------------
resource "google_cloud_run_v2_service_iam_member" "backend_public" {
  name     = google_cloud_run_v2_service.backend.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_v2_service_iam_member" "frontend_public" {
  name     = google_cloud_run_v2_service.frontend.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}
