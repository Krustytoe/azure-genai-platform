terraform {
  required_version = ">= 1.7"
  required_providers {
    azurerm = {
      source = "hashicorp/azurerm"
      # 4.33 is the oldest release with every block used here (enabled_metric on
      # diagnostic settings is the newest). Tested on 4.x and 5.x.
      version = ">= 4.33, < 6.0"
    }
  }
}
