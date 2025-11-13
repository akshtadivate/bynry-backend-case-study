from flask import Flask, jsonify, request, abort
from datetime import datetime, timedelta
import math
from sqlalchemy import func

app = Flask(__name__)
# Assume db, models are imported from your app context:
# from models import db, Company, Warehouse, Inventory, Product, OrderItem, Order, Supplier, ProductSupplier

# Configurable windows
SALES_AVG_WINDOW_DAYS = 30   # compute avg daily sales over last 30 days
SALES_ACTIVITY_WINDOW_DAYS = 60  # product must have sales within last 60 days to alert

@app.route('/api/companies/<int:company_id>/alerts/low-stock', methods=['GET'])
def low_stock_alerts(company_id):
    """
    Returns low-stock alerts for a company across its warehouses.
    Business rules:
    - Consider inventories where quantity <= threshold.
    - Only products with sales within last SALES_ACTIVITY_WINDOW_DAYS.
    - Provide avg_daily_sales over SALES_AVG_WINDOW_DAYS to calculate days_until_stockout.
    - Attach supplier (primary if set).
    """

    # Validate company
    company = Company.query.get(company_id)
    if not company:
        return jsonify({"error": "Company not found"}), 404

    now = datetime.utcnow()
    avg_since = now - timedelta(days=SALES_AVG_WINDOW_DAYS)
    activity_since = now - timedelta(days=SALES_ACTIVITY_WINDOW_DAYS)

    # Step 1: Candidate inventories where current_stock <= threshold
    # Join warehouses to ensure belongs to company
    candidate_rows = (
        db.session.query(Inventory, Product, Warehouse)
        .join(Warehouse, Inventory.warehouse_id == Warehouse.id)
        .join(Product, Inventory.product_id == Product.id)
        .filter(Warehouse.company_id == company_id)
        .filter(Inventory.quantity <= Inventory.threshold)
        .all()
    )

    if not candidate_rows:
        return jsonify({"alerts": [], "total_alerts": 0}), 200

    # Collect product_ids and inventory rows
    product_ids = list({prod.id for _, prod, _ in candidate_rows})

    # Step 2: Aggregate recent sales (activity) across products in one query (sales in activity window)
    recent_sales = (
        db.session.query(OrderItem.product_id, func.coalesce(func.sum(OrderItem.quantity), 0).label('qty'))
        .join(Order, OrderItem.order_id == Order.id)
        .filter(Order.company_id == company_id)
        .filter(OrderItem.product_id.in_(product_ids))
        .filter(OrderItem.created_at >= activity_since)
        .group_by(OrderItem.product_id)
        .all()
    )
    recent_sales_map = {r.product_id: r.qty for r in recent_sales}

    # Step 3: Aggregate sales in avg window (for avg daily sales)
    avg_sales = (
        db.session.query(OrderItem.product_id, func.coalesce(func.sum(OrderItem.quantity), 0).label('qty'))
        .join(Order, OrderItem.order_id == Order.id)
        .filter(Order.company_id == company_id)
        .filter(OrderItem.product_id.in_(product_ids))
        .filter(OrderItem.created_at >= avg_since)
        .group_by(OrderItem.product_id)
        .all()
    )
    avg_sales_map = {r.product_id: r.qty for r in avg_sales}

    # Step 4: Get supplier info for relevant products in batch
    suppliers_q = (
        db.session.query(ProductSupplier.product_id, Supplier.id, Supplier.name, Supplier.contact_email, ProductSupplier.is_primary)
        .join(Supplier, ProductSupplier.supplier_id == Supplier.id)
        .filter(ProductSupplier.product_id.in_(product_ids))
    ).all()

    # Build supplier map: product_id -> best supplier (primary preferred)
    supplier_map = {}
    for prod_id, sup_id, sup_name, sup_email, is_primary in suppliers_q:
        entry = supplier_map.get(prod_id)
        if entry is None:
            supplier_map[prod_id] = {"id": sup_id, "name": sup_name, "contact_email": sup_email, "is_primary": is_primary}
        else:
            # prefer primary
            if is_primary and not entry.get('is_primary'):
                supplier_map[prod_id] = {"id": sup_id, "name": sup_name, "contact_email": sup_email, "is_primary": is_primary}

    alerts = []
    for inv, prod, wh in candidate_rows:
        pid = prod.id
        # only alert if product had recent sales activity
        recent_qty = recent_sales_map.get(pid, 0)
        if recent_qty == 0:
            # skip as per business rule
            continue

        total_sold_in_avg = avg_sales_map.get(pid, 0)
        avg_daily_sales = total_sold_in_avg / max(SALES_AVG_WINDOW_DAYS, 1)

        if avg_daily_sales > 0:
            days_until_stockout = math.ceil(inv.quantity / avg_daily_sales)
        else:
            days_until_stockout = None

        supplier_info = None
        if pid in supplier_map:
            s = supplier_map[pid]
            supplier_info = {"id": s["id"], "name": s["name"], "contact_email": s["contact_email"]}

        alerts.append({
            "product_id": pid,
            "product_name": prod.name,
            "sku": prod.sku,
            "warehouse_id": wh.id,
            "warehouse_name": wh.name,
            "current_stock": inv.quantity,
            "threshold": inv.threshold,
            "days_until_stockout": days_until_stockout,
            "supplier": supplier_info
        })

    return jsonify({"alerts": alerts, "total_alerts": len(alerts)}), 200
