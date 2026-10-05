import logging


_logger = logging.getLogger(__name__)


def migrate(cr, version):
    # Đơn nhập tay trên hệ thống luôn mang mã sequence ORD/... (readonly
    # nên người dùng không tự gõ mã khác); mã còn lại là đơn HNCK lấy
    # về qua API trước khi có cờ hnck_order.
    cr.execute(
        """
        UPDATE sale_order
        SET hnck_order = TRUE
        WHERE catering_reference NOT LIKE 'ORD/%'
          AND catering_reference <> 'Mới'
        """
    )
    _logger.info("Backfilled hnck_order: %s orders", cr.rowcount)
