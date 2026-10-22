resource "aws_db_subnet_group" "main" {
  name       = "${var.project}-db-subnets"
  subnet_ids = aws_subnet.private[*].id
}

# Керований PostgreSQL. Пароль генерує і зберігає сам AWS у Secrets Manager
# (manage_master_user_password) — його немає ні в коді, ні в tfvars, ні в state.
resource "aws_db_instance" "main" {
  identifier     = "${var.project}-db"
  engine         = "postgres"
  engine_version = "16"
  instance_class = "db.t4g.micro"

  allocated_storage = 20
  storage_type      = "gp3"
  storage_encrypted = true

  db_name                     = "notes"
  username                    = "notes"
  manage_master_user_password = true

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.db.id]
  publicly_accessible    = false
  multi_az               = false # економія для лаби; у проді — true

  backup_retention_period = 0 # без PITR — економія і швидше створення; у проді >= 7
  skip_final_snapshot     = true
  deletion_protection     = false
  apply_immediately       = true
}
