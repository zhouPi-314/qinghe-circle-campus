"""青禾流转 Flask 应用工厂。

依赖方向固定为 route/blueprint -> service -> model/database（工程标准第 3 节）。
"""

from __future__ import annotations

from pathlib import Path

from flask import Flask
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def create_app(*, testing: bool = False) -> Flask:
    """创建并配置应用实例。

    - 解析环境配置并快速失败；
    - 初始化数据库、错误处理、CSRF、模板过滤器和蓝图；
    - 模型通过 app.models 导入以完成表注册。
    """
    from app.config import Config, flask_config_from

    config = Config(project_root=PROJECT_ROOT)
    config.validate()
    config.testing = testing

    app = Flask(__name__, template_folder="templates", static_folder="static")
    # 路由尾部斜杠不强制重定向（/admin 与 /admin/ 视为同一地址）
    app.url_map.strict_slashes = False
    app.config.update(flask_config_from(config, testing=testing))
    app.config["APP_CONFIG"] = config

    db.init_app(app)

    from app.core.sms import sms_sender_from_config

    app.extensions["sms_sender"] = sms_sender_from_config(config)

    from app.core.auth import register_auth_hooks
    from app.core.errors import register_error_handlers
    from app.core.security_monitor import enforce_public_origin

    register_error_handlers(app)
    app.before_request(enforce_public_origin)
    register_auth_hooks(app)

    _register_template_helpers(app)

    from app.routes.admin import bp as admin_bp
    from app.routes.auth import bp as auth_bp
    from app.routes.charity import bp as charity_bp
    from app.routes.circulation import bp as circulation_bp
    from app.routes.items import bp as items_bp
    from app.routes.main import bp as main_bp
    from app.routes.me import bp as me_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(me_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(items_bp)
    app.register_blueprint(circulation_bp)
    app.register_blueprint(charity_bp)

    _import_models()

    return app


def _import_models() -> None:
    """导入模型模块，确保 SQLAlchemy 表定义已注册。"""
    from app.models import charity, circulation, governance, item, university, user  # noqa: F401


def _register_template_helpers(app: Flask) -> None:
    """注册模板公共函数与过滤器。"""
    from app.core.display import register_display_helpers

    register_display_helpers(app)
