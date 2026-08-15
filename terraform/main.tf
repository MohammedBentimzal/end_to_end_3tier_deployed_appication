# configure terraform , mention cloud provider aws , its version , version of terraform 
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    http = {
      source  = "hashicorp/http"
      version = "~> 3.0"
    }
  }
  required_version = ">= 1.2"   #the version of terraform CLI 
}

provider "aws" {
  region = "us-west-2"
}
#we'lldefine the module with it's variables that he needs if he need a variable from outputs of outher module we mention it 
module "network" {
    source = "./modules/network"
    env_name = var.env_name
    backend = var.backend
    database = var.database
}
module "compute" {
    source = "./modules/compute"
    env_name = var.env_name
    backend = var.backend
    database = var.database

    public_subnet_id = module.network.public_subnet_id
    bastion_sg_id = module.network.bastion_sg_id
    nginx_sg_id = module.network.nginx_sg_id
    backend_eni_id = module.network.backend_eni_id
    data_eni_id = module.network.data_eni_id
}
