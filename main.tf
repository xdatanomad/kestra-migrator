terraform {
    required_version = ">= 1.7.0"

    required_providers {
    kestra = {
        source  = "kestra-io/kestra"
        version = "~> 1.0"
    }
    }
}

provider "kestra" {
    url       = var.kestra_url
    username  = var.kestra_username
    password  = var.kestra_password
    tenant_id = var.tenant
    # OR using api token
    # api_token = var.kestra_api_token
}
