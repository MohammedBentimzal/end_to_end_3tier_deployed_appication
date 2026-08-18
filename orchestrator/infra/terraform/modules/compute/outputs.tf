output "nginx_vm_public_ip" {
    value = aws_instance.front_server.public_ip
}
