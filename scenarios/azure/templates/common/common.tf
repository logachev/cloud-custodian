provider "azurerm" {
  # Whilst version is optional, we /strongly recommend/ using it to pin the version of the Provider being used
  version = "=1.34.0"
}

variable rg_name{
}

variable name{
}

variable location{
    default = "eastus"
}


resource "azurerm_resource_group" "test" {
  name     = var.name
  location = var.location
}