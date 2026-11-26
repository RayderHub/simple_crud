"""
Suite de Pruebas Integrales E2E (Backend + Frontend) con Pytest y Playwright.
RF-01: Valida endpoints del servidor, autenticación (positiva y negativa),
y ciclo completo CRUD de usuarios en navegador contra Supabase.
"""

import os
import time
import requests
import pytest
from playwright.sync_api import Page, expect

APP_URL = os.getenv("APP_URL", "http://127.0.0.1:5000").rstrip("/")
ADMIN_EMAIL = os.getenv("TEST_ADMIN_EMAIL", "admin@uteq.edu.mx")
ADMIN_PASSWORD = os.getenv("TEST_ADMIN_PASSWORD", "admin123")


# ==============================================================================
# PRUEBAS DE BACKEND (API & SEGURIDAD DE RUTAS)
# ==============================================================================

def test_backend_health_endpoint():
    """Verifica que el endpoint /health responda HTTP 200 con estado ok."""
    resp = requests.get(f"{APP_URL}/health", timeout=10)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["supabase_configured"] is True


def test_backend_proteccion_rutas_sin_sesion():
    """Verifica que /usuarios y /api/usuarios bloqueen acceso sin autenticación."""
    r_web = requests.get(f"{APP_URL}/usuarios", allow_redirects=False, timeout=10)
    assert r_web.status_code == 302
    assert "/login" in r_web.headers.get("Location", "")

    r_api = requests.get(f"{APP_URL}/api/usuarios", allow_redirects=False, timeout=10)
    assert r_api.status_code == 302
    assert "/login" in r_api.headers.get("Location", "")


def test_backend_login_y_api_usuarios():
    """Verifica inicio de sesión por HTTP y lectura del endpoint JSON /api/usuarios."""
    s = requests.Session()
    r_login = s.post(
        f"{APP_URL}/login",
        data={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        allow_redirects=True,
        timeout=15,
    )
    assert r_login.status_code == 200
    assert "Administración de Usuarios" in r_login.text

    r_api = s.get(f"{APP_URL}/api/usuarios", timeout=15)
    assert r_api.status_code == 200
    payload = r_api.json()
    assert payload["ok"] is True
    assert payload["total"] >= 1
    assert any(u["email"] == ADMIN_EMAIL for u in payload["usuarios"])


# ==============================================================================
# PRUEBAS DE FRONTEND E2E (PLAYWRIGHT)
# ==============================================================================

def test_frontend_renderizado_login(page: Page):
    """Verifica que la pantalla de Login cargue correctamente con sus controles."""
    page.goto(f"{APP_URL}/login", wait_until="domcontentloaded")
    expect(page.get_by_role("heading", name="Iniciar Sesión")).to_be_visible()
    expect(page.get_by_test_id("input-email")).to_be_visible()
    expect(page.get_by_test_id("input-password")).to_be_visible()
    expect(page.get_by_test_id("btn-login")).to_be_visible()


def test_frontend_login_negativo_credenciales_invalidas(page: Page):
    """Prueba negativa: credenciales incorrectas deben mostrar alerta y bloquear el acceso."""
    page.goto(f"{APP_URL}/login", wait_until="domcontentloaded")
    page.get_by_test_id("input-email").fill("noexiste@uteq.edu.mx")
    page.get_by_test_id("input-password").fill("clave_erronea_999")
    page.get_by_test_id("btn-login").click()

    expect(page).to_have_url(f"{APP_URL}/login")
    expect(page.get_by_test_id("flash-messages")).to_contain_text("Credenciales inválidas")


def test_frontend_flujo_completo_crud_y_logout(page: Page):
    """Flujo E2E completo: Login -> Crear -> Buscar -> Editar -> Eliminar -> Logout."""
    unique_suffix = int(time.time())
    test_email = f"e2e.user.{unique_suffix}@uteq.edu.mx"
    test_name = f"Usuario E2E {unique_suffix}"
    edited_name = f"Usuario Editado {unique_suffix}"

    # 1. Login exitoso
    page.goto(f"{APP_URL}/login", wait_until="domcontentloaded")
    page.get_by_test_id("input-email").fill(ADMIN_EMAIL)
    page.get_by_test_id("input-password").fill(ADMIN_PASSWORD)
    page.get_by_test_id("btn-login").click()

    expect(page).to_have_url(f"{APP_URL}/usuarios")
    expect(page.get_by_test_id("tabla-usuarios")).to_be_visible()
    expect(page.get_by_test_id("kpi-total")).to_be_visible()

    # 2. CREATE: Crear usuario mediante el modal
    page.get_by_test_id("btn-nuevo-usuario").click()
    expect(page.get_by_test_id("modal-crear")).to_be_visible()
    page.get_by_test_id("create-nombre").fill(test_name)
    page.get_by_test_id("create-email").fill(test_email)
    page.get_by_test_id("create-password").fill("Password123!")
    page.get_by_test_id("create-rol").select_option("Usuario")
    page.get_by_test_id("btn-guardar-crear").click()

    expect(page.get_by_test_id("flash-messages")).to_contain_text("creado correctamente")

    # 3. READ / SEARCH: Buscar el usuario recién creado
    page.get_by_test_id("input-buscar").fill(test_email)
    page.get_by_test_id("btn-buscar").click()
    fila = page.locator("tbody tr", has_text=test_email)
    expect(fila).to_be_visible()
    expect(fila).to_contain_text(test_name)

    # 4. UPDATE: Editar nombre y rol del usuario
    fila.get_by_role("button", name="Editar").click()
    expect(page.get_by_test_id("modal-editar")).to_be_visible()
    page.get_by_test_id("edit-nombre").fill(edited_name)
    page.get_by_test_id("edit-rol").select_option("Editor")
    page.get_by_test_id("btn-guardar-editar").click()

    expect(page.get_by_test_id("flash-messages")).to_contain_text("actualizado correctamente")

    # Verificar el cambio en la tabla
    page.get_by_test_id("input-buscar").fill(test_email)
    page.get_by_test_id("btn-buscar").click()
    fila_editada = page.locator("tbody tr", has_text=test_email)
    expect(fila_editada).to_contain_text(edited_name)
    expect(fila_editada).to_contain_text("Editor")

    # 5. DELETE: Eliminar usuario aceptando el diálogo de confirmación
    page.once("dialog", lambda dialog: dialog.accept())
    fila_editada.get_by_role("button", name="Eliminar").click()
    expect(page.get_by_test_id("flash-messages")).to_contain_text("eliminado correctamente")

    # 6. LOGOUT y verificación de bloqueo de sesión
    page.get_by_test_id("btn-logout").click()
    expect(page).to_have_url(f"{APP_URL}/login")
    page.goto(f"{APP_URL}/usuarios", wait_until="domcontentloaded")
    expect(page).to_have_url(f"{APP_URL}/login")
