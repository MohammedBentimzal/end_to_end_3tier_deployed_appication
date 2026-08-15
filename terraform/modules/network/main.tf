#contains network module to be reused in each demand
#it contains one VPC per environment, subnets, firewall(security_groups)
#data source to give my ip dynamically

data "http" "my_public_ip" {
  url = "https://ifconfig.me/ip"
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
    Name = "${var.env_name}_vpc" 
  }
}

#subnets 
#the route table that determines wether the subnet is private or public 
#public subnet : in the route table the access to the internet pass by internet gateway 

resource "aws_subnet" "public_subnet" {
  vpc_id = aws_vpc.main.id 
  cidr_block = "10.0.1.0/24"
  tags = {
    Name = "public-subnet"
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
    Name = "${var.backend}-subnet"
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
    Name = "${var.backend}_nat_gw"
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
    Name = "${var.backend}_rt"
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
    Name = "${var.database}-subnet"
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
    Name = "${var.database}_nat_gw"
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
    Name = "${var.database}_rt"
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
    cidr_blocks = ["${trimspace(data.http.my_public_ip.response_body)}/32"] #trimspaced is used if the website add new lines after the ip it removesit 
    #response_body to give me the body of the response that contains my ip 
    #individual device so the subnet is always 255.255.255.255
  }                #my ip changes over time so I need to automate that 
                   #normally when a user authenticate he needs to send the infos to my machine
                   #(backend,database,name) and me I'll return to him the public ip of the instance
                   #but how ? and what if two people asks for infrastructure at the same time ?
                   
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
    cidr_blocks = ["${trimspace(data.http.my_public_ip.response_body)}/32"] #individual device so the subnet is always 255.255.255.255
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
  name = "${var.backend}_sg"
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
    from_port = 8000
    to_port = 8000
    protocol = "tcp" 
    security_groups = [aws_security_group.front_sg.id]
  }
  ingress {
    from_port = 8080
    to_port = 8080
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
    Name = "${var.backend}_sg"
  }
}
#database : accept from backend sg on the database port 
resource "aws_security_group" "database_sg" {
  name = "${var.database}_sg"
  description = "well accept the inbound traffic only from backend sg to the database port "
  vpc_id = aws_vpc.main.id 
  
  ingress {
    from_port = 5432
    to_port = 5432
    protocol = "tcp" 
    security_groups = [aws_security_group.backend_sg.id]
  }
  ingress {
    from_port = 3306
    to_port = 3306
    protocol = "tcp" 
    security_groups = [aws_security_group.backend_sg.id]
  }
  ingress {
    from_port = 27017
    to_port = 27017
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