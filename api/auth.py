"""注册、登录、退出和当前用户。"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from services.auth_service import AuthService, AuthValidationError, DuplicateUsernameError

router = APIRouter(prefix="/api/auth", tags=["认证"])


class RegisterBody(BaseModel):
    username: str
    password: str
    display_name: str


class LoginBody(BaseModel):
    username: str
    password: str


def require_login(request: Request) -> dict:
    user = AuthService().current_user(request.session)
    if not user:
        raise HTTPException(status_code=401, detail="请先登录")
    return user


@router.post("/register")
async def register(body: RegisterBody, request: Request):
    try:
        user = AuthService().register(body.username, body.password, body.display_name)
    except DuplicateUsernameError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except AuthValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    request.session["user_id"] = str(user["id"])
    return {"username": user["username"], "display_name": user["display_name"]}


@router.post("/login")
async def login(body: LoginBody, request: Request):
    user = AuthService().login(body.username, body.password, request.session)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    return {"username": user["username"], "display_name": user["display_name"]}


@router.post("/logout")
async def logout(request: Request):
    AuthService().logout(request.session)
    return {"authenticated": False}


@router.get("/me")
async def me(request: Request):
    user = AuthService().current_user(request.session)
    if not user:
        return {"authenticated": False}
    return {
        "authenticated": True,
        "username": user["username"],
        "display_name": user["display_name"],
    }
