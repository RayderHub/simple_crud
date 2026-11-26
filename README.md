# Simple CRUD de Usuarios — CI/CD, Playwright y Observabilidad con OpenObserve

Proyecto Parcial 2: Aplicación web Flask + Supabase con pruebas automatizadas E2E (Playwright + Pytest), despliegue continuo condicionado en AWS EC2 mediante GitHub Actions y observabilidad completa (Logs, Métricas, Trazas OTLP e Infraestructura) en OpenObserve.

## Arquitectura
- **Aplicación Web (`app`):** Python Flask + Gunicorn + Supabase (puerto `5000`), instrumentada con **OpenTelemetry (OTLP/HTTP)**.
- **Observabilidad (`openobserve`):** OpenObserve (puerto `5080`) recibiendo:
  - `cicd_pipeline`: Logs de ejecuciones de pruebas y despliegues desde GitHub Actions.
  - `app_logs`: Logs estructurados de peticiones HTTP y excepciones.
  - `default` (Traces & Metrics OTLP): Trazas distribuidas y métricas de latencia/errores por endpoint.
  - `ec2_infrastructure`: Métricas de CPU, RAM, Ancho de Banda y Temperatura del servidor EC2 (`infra_monitor.py`).

## Secrets requeridos en GitHub Actions
Configurar en **Settings → Secrets and variables → Actions**:
- `SUPABASE_URL`
- `SUPABASE_KEY`
- `FLASK_SECRET_KEY`
- `EC2_HOST` (IP pública de tu instancia AWS EC2)
- `EC2_USER` (por ejemplo `ubuntu` o `ec2-user`)
- `EC2_SSH_KEY` (contenido completo de tu archivo `.pem`)
- `OPENOBSERVE_URL` (ejemplo: `http://TU_IP_EC2:5080`)
- `OPENOBSERVE_USER` (ejemplo: `admin@uteq.edu.mx`)
- `OPENOBSERVE_PASSWORD` (ejemplo: `OpenObserve123!`)
