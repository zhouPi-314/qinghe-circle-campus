"""物品路由：发布、浏览、详情。

路由只解析请求和输出模板；业务规则在 item_service。
"""

from __future__ import annotations

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from app.core.errors import InputError
from app.core.permissions import login_required, roles_required
from app.services import item_service

bp = Blueprint("items", __name__)

MODE_LABELS = {"borrow": "共享借还", "sale": "二手交易", "give": "免费赠送", "recycle": "绿色回收"}
CONDITION_LABELS = {"new": "全新", "like_new": "几乎全新", "good": "成色良好", "fair": "有使用痕迹"}


@bp.get("/items")
@login_required
def discover():
    """物品发现（FR-I03、FR-I04）：本校物品搜索与筛选。"""
    keyword = request.args.get("q", "").strip() or None
    category_id = request.args.get("category", type=int)
    mode = request.args.get("mode") or None
    campus_id = request.args.get("campus", type=int)
    if mode is not None and mode not in MODE_LABELS:
        mode = None

    items = item_service.search_items(
        g.current_user, keyword=keyword, category_id=category_id, mode=mode, campus_id=campus_id
    )
    return render_template(
        "items/discover.html",
        items=items,
        categories=item_service.list_categories(),
        campuses=item_service.list_university_campuses(g.current_user),
        mode_labels=MODE_LABELS,
        condition_labels=CONDITION_LABELS,
        filters={"q": keyword or "", "category": category_id, "mode": mode, "campus": campus_id},
    )


@bp.route("/items/new", methods=["GET", "POST"])
@roles_required("student")
def new_item():
    """发布物品（FR-I01）：仅在校学生。表单校验失败返回 400 并原位提示。"""
    field_errors: dict[str, str] = {}
    form: dict = {}
    render_status = 200

    if request.method == "POST":
        form = {
            "title": request.form.get("title", ""),
            "description": request.form.get("description", ""),
            "mode": request.form.get("mode", ""),
            "condition": request.form.get("condition", ""),
            "category_id": request.form.get("category_id", ""),
            "campus_id": request.form.get("campus_id", ""),
            "sale_price": request.form.get("sale_price", ""),
        }
        try:
            price_cents = None
            if form["sale_price"]:
                try:
                    price_cents = int(round(float(form["sale_price"]) * 100))
                except ValueError:
                    raise InputError(
                        "价格格式有误。", field_errors={"sale_price": "价格必须是数字。"}
                    ) from None
            item = item_service.create_item(
                g.current_user,
                category_id=int(form["category_id"] or 0),
                mode=form["mode"],
                title=form["title"],
                description=form["description"],
                condition=form["condition"],
                campus_id=int(form["campus_id"] or 0),
                sale_price_cents=price_cents,
            )
            flash("物品发布成功，现在可以被本校同学申请了。", "success")
            return redirect(url_for("items.detail", item_id=item.id))
        except InputError as err:
            field_errors = err.field_errors
            render_status = 400
            if not field_errors:
                flash(err.message, "error")

    return (
        render_template(
            "items/new.html",
            categories=item_service.list_categories(),
            campuses=item_service.list_university_campuses(g.current_user),
            field_errors=field_errors,
            form=form,
            mode_labels=MODE_LABELS,
            condition_labels=CONDITION_LABELS,
        ),
        render_status,
    )


@bp.get("/items/<int:item_id>")
@login_required
def detail(item_id: int):
    """物品详情（FR-I05）：状态、模式、图片、发布者与当前可执行操作。"""
    from flask import current_app

    from app.core.storage import image_public_url

    actor = g.current_user
    item = item_service.get_visible_item(actor, item_id)
    images = [
        {
            "url": image_public_url(current_app.config["APP_CONFIG"], img.object_key),
            "name": img.object_key,
        }
        for img in item_service.list_item_images(item.id)
    ]
    return render_template(
        "items/detail.html",
        item=item,
        history=item_service.item_history(item),
        images=images,
        mode_labels=MODE_LABELS,
        condition_labels=CONDITION_LABELS,
        is_owner=item.owner_user_id == actor.id,
        is_student=actor.is_student,
        can_upload=item.owner_user_id == actor.id and item.status in ("active", "off_shelf"),
        stations=_university_recycle_stations(actor) if item.mode == "recycle" else [],
    )


def _university_recycle_stations(actor):
    """本校启用的回收站点（BR-029：回收物资进入 recycle/mixed 站点）。"""
    from app.services import org_service

    return org_service.list_stations_for(actor, station_types=("recycle", "mixed"))


@bp.post("/items/<int:item_id>/images")
@login_required
def upload_image(item_id: int):
    """上传物品图片（FR-I02）：R2 服务端上传，单张 3MB，最多 5 张。"""
    upload = request.files.get("image")
    if upload is None or not upload.filename:
        from flask import flash

        flash("请选择图片文件。", "error")
        return redirect(url_for("items.detail", item_id=item_id))
    try:
        item_service.add_item_image(
            g.current_user,
            item_id,
            content=upload.read(),
            content_type=upload.mimetype or "image/jpeg",
        )
        from flask import flash

        flash("图片上传成功。", "success")
    except InputError as err:
        from flask import flash

        flash(err.message, "error")
    return redirect(url_for("items.detail", item_id=item_id))
