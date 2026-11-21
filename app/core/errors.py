"""统一业务错误类型与全局错误处理。

错误分类遵循 6.2 全局约定第 10 节：
未登录跳转登录并保留目标页；无角色权限 403；跨校对象 404；
状态冲突与输入错误给出可执行的下一步；未处理异常只显示请求标识。
"""

from __future__ import annotations

import logging
import uuid

from flask import Flask, redirect, render_template, request, url_for

logger = logging.getLogger("qinghe.errors")


class AppError(Exception):
    """业务错误基类：带错误码、用户可读消息和 HTTP 状态。"""

    status_code = 400
    title = "请求无法处理"

    def __init__(self, message: str, *, title: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        if title:
            self.title = title


class InputError(AppError):
    """输入错误：表单原位显示字段错误。"""

    status_code = 400
    title = "输入有误"

    def __init__(self, message: str, *, field_errors: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.field_errors = field_errors or {}


class LoginRequiredError(AppError):
    """未登录：跳转登录并保留目标页。"""

    status_code = 401
    title = "请先登录"


class PermissionDeniedError(AppError):
    """角色越权：返回 403。"""

    status_code = 403
    title = "没有访问权限"


class NotFoundError(AppError):
    """对象不存在或不属于本校：返回 404，不泄露对象存在与否。"""

    status_code = 404
    title = "没有找到对应内容"


class ConflictError(AppError):
    """状态冲突：解释当前状态和下一步。"""

    status_code = 409
    title = "当前状态无法执行该操作"


def register_error_handlers(app: Flask) -> None:
    """注册全局错误处理；错误页必须说明原因和下一步。"""

    def _render_error(
        status: int,
        title: str,
        reason: str,
        next_step: str,
        request_id: str | None = None,
    ):
        if _wants_json():
            payload: dict = {
                "status": status,
                "title": title,
                "message": reason,
                "next_step": next_step,
            }
            if request_id:
                payload["request_id"] = request_id
            return payload, status
        return (
            render_template(
                "errors/error.html",
                status=status,
                title=title,
                reason=reason,
                next_step=next_step,
                request_id=request_id,
            ),
            status,
        )

    def _wants_json() -> bool:
        # 只有明确请求 JSON 的客户端才返回 JSON 错误；浏览器一律得到中文错误页
        return request.accept_mimetypes.best == "application/json"

    @app.errorhandler(AppError)
    def handle_app_error(err: AppError):
        if isinstance(err, LoginRequiredError):
            target = request.full_path if request.query_string else request.path
            return redirect(url_for("auth.login", next=target))
        return _render_error(
            err.status_code, err.title, err.message, _default_next_step(err.status_code)
        )

    @app.errorhandler(403)
    def handle_403(_err):
        return _render_error(
            403,
            "没有访问权限",
            "当前账号的角色无法访问该页面。",
            "返回首页，或使用有对应权限的账号登录。",
        )

    @app.errorhandler(404)
    def handle_404(_err):
        return _render_error(
            404,
            "没有找到页面",
            "地址可能输入有误，或该内容不属于你所在的学校。",
            "返回首页重新查找。",
        )

    @app.errorhandler(500)
    def handle_500(err):
        request_id = uuid.uuid4().hex[:12]
        logger.exception("未处理异常 request_id=%s path=%s", request_id, request.path)
        return _render_error(
            500,
            "服务暂时不可用",
            "系统遇到了意外错误，请稍后重试。",
            "刷新重试；若仍然失败，请联系平台管理员并提供页面上的请求标识。",
            request_id=request_id,
        )

    @app.errorhandler(Exception)
    def handle_unexpected(err: Exception):
        # 其余 HTTPException（405、413 等）：统一渲染中文错误页，说明原因和下一步
        from werkzeug.exceptions import HTTPException

        if isinstance(err, HTTPException):
            status = err.code or 500
            title, reason, next_step = _http_exception_copy(status, err)
            return _render_error(status, title, reason, next_step)
        request_id = uuid.uuid4().hex[:12]
        logger.exception("未处理异常 request_id=%s path=%s", request_id, request.path)
        return _render_error(
            500,
            "服务暂时不可用",
            "系统遇到了意外错误，请稍后重试。",
            "刷新重试；若仍然失败，请联系平台管理员并提供页面上的请求标识。",
            request_id=request_id,
        )


def _http_exception_copy(status: int, err) -> tuple[str, str, str]:
    """按状态码给出中文标题、原因和下一步（覆盖常见 HTTPException）。"""
    copies = {
        400: ("请求无法处理", "请求参数或格式有误，页面无法处理本次提交。"),
        405: ("请求方式不正确", "该页面不支持当前提交方式，请使用页面上的按钮进行操作。"),
        413: ("内容过大", "提交的内容超过了允许的大小限制。"),
        429: ("请求过于频繁", "操作过于频繁，请稍等片刻再试。"),
    }
    title, reason = copies.get(
        status, ("请求无法处理", "本次请求无法完成（%s）。" % (err.name or "HTTP 错误"))
    )
    next_step = _default_next_step(status)
    return title, reason, next_step


def _default_next_step(status: int) -> str:
    if status == 401:
        return "登录后继续操作。"
    if status == 403:
        return "返回首页，或使用有对应权限的账号登录。"
    if status == 404:
        return "返回首页重新查找。"
    if status == 409:
        return "返回对象详情页查看当前状态。"
    return "返回上一页检查输入内容。"
