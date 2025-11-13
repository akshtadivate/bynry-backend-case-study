# PART 1 — Code Review, Issues, Impact & Fixes
Given code
@app.route('/api/products', methods=['POST'])
def create_product():
    data = request.json
    
    # Create new product
    product = Product(
        name=data['name'],
        sku=data['sku'],
        price=data['price'],
        warehouse_id=data['warehouse_id']
    )
    
    db.session.add(product)
    db.session.commit()
    
    # Update inventory count
    inventory = Inventory(
        product_id=product.id,
        warehouse_id=data['warehouse_id'],
        quantity=data['initial_quantity']
    )
    
    db.session.add(inventory)
    db.session.commit()
    
    return {"message": "Product created", "product_id": product.id}

Problems (what’s wrong) — short list with impact

Product contains warehouse_id

Why wrong: Products can exist in many warehouses. Storing warehouse_id on Product couples product to one warehouse.

Impact: Data model mismatch; impossible to represent product in multiple warehouses correctly.

No input validation

Why wrong: Missing required/optional fields checks and type validation.

Impact: Server errors (KeyError), garbage data, crashes.

SKU uniqueness not enforced or checked

Why wrong: SKUs must be unique platform-wide. No check or DB constraint shown.

Impact: Duplicate SKUs causing product ambiguity and inventory errors.

Price stored as float / not using Decimal/Numeric

Why wrong: Floating point for money causes precision issues.

Impact: Rounding errors, billing inaccuracies.

Multiple commits — not transactional

Why wrong: Commits product then inventory separately.

Impact: Partial state if crash between commits — product without inventory or duplicated entities.

No check/validation for warehouse existence / ownership

Why wrong: Could create inventory for invalid warehouse.

Impact: Orphaned inventory rows or security/multi-tenant errors.

Inventory insert might duplicate rows

Why wrong: No unique constraint on (product_id, warehouse_id) or upsert logic.

Impact: Duplicate inventory entries and wrong counts.

No audit/history for inventory changes

Why wrong: No tracking of who/when changed stock.

Impact: Hard to debug changes, impossible to compute supply chain metrics.

No concurrency control

Why wrong: Concurrent requests can race when creating same SKU or updating same inventory.

Impact: Lost updates, duplicate rows.

No error handling or correct HTTP codes

Why wrong: Always returns 200-like dict, no 400/409/500.

Impact: Poor client UX, hard error semantics.

Fix summary

Validate input.

Use Decimal / NUMERIC for price.

Enforce SKU uniqueness at DB + handle IntegrityError.

Use a single DB transaction for product + inventory creation.

Use unique constraint on inventory (product_id, warehouse_id) and upsert/update when needed.

Check warehouse exists and belongs to caller’s company (if multi-tenant).

Create inventory_history record.

Return proper HTTP status codes.

Use SELECT ... FOR UPDATE (or SQLAlchemy with_for_update) when updating inventory to avoid races.

Corrected endpoint (Flask + SQLAlchemy, minimal)

Put this in part1_code_review.md or directly into your Flask app. This version is concise but production-minded.

# part1_code_review.py 
from flask import Blueprint, request, jsonify
from decimal import Decimal, InvalidOperation
from sqlalchemy.exc import IntegrityError
from datetime import datetime

bp = Blueprint('products', __name__)

@bp.route('/api/products', methods=['POST'])
def create_product():
    """
    Create a product and initial inventory (optional). 
    - Validates input.
    - Ensures SKU uniqueness.
    - Uses single transaction to avoid partial state.
    - Creates or updates inventory row (product+warehouse).
    - Logs inventory history.
    """
    data = request.get_json() or {}
    # Required fields
    name = data.get('name')
    sku = data.get('sku')
    price_raw = data.get('price')
    initial_quantity = data.get('initial_quantity', 0)
    warehouse_id = data.get('warehouse_id')  # optional
    
    if not name or not sku or price_raw is None:
        return jsonify({"error": "Missing required fields: name, sku, price"}), 400

    # Price -> Decimal
    try:
        price = Decimal(str(price_raw))
    except (InvalidOperation, TypeError):
        return jsonify({"error": "Invalid price format"}), 400

    # qty validation
    try:
        qty = int(initial_quantity)
        if qty < 0:
            raise ValueError()
    except Exception:
        return jsonify({"error": "initial_quantity must be non-negative integer"}), 400

    # If warehouse_id provided, validate existence
    if warehouse_id is not None:
        warehouse = Warehouse.query.get(warehouse_id)
        if not warehouse:
            return jsonify({"error": "Invalid warehouse_id"}), 400

    try:
        with db.session.begin():  # transaction
            product = Product(name=name, sku=sku, price=price)
            db.session.add(product)
            db.session.flush()  # assign product.id

            # If warehouse specified, create/update inventory
            if warehouse_id is not None:
                inv = (db.session.query(Inventory)
                       .filter_by(product_id=product.id, warehouse_id=warehouse_id)
                       .with_for_update(nowait=False)
                       .one_or_none())
                if inv:
                    # increase existing inventory (or choose set depending on requirements)
                    inv.quantity += qty
                    inv.last_updated = datetime.utcnow()
                else:
                    inv = Inventory(product_id=product.id, warehouse_id=warehouse_id, quantity=qty)
                    db.session.add(inv)
                    db.session.flush()

                # add history record
                history = InventoryHistory(
                    inventory_id=inv.id,
                    product_id=product.id,
                    warehouse_id=warehouse_id,
                    change=qty,
                    reason='initial_stock',
                    created_at=datetime.utcnow()
                )
                db.session.add(history)
    except IntegrityError as e:
        db.session.rollback()
        # probably SKU uniqueness violation
        return jsonify({"error": "SKU already exists"}), 409
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Internal error", "detail": str(e)}), 500

    return jsonify({"message": "Product created", "product_id": product.id}), 201
