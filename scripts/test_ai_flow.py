import argparse

from local_test_client import login, request

CASES = {
    "disk_full": ("erp-linux-01", "Check disk capacity", "100%"),
    "cpu_high": ("erp-linux-01", "Check CPU utilization", "94.7 us"),
    "memory_leak": ("erp-linux-01", "Check memory pressure", "1988"),
    "redis_down": ("erp-redis-01", "Check Redis service", "redis-server.service"),
    "oracle_slow": ("erp-oracle-01", "Check Oracle processes", "ora_p003_ERP"),
    "kafka_lag": ("crm-kafka-01", "Check Kafka consumer lag", "total_lag=29830"),
    "network_timeout": ("erp-linux-01", "Check network connectivity", "Network is unreachable"),
    "nginx_down": ("crm-nginx-01", "Check Nginx service", "nginx.service"),
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run AI to Tool Registry to local adapter flow")
    parser.add_argument("profile", choices=CASES)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/api/v1")
    parser.add_argument("--email", default="operator@aiops.example.com")
    parser.add_argument("--password", default="Operator@123456")
    args = parser.parse_args()
    hostname, prompt, expected = CASES[args.profile]
    token = login(args.base_url, args.email, args.password)
    servers = request(args.base_url, "/inventory/servers?page=1&page_size=200", token=token)
    server = next((item for item in servers if item["hostname"] == hostname), None)
    if server is None:
        raise RuntimeError(f"Development target not found: {hostname}")
    request(args.base_url, f"/development/servers/{server['id']}/profile", method="PUT",
            token=token, payload={"profile": args.profile})
    result = request(args.base_url, "/ai/chat", method="POST", token=token, payload={
        "server_id": server["id"], "system_id": server["system_id"], "message": prompt,
    })
    events = result.get("executed_tools", [])
    if not events:
        raise RuntimeError("FAIL: AI did not request a registered backend tool")
    output = str(events[0].get("result", {}).get("stdout", ""))
    if expected not in output:
        raise RuntimeError(f"FAIL: expected snapshot marker {expected!r} was not returned")
    if result.get("confidence", {}).get("reason") == "":
        raise RuntimeError("FAIL: AI response has no confidence reason")
    print(f"PASS {args.profile}: {events[0]['tool']} -> gateway -> local adapter -> AI summary")
    print(result["answer"])


if __name__ == "__main__":
    main()
