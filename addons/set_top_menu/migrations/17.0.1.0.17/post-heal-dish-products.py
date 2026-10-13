import logging

from odoo import SUPERUSER_ID, api


_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Bật sẵn cờ bán được trên bảng mẫu cho các món đang hoạt động.

    Cột chọn đơn hàng lọc theo cờ này nên dữ liệu cũ phải được chữa
    một lần khi nâng cấp (món mới và món được sửa đã tự chữa ở model).
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    dishes = env["set_top_menu.menu.item"].search([("active", "=", True)])
    dishes._ensure_sale_product()
    _logger.info("Ensured saleable products for %s dishes", len(dishes))
