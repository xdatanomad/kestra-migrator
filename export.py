#!/usr/bin/env python
from __future__ import annotations

import json
import os
from pathlib import Path
from pprint import pprint
from typing import Any, Dict, List, Optional
import logging

import requests
import typer
from pydantic import BaseModel

from kestrapy.rest import ApiException
from kestrapy import ApiClient, Configuration, KestraClient
from io import StringIO
from kestrapy.api import (
    FlowsApi,
    NamespacesApi,
    UsersApi,
    GroupsApi,
    RolesApi,
    KVApi,
    ServiceAccountApi,
)


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger()

app = typer.Typer(help="Kestra exporter (namespaces, flows, files, users, groups, roles, KV, service accounts)")


class ApiContext:
    """
    Wraps Kestra Python SDK + raw HTTP for endpoints not yet in the SDK (e.g. namespace files).
    """

    def __init__(
        self,
        base_url: str,
        tenant: str = "main",
        username: Optional[str] = None,
        password: Optional[str] = None,
        api_token: Optional[str] = None,
        verify_ssl: bool = True,
    ):
        self.base_url = base_url.rstrip("/")
        self.tenant = tenant

        cfg = Configuration()
        cfg.host = self.base_url

        # Auth: either basic auth or bearer token
        if api_token:
            cfg.api_key = {"Bearer": api_token}
            cfg.api_key_prefix = {"Bearer": "Bearer"}
        elif username and password:
            cfg.username = username
            cfg.password = password

        cfg.verify_ssl = verify_ssl

        self.api_client = ApiClient(cfg)

        # SDK API clients
        self.flows_api = FlowsApi(self.api_client)
        self.namespaces_api = NamespacesApi(self.api_client)
        self.users_api = UsersApi(self.api_client)
        self.groups_api = GroupsApi(self.api_client)
        self.roles_api = RolesApi(self.api_client)
        self.kv_api = KVApi(self.api_client)
        self.service_accounts_api = ServiceAccountApi(self.api_client)

        # raw HTTP session (for namespace files)
        self._session = requests.Session()
        if api_token:
            self._session.headers.update({"Authorization": f"Bearer {api_token}"})
        elif username and password:
            self._session.auth = (username, password)

    # ---------- raw HTTP helpers for namespace files ----------

    def list_namespace_files(self, namespace: str) -> List[Dict[str, Any]]:
        """
        Calls GET /api/v1/{tenant}/namespaces/{namespace}/files/directory
        Returns list of file metadata objects (fileName, type, size, etc.).
        """
        url = f"{self.base_url}/api/v1/{self.tenant}/namespaces/{namespace}/files/directory"
        resp = self._session.get(url)
        resp.raise_for_status()
        return resp.json()

    def get_namespace_file_content(self, namespace: str, path: str) -> bytes:
        """
        Calls GET /api/v1/{tenant}/namespaces/{namespace}/files?path=...
        Returns raw bytes of the file.
        """
        url = f"{self.base_url}/api/v1/{self.tenant}/namespaces/{namespace}/files"
        resp = self._session.get(url, params={"path": path})
        resp.raise_for_status()
        return resp.content


class KestraExporter:
    def __init__(self, api: ApiContext, output_dir: Path):
        self.api = api
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ---------- Namespaces ----------

    def get_namespaces(self) -> List[BaseModel]:
        """
        Uses NamespacesApi.search_namespaces to fetch all namespaces.
        """
        namespaces: List[BaseModel] = []
        page = 1
        size = 100
        while True:
            # Kestra API usually uses page/size for pagination
            res = self.api.namespaces_api.search_namespaces(
                tenant=self.api.tenant, page=page, size=size, existing=False,
            )
            # res.content is typical in generated clients; adjust if needed
            items = getattr(res, "results", None)
            if not items:
                break
            # Convert models to dicts
            for ns in items:
                if ns.secret_isolation.enabled:
                    logger.warning(f"Namespace '{ns.id}' has secret isolation enabled; ensure to handle secrets appropriately during migration.")
                namespaces.append(ns)
            if len(items) < size:
                break
            page += 1

        return namespaces

    # ---------- Flows ----------

    def get_flows_by_namespace(self, namespace: str) -> List[BaseModel]:
        """
        Uses FlowsApi.list_flows_by_namespace to export flows per namespace.
        """
        flows: List[BaseModel] = []
        res = self.api.flows_api.list_flows_by_namespace(
            namespace=namespace, tenant=self.api.tenant
        )
        items = getattr(res, "results", res)
        if items: 
            for flow in items:
                flows.append(flow)

        return flows
        

    def export_flows_zip(self, filename: str = "flows.zip") -> Path:
        """
        Uses FlowsApi.export_flows_by_query to export ALL flows as a single ZIP of YAML sources.
        """
        # Most generated clients follow: export_flows_by_query(tenant, **filters)
        zip_bytes = self.api.flows_api.export_flows_by_query(self.api.tenant)
        out_path = self.output_dir / filename
        out_path.write_bytes(zip_bytes)
        return out_path

    # ---------- Namespace files ----------

    def get_namespace_files(self, namespaces: List[str]) -> None:
        """
        Uses raw HTTP endpoints to dump namespace files for each namespace.
        - /files/directory to list
        - /files?path=... to fetch
        """
        base_dir = self.output_dir / "namespace_files"
        base_dir.mkdir(exist_ok=True)

        all_meta: Dict[str, List[Dict[str, Any]]] = {}

        for ns in namespaces:
            typer.echo(f"[namespace-files] Exporting files for namespace: {ns}")
            try:
                entries = self.api.list_namespace_files(ns)
                pprint(entries)
            except Exception as exc:
                typer.echo(f"  ! Failed to list files for {ns}: {exc}")
                continue

            ns_dir = base_dir / ns
            ns_dir.mkdir(exist_ok=True)

            ns_meta: List[Dict[str, Any]] = []

        #     for entry in entries:
        #         filename = entry.get("fileName")
        #         if not filename:
        #             continue

        #         ns_meta.append(entry)

        #         # Build nested path based on fileName (supports directories)
        #         target_path = ns_dir / filename
        #         target_path.parent.mkdir(parents=True, exist_ok=True)

        #         try:
        #             content = self.api.get_namespace_file_content(ns, filename)
        #             target_path.write_bytes(content)
        #         except Exception as exc:
        #             typer.echo(f"    ! Failed to fetch {filename} in {ns}: {exc}")

        #     all_meta[ns] = ns_meta


    # ---------- Users, Groups, Roles, Service Accounts ----------

    def get_users(self) -> list[BaseModel]:
        """
        Uses UsersApi.list_users to export all users.
        """

        # *****************************************
        # ***** TODO: NOT WORKING AS EXPECTED *****
        # *****************************************

        page = 1
        size = 100
        users: List[BaseModel] = []
        while True:
            # THROWS UNAUTHORIZED ERROR
            res = self.api.users_api.list_users(page=page, size=size)
            pprint(res)
            items = getattr(res, "results", res)
            if not items:
                break
            for u in items:
                users.append(u)
            if len(items) < size:
                break
            page += 1

        return users

    def get_groups(self) -> list[BaseModel]:
        """
        Uses GroupsApi.search_groups to export groups (and optionally memberships).
        """
        groups: List[BaseModel] = []
        page = 1
        size = 100
        while True:
            res = self.api.groups_api.search_groups(
                tenant=self.api.tenant, page=page, size=size
            )
            items = getattr(res, "results", res)
            if not items:
                break
            for g in items:
                groups.append(g)
            if len(items) < size:
                break
            page += 1

        return groups

    def get_roles(self) -> list[BaseModel]:
        """
        Uses RolesApi.search_roles to export all roles.
        """
        roles: List[BaseModel] = []
        page = 1
        size = 100
        while True:
            res = self.api.roles_api.search_roles(
                tenant=self.api.tenant, page=page, size=size,
            )
            items = getattr(res, "results", res)
            if not items:
                break
            for r in items:
                roles.append(r)
            if len(items) < size:
                break
            page += 1

        return roles

    def get_service_accounts(self) -> list[BaseModel]:
        """
        Uses ServiceAccountApi.list_service_accounts to export all service accounts (superadmin endpoint).
        """
        try:
            sas = self.api.service_accounts_api.list_service_accounts()
        except Exception as exc:
            typer.echo(f"[service-accounts] Skipping, failed to list: {exc}")
            return

        return sas

    # ---------- KV ----------

    def get_kv(self, namespaces: List[str]) -> None:
        """
        Uses KVApi.list_keys + KVApi.key_value to export key-value store per namespace.
        """
        kv_root = self.output_dir / "kv"
        kv_root.mkdir(exist_ok=True)

        for ns in namespaces:
            typer.echo(f"[kv] Exporting KV for namespace: {ns}")
            try:
                keys = self.api.kv_api.list_keys(self.api.tenant, ns)
            except Exception as exc:
                typer.echo(f"  ! Failed to list KV keys for {ns}: {exc}")
                continue

            kv_data: Dict[str, Any] = {}
            for k in keys:
                try:
                    kv_entry = self.api.kv_api.key_value(self.api.tenant, ns, k)
                    kv_data[k] = self._model_to_dict(kv_entry)
                except Exception as exc:
                    typer.echo(f"    ! Failed to fetch KV '{k}' in ns '{ns}': {exc}")


    # ---------- helpers ----------

    @staticmethod
    def _model_to_dict(obj: Any) -> Any:
        """
        Safely convert Kestra SDK model to dict.
        """
        if obj is None:
            return None
        # OpenAPI models typically expose .to_dict()
        if hasattr(obj, "to_dict"):
            return obj.to_dict()
        # Fallback: dataclasses / simple objects
        if hasattr(obj, "__dict__"):
            return {k: KestraExporter._model_to_dict(v) for k, v in obj.__dict__.items()}
        if isinstance(obj, list):
            return [KestraExporter._model_to_dict(v) for v in obj]
        if isinstance(obj, dict):
            return {k: KestraExporter._model_to_dict(v) for k, v in obj.items()}
        return obj

    @staticmethod
    def _json_default(obj: Any) -> Any:
        """
        Default serializer for json.dumps to handle SDK models.
        """
        return KestraExporter._model_to_dict(obj)




@app.command("test-client")
def test_client(
    base_url: str = typer.Option(
        "http://localhost:8080",
        help="Base Kestra URL (e.g. http://localhost:8080)",
    ),
    tenant: str = typer.Option(
        "main",
        help="Tenant id",
    ),
    username: Optional[str] = typer.Option(
        "admin@kestra.io", help="Basic auth username (if using basic auth)"
    ),
    password: Optional[str] = typer.Option(
        "admin1234", help="Basic auth password (if using basic auth)", hide_input=True
    ),
    api_token: Optional[str] = typer.Option(
        None, help="API token (preferred in EE / Cloud)"
    ),
    output_dir: Path = typer.Option(
        Path.absolute(Path.cwd() / "storage"),
        help="Output directory for exported data (JSON, ZIP, files).",
    ),
):
    """
    Initialize export directory by exporting namespaces only.
    """
    typer.echo(f"Connecting to Kestra at {base_url} (tenant={tenant}) ({username}:{password}) (path={output_dir})")
    typer.echo("Initialization complete.")

    configuration = Configuration(
        host=base_url,
        username=username,
        password=password,
    )

    # Enter a context with an instance of the API client
    client = KestraClient(configuration)
    namespace = 'company.team' # str | Namespace to filter flows
    tenant = tenant # str | 

    try:
        # Retrieve all flows from a given namespace
        api_response = client.flows.list_flows_by_namespace(namespace, tenant)
        print(f"Listing flows: (namespace={namespace}, tenant={tenant})")     
        for flow in api_response:
            print(f"{flow.namespace}: {flow.id}")

        # try exporting flows as zip
        resp_data = client.flows.export_flows_by_ids(tenant, [{'namespace': namespace, 'id': flow.id} for flow in api_response])
        zip_path = output_dir / "export.zip"
        zip_path.parent.mkdir(parents=True, exist_ok=True)
        # Handle common return shapes (raw bytes, ApiResponse-like, file-like)
        data = resp_data
        if not isinstance(data, (bytes, bytearray)):
            # Try attributes
            print("data was not bytes, trying attributes…")
            for attr in ("data", "payload", "content"):
                if hasattr(resp_data, attr):
                    print(f"Found attribute: {attr}")
                    data = getattr(resp_data, attr)
                    break
            else:
                # Try file-like
                print("Trying file-like read()…")
                if hasattr(resp_data, "read"):
                    data = resp_data.read()
        else:
            print("data is already bytes.")
        if not isinstance(data, (bytes, bytearray)):
            raise TypeError(f"Unsupported export data type: {type(data)}")
        with open(zip_path, "wb") as f:
            f.write(data)
        typer.echo(f"Flows ZIP saved to {zip_path.relative_to(Path.cwd())}")

        # trying listing users and groups
        users = client.users.list_users(page=1, size=100)
        print(f"Listing users: (tenant={tenant})")
        pprint(users)
        for user in users.results:
            print(f"User: {user.id} - {user.display_name} - {user.username}")
        groups = client.groups.search_groups(page=1, size=100, tenant=tenant)
        print(f"Listing groups: (tenant={tenant})")
        pprint(groups)
        for group in groups.results:
            print(f"Group: {group.id} - {group.name}")

    except Exception as e:
        print("Exception when calling FlowsApi->list_flows_by_namespace: %s\n" % e)
    

@app.command("run")
def run(
    base_url: str = typer.Option(
        "http://localhost:8080",
        help="Base URL Kestra (e.g. http://localhost:8080)",
    ),
    tenant: str = typer.Option(
        "main",
        help="Tenant id",
    ),
    username: Optional[str] = typer.Option(
        "admin@kestra.io", help="Basic auth username (if using basic auth)"
    ),
    password: Optional[str] = typer.Option(
        "admin1234", help="Basic auth password (if using basic auth)", hide_input=True
    ),
    api_token: Optional[str] = typer.Option(
        None, help="API token (preferred in EE / Cloud)"
    ),
    output_dir: Path = typer.Option(
        Path.absolute(Path.cwd()),
        help="Output directory for exported data. Recommended to use 'storage' subdirectory.",
    ),
):
    """
    Initialize export directory by exporting namespaces only.
    """
    typer.echo(f"\n\nConnecting to Kestra at {base_url} (tenant={tenant}) ({username}:{'*' * len(password)}) (path={output_dir.relative_to(Path.cwd())})")

    # create an ApiContext class
    api = ApiContext(
        base_url=base_url,
        tenant=tenant,
        username=username,
        password=password,
        api_token=api_token,
    )
    # create a KestraExporter class
    ke = KestraExporter(api=api, output_dir=output_dir)
    tfvars: StringIO = StringIO()
    import_sh: StringIO = StringIO()
    typer.echo("Connection successful.\n")
    
    # get namespaces
    nss = ke.get_namespaces()
    # write kestra instance variables
    tfvars.writelines([
        f'kestra_base_url = "{base_url}"\n',
        f'kestra_username = "{username}"\n',
        f'kestra_password = "{password}"\n',
        "\n",
    ])

    # namespaces
    tfvars.write("namespaces = [\n")
    import_sh.write("#!/bin/bash\n\n")
    for ns in nss:
        tfvars.write(f'  "{ns.id}",\n')
        import_sh.write(f"terraform import -var-file=kestra.tfvars 'kestra_namespace.namespaces[\"{ns.id}\"]' {ns.id}\n")
    tfvars.write("]\n\n")
    import_sh.write("\n")

    # flows by namespace
    tfvars.write("flows_by_namespace = {\n")
    for ns in nss:
        flows = ke.get_flows_by_namespace(ns.id)
        tfvars.write(f'  "{ns.id}" = [\n')
        for flow in flows:
            tfvars.write(f'    "{flow.id}",\n')
            import_sh.write(f"terraform import -var-file=kestra.tfvars 'kestra_flow.flows[\"{ns.id}|{flow.id}\"]' {ns.id}/{flow.id}\n")
        tfvars.write("  ]\n")
    tfvars.write("}\n\n")

    # write to console
    typer.echo(f"\n\n{'*' * 10} kestra.tfvars {'*' * 10}\n\n")
    typer.echo(tfvars.getvalue())
    # write to file
    with open(output_dir / "kestra.tfvars", "w") as f:
        f.write(tfvars.getvalue())

    # write to console
    typer.echo(f"\n\n{'*' * 10} import.sh {'*' * 10}\n\n")
    typer.echo(import_sh.getvalue())
    # write to file
    with open(output_dir / "import.sh", "w") as f:
        f.write(import_sh.getvalue())


if __name__ == "__main__":
    app()
