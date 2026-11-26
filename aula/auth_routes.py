import hmac
import sqlite3
import smtplib
from email.message import EmailMessage

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator

from aula import auth
from aula.config import CORS_ORIGINS, SESSION_DAYS, EXPOSE_RESET_LINKS, SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM, SMTP_TLS, RESET_BASE_URL
from aula.db import session
from aula.repo import user_by_email
from aula.serialize import present_user
from aula.util import valid_email

router = APIRouter(prefix="/api/auth", tags=["authentification"])
SESSION_COOKIE = "campusia_session"
COOKIE_SAMESITE = "lax"


class LoginPayload(BaseModel):
    email: str = Field(min_length=3, max_length=160)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        email = value.strip().lower()
        if not valid_email(email):
            raise ValueError("Adresse e-mail invalide.")
        return email


class RegisterPayload(LoginPayload):
    name: str = Field(min_length=2, max_length=80)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        name = value.strip()
        if len(name) < 2:
            raise ValueError("Indiquez votre nom complet.")
        return name

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        if len(value) < 10:
            raise ValueError("Le mot de passe doit contenir au moins 10 caractères.")
        if value.isspace():
            raise ValueError("Le mot de passe ne peut pas contenir uniquement des espaces.")
        return value


class PasswordPayload(BaseModel):
    model_config = {"extra": "forbid"}
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=10, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        if value.isspace():
            raise ValueError("Le nouveau mot de passe ne peut pas contenir uniquement des espaces.")
        return value


class ForgotPasswordPayload(BaseModel):
    model_config = {"extra": "forbid"}
    email: str = Field(min_length=3, max_length=160)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not valid_email(value):
            raise ValueError("Adresse e-mail invalide.")
        return value


class ResetPasswordPayload(BaseModel):
    model_config = {"extra": "forbid"}
    token: str = Field(min_length=20, max_length=200)
    new_password: str = Field(min_length=10, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_reset_password(cls, value: str) -> str:
        if value.isspace():
            raise ValueError("Le nouveau mot de passe ne peut pas contenir uniquement des espaces.")
        return value


def _check_same_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin:
        expected = str(request.base_url).rstrip("/")
        normalized = origin.rstrip("/")
        if normalized != expected and normalized not in CORS_ORIGINS:
            raise HTTPException(status_code=403, detail="Origine de requête non autorisée.")
    elif request.headers.get("sec-fetch-site", "").lower() == "cross-site":
        raise HTTPException(status_code=403, detail="Origine de requête non autorisée.")


def _set_session_cookie(response: Response, request: Request, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=SESSION_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite=COOKIE_SAMESITE,
        path="/",
    )


def _clear_session_cookie(response: Response, request: Request) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite=COOKIE_SAMESITE,
        path="/",
    )


def _session_response(response: Response, request: Request, result: dict) -> dict:
    _set_session_cookie(response, request, result["token"])
    return {"authenticated": True, "user": present_user(result["user"]), "csrf_token": result["csrf"]}


def current_auth(request: Request) -> dict:
    token = request.cookies.get(SESSION_COOKIE)
    with session() as conn:
        user = auth.resolve_session(conn, token)
    if not user:
        raise HTTPException(status_code=401, detail="Authentification requise.")
    return {"user": user, "csrf": user["csrf"], "token": token}


def _require_csrf(request: Request, context: dict) -> None:
    _check_same_origin(request)
    supplied = request.headers.get("x-csrf-token", "")
    if not supplied or not hmac.compare_digest(supplied, context["csrf"]):
        raise HTTPException(status_code=403, detail="Jeton de sécurité invalide ou manquant.")


@router.post("/register", status_code=201)
def register(payload: RegisterPayload, request: Request, response: Response):
    _check_same_origin(request)
    try:
        with session() as conn:
            if user_by_email(conn, payload.email):
                raise HTTPException(status_code=409, detail={"field": "email", "message": "Cette adresse e-mail est déjà utilisée."})
            user = auth.create_user(
                conn,
                email=payload.email,
                password=payload.password,
                name=payload.name,
                role="student",
            )
            result, _ = auth.open_session(conn, user["id"])
    except sqlite3.IntegrityError as exc:
        if "users.email" in str(exc).lower() or "unique constraint failed: users.email" in str(exc).lower():
            raise HTTPException(status_code=409, detail={"field": "email", "message": "Cette adresse e-mail est déjà utilisée."}) from None
        raise
    return _session_response(response, request, result)


@router.post("/login")
def login(payload: LoginPayload, request: Request, response: Response):
    _check_same_origin(request)
    with session() as conn:
        result, error = auth.authenticate(conn, payload.email, payload.password)
    if error:
        if error.startswith("Trop de tentatives"):
            raise HTTPException(status_code=429, detail=error)
        raise HTTPException(status_code=401, detail="Adresse e-mail ou mot de passe incorrect.")
    return _session_response(response, request, result)


@router.get("/me")
def me(context: dict = Depends(current_auth)):
    return {
        "authenticated": True,
        "user": present_user(context["user"]),
        "csrf_token": context["csrf"],
    }


@router.get("/session")
def session_status(request: Request):
    try:
        context = current_auth(request)
    except HTTPException as exc:
        if exc.status_code == 401:
            return {"authenticated": False}
        raise
    return {
        "authenticated": True,
        "user": present_user(context["user"]),
        "csrf_token": context["csrf"],
    }


@router.post("/logout")
def logout(request: Request, response: Response, context: dict = Depends(current_auth)):
    _require_csrf(request, context)
    with session() as conn:
        auth.destroy_session(conn, context["token"])
    _clear_session_cookie(response, request)
    return {"authenticated": False}


@router.post("/password")
def change_password(payload: PasswordPayload, request: Request, context: dict = Depends(current_auth)):
    _require_csrf(request, context)
    try:
        with session() as conn:
            auth.change_password(
                conn,
                context["user"]["id"],
                payload.current_password,
                payload.new_password,
            )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return {"changed": True}


def _send_reset_email(recipient: str, reset_link: str) -> None:
    if not SMTP_HOST or not SMTP_FROM:
        raise RuntimeError("SMTP non configuré")
    message = EmailMessage()
    message["Subject"] = "Réinitialisation de votre mot de passe MED_ETUD"
    message["From"] = SMTP_FROM
    message["To"] = recipient
    message.set_content(
        "Vous avez demandé la réinitialisation de votre mot de passe MED_ETUD.\n\n"
        f"Utilisez ce lien: {reset_link}\n\n"
        "Ce lien expire dans deux heures. Si vous n'avez pas demandé ce lien, ignorez cet e-mail."
    )
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
        if SMTP_TLS:
            server.starttls()
        if SMTP_USER:
            server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(message)


@router.post("/forgot-password")
def forgot_password(payload: ForgotPasswordPayload, request: Request):
    _check_same_origin(request)
    response = {"sent": True}
    with session() as conn:
        user = user_by_email(conn, payload.email)
        if user and not user["suspended"]:
            token = auth.issue_email_token(conn, user["id"], "reset", hours=2)
            reset_link = f"{RESET_BASE_URL}/?reset={token}" if RESET_BASE_URL else None
            if not reset_link:
                return response
            try:
                _send_reset_email(user["email"], reset_link)
            except (smtplib.SMTPException, OSError, RuntimeError):
                if not EXPOSE_RESET_LINKS:
                    return response
                response["reset_link"] = reset_link
    return response


@router.post("/reset-password")
def reset_password(payload: ResetPasswordPayload, request: Request):
    _check_same_origin(request)
    try:
        with session() as conn:
            auth.reset_password(conn, payload.token, payload.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return {"changed": True}
