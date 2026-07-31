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
#we need bastion instance so we can ssh the private vms 
resource "aws_instance" "bastion_server" {
  ami           = data.aws_ami.ubuntu.id
  instance_type = "t3.micro"
  key_name = "flask_app"
  #this instance needs to be accessible from internet 
  subnet_id = aws_subnet.public_subnet.id
  # to mention security group in the instance : vpc_security_group_ids
  vpc_security_group_ids = [aws_security_group.bastion_sg.id]
  associate_public_ip_address = true
  tags = {
    Name = "bastion-machine"
    role = "bastion"
  }
}

#we need to create the frontend instance so we can ssh to it and see if the backend will response 
resource "aws_instance" "front_server" {
  ami           = data.aws_ami.ubuntu.id
  instance_type = "t3.micro"
  key_name = "flask_app"
  subnet_id = aws_subnet.public_subnet.id
  # to mention security group in the instance : vpc_security_group_ids
  vpc_security_group_ids = [aws_security_group.front_sg.id]
  # to give to the instance a pubilc ip to connect to it asoociate_public_ip_address
  associate_public_ip_address = true
  tags = {
    Name = "front-machine"
    role = "nginx"
  }
}

#the instance for the backend 
resource "aws_instance" "app_server" {
  ami           = data.aws_ami.ubuntu.id
  instance_type = "t3.micro"
  key_name = "flask_app"
  primary_network_interface {
    network_interface_id = aws_network_interface.example.id 
  }
  tags = {
    Name = "backend-machine"
    role = "backend"
  }
}
resource "aws_instance" "database_server" {
  ami           = data.aws_ami.ubuntu.id
  instance_type = "t3.micro"
  key_name = "flask_app"
  primary_network_interface {
    network_interface_id = aws_network_interface.dataeni.id 
  }
  tags = {
    Name = "database-machine"
    role = "database"
  }
}

#the interface resource that links between the private subnet and the instance 
resource "aws_network_interface" "example" {
  subnet_id = aws_subnet.private_subnet.id 
  security_groups = [aws_security_group.backend_sg.id]
  private_ips = ["10.0.2.10"]
  tags = {
    Name = "primary_network_interface"
  }
}
#we need to give to the database an eni so it will have a fixed private ip we mentioned in the app.py host
resource "aws_network_interface" "dataeni" {
  subnet_id = aws_subnet.data_subnet.id 
  security_groups = [aws_security_group.database_sg.id]
  private_ips = ["10.0.3.10"]
  tags = {
    Name = "database_network_interface"
  }
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
  tags = {
    Name = "public_rt"
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
#the NAT needs to be in a public subnet so it can access the internet gateway 
resource "aws_nat_gateway" "nat_gw" {
  allocation_id = aws_eip.ipr.id 
  subnet_id = aws_subnet.public_subnet.id 
  tags = {
    Name = "nat_gw"
  }
  depends_on = [aws_internet_gateway.igw]
}
#route table :if the destination is outside the vpc network use the NAT to deliver it to internet gateway 
#so the route keeps private 
resource "aws_route_table" "private_rt" {
  vpc_id = aws_vpc.main.id 
  route {
    cidr_block = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.nat_gw.id
  }
  tags = {
    Name = "private_rt"
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
resource "aws_eip" "dbipr" {
  domain = "vpc"
  tags = {
    Name = "ipr"
  }
}
#the NAT needs to be in a public subnet so it can access the internet gateway 
resource "aws_nat_gateway" "dbnat_gw" {
  allocation_id = aws_eip.dbipr.id 
  subnet_id = aws_subnet.public_subnet.id 
  tags = {
    Name = "dbnat_gw"
  }
  depends_on = [aws_internet_gateway.igw]
}
#we mention only the vpc id because in the database subnet communicate only with the private subnet
#which exist in the same network so aws already creates the route 
resource "aws_route_table" "data_rt" {
  vpc_id = aws_vpc.main.id 
  route {
    cidr_block = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.dbnat_gw.id
  }
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
#we'll need 3 security groups 

#for the instance of the front : accept ssh http https traffic from anywhere
resource "aws_security_group" "front_sg" {
  name = "front_sg"
  description = "well accept the inbound traffic from all"
  vpc_id = aws_vpc.main.id 
  
  ingress {
    from_port = 80
    to_port = 80
    protocol = "tcp" 
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    from_port = 443
    to_port = 443
    protocol = "tcp" 
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    from_port = 22
    to_port = 22
    protocol = "tcp"   
    cidr_blocks = ["196.77.28.188/32"] #individual device so the subnet is always 255.255.255.255
  }
  egress {
    from_port = 0
    to_port = 0
    protocol = "-1" #all protocols
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = {
    Name = "front_sg"
  }
}
#we'll need security group for bastion instance that will allow the traffic frommy ùachine into backend and database with ssh 
resource "aws_security_group" "bastion_sg" {
  name = "bastion_sg"
  description = "well accept the inbound traffic my machine and connect me to other private vms"
  vpc_id = aws_vpc.main.id 
  
  ingress {
    from_port = 22
    to_port = 22
    protocol = "tcp" 
    cidr_blocks = ["196.77.28.188/32"] #individual device so the subnet is always 255.255.255.255
  }
  egress {
    from_port = 0
    to_port = 0
    protocol = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  
  tags = {
    Name = "bastion_sg"
  }
}
#for the backend sg accept from front security group on the port of the backend 5000 
resource "aws_security_group" "backend_sg" {
  name = "backend_sg"
  description = "well accept the inbound traffic only from nginx port to the database port "
  vpc_id = aws_vpc.main.id 
  #add connectivity from bastion over ssh so I can reach this vm with my machine 
  ingress {
    from_port = 22
    to_port = 22
    protocol = "tcp" 
    security_groups = [aws_security_group.bastion_sg.id]
  }
  ingress {
    from_port = 5000
    to_port = 5000
    protocol = "tcp" 
    security_groups = [aws_security_group.front_sg.id]
  }
  
  egress {
    from_port = 0
    to_port = 0
    protocol = "-1" #all protocols
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = {
    Name = "backend_sg"
  }
}
#database : accept from backend sg on the database port 
resource "aws_security_group" "database_sg" {
  name = "database_sg"
  description = "well accept the inbound traffic only from backend sg to the database port "
  vpc_id = aws_vpc.main.id 
  
  ingress {
    from_port = 5432
    to_port = 5432
    protocol = "tcp" 
    security_groups = [aws_security_group.backend_sg.id]
  }
  ingress {
    from_port = 22
    to_port = 22
    protocol = "tcp" 
    security_groups = [aws_security_group.bastion_sg.id]
  }
  egress {
    from_port = 0
    to_port = 0
    protocol = "-1" #all protocols
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "database_sg"
  }
}