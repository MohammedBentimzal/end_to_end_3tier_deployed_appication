output "public_subnet_id" {
    value = aws_subnet.public_subnet.id
}
output "bastion_sg_id" {
    value = aws_security_group.bastion_sg.id
}
output "nginx_sg_id" {
    value = aws_security_group.front_sg.id
}
output "backend_eni_id" {
    value = aws_network_interface.example.id
}
output "data_eni_id" {
    value = aws_network_interface.dataeni.id 
}
