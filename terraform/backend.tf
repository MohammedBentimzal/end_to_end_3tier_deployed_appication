#use s3 bucket so state is shared and locked 
#we need to work with workspaces so the environments stay separated
terraform {
  backend "s3" {
    bucket = "s3-bucket-464716974375" #name of the backet 
    key    = "idp-aws/terraform.tfstate" #the file path/name that Terraform's state file will be stored under
    # we chose this file
    region = "us-west-2"
    use_lockfile = true
  }
}
