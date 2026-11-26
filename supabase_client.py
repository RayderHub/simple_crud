import hashlib
import os
from typing import Any, Dict, List, Optional
import requests
from dotenv import load_dotenv

load_dotenv()


def hash_password(password: str) -> str:
    """Genera el hash SHA-256 en hexadecimal de una contraseña."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


class SupabaseError(Exception):
    """Error al comunicarse con la API REST de Supabase."""


class SupabaseClient:
    """Cliente ligero para consumir la tabla 'usuarios' en Supabase vía PostgREST."""

    def __init__(self) -> None:
        self.reload_config()

    def reload_config(self) -> None:
        load_dotenv(override=True)
        self.url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
        self.key = os.getenv("SUPABASE_KEY", "").strip()

    @property
    def is_configured(self) -> bool:
        return bool(
            self.url
            and self.key
            and "TU-PROYECTO" not in self.url
            and "TU_CLAVE" not in self.key
        )

    @property
    def _endpoint(self) -> str:
        return f"{self.url}/rest/v1/usuarios"

    def _headers(self, prefer: Optional[str] = None) -> Dict[str, str]:
        headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer
        return headers

    def _request(self, method: str, params: Optional[Dict[str, str]] = None,
                 json_data: Optional[Dict[str, Any]] = None,
                 prefer: Optional[str] = None) -> Any:
        self.reload_config()
        if not self.is_configured:
            raise SupabaseError(
                "Faltan las credenciales de Supabase. Configura SUPABASE_URL y SUPABASE_KEY en el archivo .env."
            )
        try:
            resp = requests.request(
                method=method,
                url=self._endpoint,
                headers=self._headers(prefer=prefer),
                params=params,
                json=json_data,
                timeout=15,
            )
        except requests.RequestException as exc:
            raise SupabaseError(f"Error de conexión con Supabase: {exc}") from exc

        if not resp.ok:
            try:
                detail = resp.json()
                msg = detail.get("message") or detail.get("error") or str(detail)
            except ValueError:
                msg = resp.text or f"HTTP {resp.status_code}"
            raise SupabaseError(f"Supabase respondió {resp.status_code}: {msg}")

        if resp.status_code == 204 or not resp.text:
            return None
        return resp.json()

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        data = self._request(
            "GET",
            params={"email": f"eq.{email.strip().lower()}", "select": "*"},
        )
        return data[0] if data else None

    def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        data = self._request(
            "GET",
            params={"id": f"eq.{user_id}", "select": "id,nombre,email,rol,activo,creado_en"},
        )
        return data[0] if data else None

    def list_users(self, search: str = "") -> List[Dict[str, Any]]:
        params: Dict[str, str] = {
            "select": "id,nombre,email,rol,activo,creado_en",
            "order": "id.asc",
        }
        if search:
            term = search.strip()
            params["or"] = f"(nombre.ilike.*{term}*,email.ilike.*{term}*,rol.ilike.*{term}*)"
        return self._request("GET", params=params) or []

    def create_user(self, nombre: str, email: str, password: str, rol: str, activo: bool = True) -> Dict[str, Any]:
        payload = {
            "nombre": nombre.strip(),
            "email": email.strip().lower(),
            "password_hash": hash_password(password),
            "rol": rol,
            "activo": activo,
        }
        data = self._request("POST", json_data=payload, prefer="return=representation")
        return data[0] if data else payload

    def update_user(
        self,
        user_id: int,
        nombre: str,
        email: str,
        rol: str,
        activo: bool,
        password: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        payload: Dict[str, Any] = {
            "nombre": nombre.strip(),
            "email": email.strip().lower(),
            "rol": rol,
            "activo": activo,
        }
        if password:
            payload["password_hash"] = hash_password(password)
        data = self._request(
            "PATCH",
            params={"id": f"eq.{user_id}"},
            json_data=payload,
            prefer="return=representation",
        )
        return data[0] if data else None

    def delete_user(self, user_id: int) -> None:
        self._request("DELETE", params={"id": f"eq.{user_id}"})
