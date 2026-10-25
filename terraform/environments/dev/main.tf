resource "azurerm_resource_group" "finops" {
  name     = "rg-azure-finops-dev"
  location = var.location

  tags = {
    project     = var.project_name
    environment = var.environment
    team        = "platform-engineering"
    service     = "finops"
    owner       = var.owner
    managed_by  = "terraform"
    cost_center = var.cost_center
  }
}

resource "azurerm_storage_account" "costdata" {
  name = "finops${substr(
    lower(replace(var.subscription_id, "-", "")), 0, 12
  )}"
  resource_group_name      = azurerm_resource_group.finops.name
  location                 = azurerm_resource_group.finops.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  account_kind             = "StorageV2"
  min_tls_version          = "TLS1_2"

  allow_nested_items_to_be_public = false
  shared_access_key_enabled       = false

  blob_properties {
    versioning_enabled = false

    delete_retention_policy {
      days = 7
    }
  }

  tags = {
    project     = var.project_name
    environment = var.environment
    team        = "platform-engineering"
    service     = "cost-data-storage"
    owner       = var.owner
    managed_by  = "terraform"
    cost_center = var.cost_center
  }
}

resource "azurerm_storage_container" "exports" {
  name                  = "cost-exports"
  storage_account_id    = azurerm_storage_account.costdata.id
  container_access_type = "private"
}

output "resource_group_name" {
  value = azurerm_resource_group.finops.name
}

output "storage_account_name" {
  value = azurerm_storage_account.costdata.name
}

output "storage_container_name" {
  value = azurerm_storage_container.exports.name
}
