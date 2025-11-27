kestra_url      = "http://localhost:8080"
kestra_username = "admin@kestra.io"
kestra_password = "admin1234"

namespaces = [
  "company.team",
  "solutions"
]

flows_by_namespace = {
  "company.team" = [
    "simple-log",
  ]
  "solutions" = [
    "simple-task",
  ]
}
