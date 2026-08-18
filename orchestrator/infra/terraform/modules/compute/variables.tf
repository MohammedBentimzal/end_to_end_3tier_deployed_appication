variable  "backend" {type = string}  
variable  "database" {type = string} 
variable  "env_name" {type = string} 

variable "public_subnet_id" {
    type = string
}
variable "bastion_sg_id" {
    type = string
}
variable "nginx_sg_id" {
    type = string
}
variable "backend_eni_id" {
    type = string
}
variable "data_eni_id" {
    type = string
}
