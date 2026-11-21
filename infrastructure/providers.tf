provider "aws" {
  region              = "us-east-1"
  allowed_account_ids = ["402909940511"]

  default_tags {
    tags = {
      Project   = "cascadasen"
      ManagedBy = "terraform"
    }
  }
}
