variable  "backend" {type = string}  
variable  "database" {type = string} 
variable  "env_name" {type = string} 
#the vpc , public_subnets ... has hardned ips , I need to give them elastic ips 
#so when terraform want to create a new vpc no collision of ips  