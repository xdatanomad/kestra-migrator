# Kestra migration vi Terraform

This project shows how to use Terraform to migrate from an older version of Kestra to a new version. It does _NOT_ actually provision the Kestra instances, rather it exports/imports Kestra resources such as flows, namespace, ns files, users, roles from old > new instance.


## Installation

1. Install [Terraform](https://developer.hashicorp.com/terraform/install) (v1.5+ recommended) and ensure `terraform -version` works.
2. Create and activate a Python virtual environment using [uv](https://github.com/astral-sh/uv):
    ```bash
    uv venv
    source .venv/bin/activate
    ```
3. Install Python dependencies:
    ```bash
    pip install -r requirements.txt
    ```

## Prepare Terraform Import

This project includes a utility called `export.py`.  This utility connects to the old Kestra instance, exports all resources. At the moment it supports: Namespaces, Flows, Files.

The script will produce two outputs:
1. a `kestra.tfvars` file containing all the resources to import
2. a `import.sh` bash script that contains all the `terraform import` commands

There's an example [`envs/kestra.tfvars`](envs/kestra.tfvars) file.

To run the export script, use the following command:

```bash
# you can omit the path in older versions of Kestra
python export.py run --url http://localhost:8080 --username kestra --password kestra --tenant main

# for additional parameters, run:
python export.py run --help
```

You should see two new files created: `kestra.tfvars` and `import.sh` generated under the current directory.

You should also see an output similar to this:

```terminal
Connecting to Kestra at http://localhost:8086 (tenant=main) (pparvizi@kestra.io:********) (path=storage)
Connection successful.

********** kestra.tfvars **********

kestra_base_url = "http://localhost:8080"
kestra_username = "admin@kestra.io"
kestra_password = "********"

namespaces = [
  "company",
  "company.team",
  "system",
]
...
```

## Export from Kestra into Terraform State

To import the exported resources into your new Kestra instance using Terraform, follow these steps:

```bash
terraform init

# run the import script
./import.sh


# OR - subsequently, you can run the commands manually:
# importing a namespace
terraform import -var-file=kestra.tfvars 'kestra_namespace.namespaces["company"]' company
# importing a flow
terraform import -var-file=kestra.tfvars 'kestra_flow.flows["company.team|flow-log"]' company.team/flow-log
```

## Import from Terraform State into Kestra

First, edit the `kestra.tfvars` file to point to your new Kestra instance by updating the `kestra_base_url`, `kestra_username`, and `kestra_password` values.

To apply the imported resources to your new Kestra instance, use the following Terraform commands:

```bash
terraform init
terraform plan -var-file=kestra.tfvars
terraform apply -var-file=kestra.tfvars
```

## Notes
