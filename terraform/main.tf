provider "aws" {
  region = "us-west-2"
}

data "aws_ami" "ubuntu" {
  most_recent = true

  filter {
    name = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]
  }

  owners = ["099720109477"] # Canonical
}

resource "aws_instance" "app_server" {
  ami           = data.aws_ami.ubuntu.id
  instance_type = "t3.micro"
  key_name = "flask_app"
  subnet_id = backend-subnet.id
  network_interface_id = aws_network_interface.example.id 
  tags = {
    Name = "flask-app-machine"
  }
}
#the interface resource that links between the public subnet and the instance 
resource "aws_network_interface" "example" {
  subnet_id = aws_subnet.public_subnet.id
  private_ips = ["10.0.2.10"]
}

#each vpc will represent a combination so for now we'll made one vpc for one envirment 
#this vpc will be segmentated into subnets and each subnet will contain a tier so we need 3 subnets 
#between those subnets we'll configure firewalls mentionned in the project 


resource "aws_vpc" "main" {
  cidr_block = "10.0.0.0/16"
  tags = {
    Name = "first_combo"
  }
}

#subnets 
#the route table that determines wether the subnet is private or public 
#public subnet : in the route table the access to the internet pass by internet gateway 

resource "aws_subnet" "public_subnet" {
  vpc_id = aws_vpc.main.id 
  cidr_block = "10.0.1.0/24"
  tags = {
    Name = "front-subnet"
  }
}
#internet gateway
resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.main.id 
  tags = {
    Name = "igw"
  }
}
#now we needto create the route table and the route table association between the subnet and route table
#for Nginx whatever the destination outside the vpc it passes by internet gateway 0.0.0.0/0 -> internet gateway 
#inside of the vpc network talk locally between subnets 
resource "aws_route_table" "public_rt" {
  vpc_id = aws_vpc.main.id 
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.igw.id
  }
} 
#now we need to associate this route table to the subnet we use aws_route_table_association resource 
resource "aws_route_table_association" "public_as" {
  subnet_id = aws_subnet.public_subnet.id
  route_table_id = aws_route_table.public_rt.id 
}

#private subnet : the resource communicate to the internet via NAT gateway 

resource "aws_subnet" "private_subnet" {
  vpc_id = aws_vpc.main.id 
  cidr_block = "10.0.2.0/24"
  tags = {
    Name = "backend-subnet"
  }
}
#NAT Gateway depends on the internet gateway
#the nat needs a public ip they call it elastic ip so we need to use the aws elastic ip resource aws_eip
resource "aws_eip" "ipr" {
  domain = "vpc"
  tags = {
    Name = "ipr"
  }
}
resource "aws_nat_gateway" "nat_gw" {
  allocation_id = aws_eip.ipr.id 
  subnet_id = aws_subnet.private_subnet.id 
  tags = {
    Name = "nat_gw"
  }
  depends_on = [aws_internet_gateway.igw]
}
#route table :if the destination is outside the vpc network use the NAT to deliver it to internet gateway 
#so the route keeps private 
resource "aws_route_table" "private_rt" {
  route {
    cidr_block = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.nat_gw.id
  }
}
resource "aws_route_table_association" "private_as" {
  subnet_id = aws_subnet.private_subnet.id
  route_table_id = aws_route_table.private_rt.id 
}


resource "aws_subnet" "data_subnet" {
  vpc_id = aws_vpc.main.id 
  cidr_block = "10.0.3.0/24"
  tags = {
    Name = "database-subnet"
  }
} 
#we mention only the vpc id because in the database subnet communicate only with the private subnet
#which exist in the same network so aws already creates the route 
resource "aws_route_table" "data_rt" {
  vpc_id = aws_vpc.main.id 
  tags = {
    Name = "data_rt"
  }
}
resource "aws_route_table_association" "data_as" {
  subnet_id = aws_subnet.data_subnet.id
  route_table_id = aws_route_table.data_rt.id 
}

#the firewall layer which is the security group that we want to use for the backend 
# the firewall enforce the least priviliege to the network subnets 
#firstly we'll create security group within the vpc then attach it to the ENI of the VM



resource "aws_security_group" "allow_nginx" {
  name = "allow_nginx"
  description = "we'll accept the inbound traffic only from nginx port to the database port "
  vpc_id = aws_vpc.main.id 
  tags = {
    Name = "allow_nginx"
  }
}
