import logging


_logger = logging.getLogger(__name__)

# Payload của foods/paginate mang các chỉ số dinh dưỡng mà
# standard-foods không có; dùng để nhận diện bản ghi cũ.
FOODS_PAYLOAD_KEYS = ["calo", "protein", "fat"]


def migrate(cr, version):
    cr.execute(
        """
        UPDATE product_template
        SET crall_food_source = 'foods'
        WHERE crall_supplier_id IS NOT NULL
          AND crall_food_source IS NULL
          AND crall_supplier_payload IS NOT NULL
          AND (crall_supplier_payload::jsonb ?| %s)
        """,
        (FOODS_PAYLOAD_KEYS,),
    )
    foods_marked = cr.rowcount
    cr.execute(
        """
        UPDATE product_template
        SET crall_food_source = 'standard'
        WHERE crall_supplier_id IS NOT NULL
          AND crall_food_source IS NULL
        """
    )
    _logger.info(
        "Backfilled crall_food_source: %s foods, %s standard",
        foods_marked,
        cr.rowcount,
    )
