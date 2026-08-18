#it s gonna contain one VM per tier, tagged so firewall rules apply correctly, sized via variables


data "aws_ami" "ubuntu" {
  most_recent = true

  filter {
    name = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]
  }

  owners = ["099720109477"] # Canonical
}

#we need bastion instance so we can ssh the private vms 
resource "aws_instance" "bastion_server" {
  ami           = data.aws_ami.ubuntu.id
  instance_type = "t3.micro"
  key_name = "flask_app"
  #this instance needs to be accessible from internet 
  subnet_id = var.public_subnet_id 
  # to mention security group in the instance : vpc_security_group_ids
  vpc_security_group_ids = [var.bastion_sg_id ]
  associate_public_ip_address = true
  tags = {
    Name = "bastion-${var.env_name}"
    role = "bastion"
    env_name = "${var.env_name}"
  }
}

#we need to create the frontend instance so we can ssh to it and see if the backend will response 
resource "aws_instance" "front_server" {
  ami           = data.aws_ami.ubuntu.id
  instance_type = "t3.micro"
  key_name = "flask_app"
  subnet_id = var.public_subnet_id 
  # to mention security group in the instance : vpc_security_group_ids
  vpc_security_group_ids = [var.nginx_sg_id ]
  # to give to the instance a pubilc ip to connect to it asoociate_public_ip_address
  associate_public_ip_address = true
  tags = {
    Name = "front-${var.env_name}"
    role = "nginx"
    env_name = "${var.env_name}"
  }
}

#the instance for the backend 
resource "aws_instance" "app_server" {
  ami           = data.aws_ami.ubuntu.id
  instance_type = "t3.micro"
  key_name = "flask_app"
  primary_network_interface {
    network_interface_id = var.backend_eni_id
  }
  tags = {
    Name = "${var.backend}_${var.env_name}"
    role = "backend"
    env_name = "${var.env_name}"
  }
}
resource "aws_instance" "database_server" {
  ami           = data.aws_ami.ubuntu.id
  instance_type = "t3.micro"
  key_name = "flask_app"
  primary_network_interface {
    network_interface_id = var.data_eni_id 
  }
  tags = {
    Name = "${var.database}_${var.env_name}"
    role = "database"
    env_name = "${var.env_name}"
  }
}