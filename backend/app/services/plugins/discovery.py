import json
import re
from hashlib import sha256
from typing import Any, Protocol

DEPLOYED_MARKERS = {
    "nginx", "redis", "oracle", "kafka", "rabbitmq", "mysql", "postgresql", "postgres",
    "elasticsearch", "mongodb", "tomcat", "httpd", "apache", "erp", "crm", "mes",
    "api", "worker", "internal",
}
SYSTEM_SERVICES = {
    "systemd", "systemd-journald", "cron", "dbus", "networkd", "resolved", "udev",
    "polkit", "rsyslog", "sshd", "ssh", "winrm", "svchost",
}
PORT_SERVICES = {
    80: "http", 443: "https", 1521: "oracle", 3306: "mysql", 5432: "postgresql",
    5672: "rabbitmq", 6379: "redis", 8080: "application", 8443: "application-https",
    9092: "kafka", 9200: "elasticsearch",
}


class DiscoveryParserPlugin(Protocol):
    name: str

    def enrich(self, node: dict[str, Any], evidence: dict[str, str],
               include_system_services: bool) -> None: ...


class HostDiscoveryPlugin:
    name = "host"

    def enrich(self, node: dict[str, Any], evidence: dict[str, str],
               include_system_services: bool) -> None:
        data = node["data"]
        hardware = evidence.get("hardware_information", "")
        linux_cores = re.search(r"^\s*(\d+)\s*$", hardware, re.M)
        windows_cores = re.search(r"NumberOfLogicalProcessors\s*:?\s*(\d+)", hardware)
        windows_capacity = re.search(r"^(\d+)\s+(\d+)\s*$", hardware, re.M)
        core_match = linux_cores or windows_cores or windows_capacity
        data["cpu_cores"] = int(core_match.group(1)) if core_match else None
        linux_memory = re.search(r"MemTotal:\s*(\d+)\s*kB", hardware, re.I)
        windows_memory = re.search(r"TotalPhysicalMemory\s*:?\s*(\d+)", hardware)
        data["ram_bytes"] = int(linux_memory.group(1)) * 1024 if linux_memory else int(windows_memory.group(1)) if windows_memory else int(windows_capacity.group(2)) if windows_capacity else None
        linux_disks = [(name, int(size)) for name, size in re.findall(r"^(\S+)\s+(\d+)\s+disk$", hardware, re.M)]
        windows_disks = [(name, int(size)) for name, size in re.findall(r"(\\\\\.\\PHYSICALDRIVE\d+)\s+(\d+)", hardware, re.I)]
        disks = linux_disks or windows_disks
        data["disks"] = [{"source": name, "size_bytes": size} for name, size in disks]
        data["disk_count"] = len(disks)
        data["disk_total_bytes"] = sum(size for _, size in disks)
        filesystems = evidence.get("list_filesystems", "")
        try:
            data["filesystems"] = json.loads(filesystems).get("filesystems", [])
        except json.JSONDecodeError:
            data["filesystems"] = []
        network = evidence.get("check_network", "")
        data["interfaces"] = sorted(set(re.findall(r"inet\s+([0-9.]+/\d+)", network)))
        ports = {int(port) for port in re.findall(r"(?:LISTEN\s+\S+\s+\S+\s+\S+:)(\d+)", network)}
        ports.update(int(port) for port in re.findall(r"\b0\.0\.0\.0:(\d+)\b", network))
        data["listening_ports"] = [
            {"port": port, "protocol": "tcp", "service": PORT_SERVICES.get(port, "unknown")}
            for port in sorted(ports)
        ]
        # Listening sockets are the remotely reachable/open-port evidence available
        # through the governed host collector; network scanners can enrich this later.
        data["open_ports"] = list(data["listening_ports"])
        candidates: set[str] = set()
        for line in (evidence.get("list_services", "") + "\n" +
                     evidence.get("list_deployed_applications", "")).splitlines():
            lowered = line.lower()
            parts = re.split(r"\s+", lowered.strip()) if line.strip() else []
            token = (parts[1] if parts and parts[0] == "running" and len(parts) > 1 else
                     parts[0] if parts else "").removesuffix(".service")
            deployed = any(marker in lowered for marker in DEPLOYED_MARKERS)
            system = any(token.startswith(marker) for marker in SYSTEM_SERVICES)
            if token and (deployed or (include_system_services and system)):
                candidates.add(token)
        candidates.add(str(data.get("role", "")))
        data["services"] = sorted(value for value in candidates if value)
        data["installed_applications"] = list(data["services"])


class DockerDiscoveryPlugin:
    name = "docker"

    def enrich(self, node: dict[str, Any], evidence: dict[str, str],
               include_system_services: bool) -> None:
        del include_system_services
        containers, networks, compose = [], [], []
        for line in evidence.get("docker_inventory", evidence.get("docker_ps", "")).splitlines():
            if line.count("|") >= 5:
                container_id, image, name, network, ports, status = line.split("|", 5)
                containers.append({"id": container_id, "name": name, "image": image,
                                   "ports": ports, "network": network, "status": status})
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            values = value if isinstance(value, list) else [value]
            for item in values:
                if "Image" in item:
                    containers.append({"name": item.get("Names"), "image": item.get("Image"),
                                       "ports": item.get("Ports", ""),
                                       "network": item.get("Networks", ""),
                                       "status": item.get("Status", "")})
                elif "Driver" in item:
                    networks.append({"name": item.get("Name"), "driver": item.get("Driver")})
                elif "ConfigFiles" in item:
                    compose.append({"name": item.get("Name"), "status": item.get("Status"),
                                    "config_files": item.get("ConfigFiles")})
        node["data"].update({"docker": bool(containers), "containers": containers,
                             "docker_networks": networks, "docker_compose": compose})


class KubernetesDiscoveryPlugin:
    name = "kubernetes"

    def enrich(self, node: dict[str, Any], evidence: dict[str, str],
               include_system_services: bool) -> None:
        del include_system_services
        resources = []
        for line in evidence.get("kubernetes_inventory", evidence.get("kubectl_get_pods", "")).splitlines():
            if not line.strip() or line.startswith(("NAME", "NAMESPACE")):
                continue
            parts = line.split()
            name_index = 1 if "/" in " ".join(parts[:2]) else 0
            if len(parts) > name_index:
                name = parts[name_index]
                resources.append({"name": name, "kind": name.split(".")[0].split("/")[0],
                                  "namespace": parts[0] if name_index else "default"})
        node["data"].update({"kubernetes": bool(resources), "kubernetes_resources": resources,
                             "pods": [item for item in resources if "pod" in item["kind"]]})


def build_dependency_edges(nodes: list[dict[str, Any]], evidence_by_server: dict[str, dict[str, str]]) -> list[dict[str, Any]]:
    by_ip = {node["data"]["ip"]: node for node in nodes}
    edges: dict[tuple[str, str, int], dict[str, Any]] = {}
    for source in nodes:
        connections = evidence_by_server.get(source["id"], {}).get("list_connections", "")
        for line in connections.splitlines():
            if not re.search(r"ESTAB|Established", line, re.I):
                continue
            addresses = re.findall(r"(\d+\.\d+\.\d+\.\d+):(\d+)", line)
            if len(addresses) < 2:
                continue
            (local_ip, _), (remote_ip, remote_port) = addresses[:2]
            target = by_ip.get(remote_ip)
            if target and target["id"] != source["id"]:
                _add_edge(edges, source, target, int(remote_port), 0.94,
                          "Observed established TCP connection")
        role = str(source["data"].get("role", "")).lower()
        if role in {"application", "api", "worker", "iis", "nginx"}:
            for target in nodes:
                target_role = str(target["data"].get("role", "")).lower()
                if target["id"] != source["id"] and target["data"]["system_id"] == source["data"]["system_id"]:
                    port = next((port for port, service in PORT_SERVICES.items()
                                 if target_role in service), None)
                    if port:
                        _add_edge(edges, source, target, port, 0.68,
                                  "Inferred from application and deployed data-service roles")
    return list(edges.values())


def _add_edge(edges: dict, source: dict, target: dict, port: int, confidence: float,
              reason: str) -> None:
    key = (source["id"], target["id"], port)
    if key in edges and edges[key]["confidence"] >= confidence:
        return
    service = PORT_SERVICES.get(port, target["data"].get("role", "unknown"))
    digest = sha256("|".join(map(str, key)).encode()).hexdigest()[:16]
    edges[key] = {"id": f"dependency-{digest}", "source": source["id"],
                  "target": target["id"], "port": port, "protocol": "tcp",
                  "connection_type": "observed" if confidence > 0.9 else "inferred",
                  "service_name": service, "confidence": confidence, "reason": reason}


DISCOVERY_PLUGINS: tuple[DiscoveryParserPlugin, ...] = (
    HostDiscoveryPlugin(), DockerDiscoveryPlugin(), KubernetesDiscoveryPlugin()
)
