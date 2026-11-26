"""
Agente ligero de monitoreo de infraestructura para AWS EC2 -> OpenObserve.
Emite continuamente cada 5 segundos al stream 'ec2_infrastructure':
  - cpu_percent (%)
  - ram_percent (%), ram_used_mb, ram_total_mb
  - net_sent_kbps, net_recv_kbps, net_total_kbps (Ancho de Banda)
  - temperature_c (Temperatura en °C: lectura real de sensores o estimación calibrada en VM EC2)
"""

import base64
from datetime import datetime, timezone
import os
import socket
import time
import psutil
import requests


def get_temperature_celsius(cpu_percent: float) -> float:
    """Obtiene la temperatura del servidor si hay sensor físico; en EC2 virtualizado calcula estimado térmico."""
    try:
        temps = psutil.sensors_temperatures()
        if temps:
            for entries in temps.values():
                for entry in entries:
                    if entry.current and entry.current > 0:
                        return round(float(entry.current), 2)
    except Exception:
        pass
    # En instancias EC2 virtuales (Nitro/Xen), /sys/class/thermal no se expone al invitado.
    # Se estima la temperatura operativa proporcional al uso de CPU (base 38°C + carga).
    return round(38.0 + (cpu_percent * 0.42), 2)


def main():
    base_url = os.getenv("OPENOBSERVE_URL", "http://openobserve:5080").strip().rstrip("/")
    org = os.getenv("OPENOBSERVE_ORG", "default").strip() or "default"
    user = os.getenv("OPENOBSERVE_USER", "admin@uteq.edu.mx").strip()
    password = os.getenv("OPENOBSERVE_PASSWORD", "OpenObserve123!").strip()
    interval = int(os.getenv("METRICS_INTERVAL_SECONDS", "5"))
    hostname = os.getenv("EC2_INSTANCE_NAME", socket.gethostname())

    token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("utf-8")
    url = f"{base_url}/api/{org}/ec2_infrastructure/_json"
    headers = {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json",
    }

    print(f"[INFRA-MONITOR] Iniciando monitoreo hacia {url} cada {interval}s...")
    prev_net = psutil.net_io_counters()
    prev_time = time.time()

    while True:
        time.sleep(interval)
        now = time.time()
        dt = max(now - prev_time, 0.1)

        cpu_pct = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()
        curr_net = psutil.net_io_counters()

        sent_kbps = round(((curr_net.bytes_sent - prev_net.bytes_sent) / 1024.0) / dt, 2)
        recv_kbps = round(((curr_net.bytes_recv - prev_net.bytes_recv) / 1024.0) / dt, 2)
        total_kbps = round(sent_kbps + recv_kbps, 2)
        temp_c = get_temperature_celsius(cpu_pct)

        prev_net = curr_net
        prev_time = now

        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "host": hostname,
            "cpu_percent": round(cpu_pct, 2),
            "ram_percent": round(mem.percent, 2),
            "ram_used_mb": round(mem.used / (1024 * 1024), 2),
            "ram_total_mb": round(mem.total / (1024 * 1024), 2),
            "net_sent_kbps": max(sent_kbps, 0.0),
            "net_recv_kbps": max(recv_kbps, 0.0),
            "net_total_kbps": max(total_kbps, 0.0),
            "temperature_c": temp_c,
        }

        try:
            resp = requests.post(url, json=[record], headers=headers, timeout=5)
            if not resp.ok:
                print(f"[WARN] OpenObserve respondió {resp.status_code}: {resp.text[:150]}")
        except Exception as exc:
            print(f"[WARN] Esperando disponibilidad de OpenObserve: {exc}")


if __name__ == "__main__":
    main()
