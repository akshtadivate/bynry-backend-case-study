# Part 2 – Database Design: StockFlow (B2B SaaS Inventory Management)

### Tables and Relationships
**1. Companies**
- `id` (PK)
- `name`
- `contact_email`
- Each company can own multiple warehouses.

**2. Warehouses**
- `id` (PK)
- `company_id` (FK → companies.id)
- `name`, `location`
- One company → many warehouses.

**3. Products**
- `id` (PK)
- `name`, `sku` (unique), `price`, `description`
- Products can exist in multiple warehouses.

**4. Inventory**
- `id` (PK)
- `product_id` (FK → products.id)
- `warehouse_id` (FK → warehouses.id)
- `quantity`, `last_updated`
- Tracks product stock in each warehouse.

**5. Suppliers**
- `id` (PK)
- `name`, `contact_email`, `phone_number`

**6. Product_Suppliers**
- Links suppliers to products (many-to-many)
- Unique constraint on (`product_id`, `supplier_id`)

**7. Inventory_History**
- Tracks all stock changes (additions, sales, transfers)
- Columns: `inventory_id`, `change_type`, `quantity_changed`, `previous_quantity`, `new_quantity`, `changed_at`

**8. Product_Bundles**
- Supports bundle products (e.g., “Combo Pack”)
- Columns: `parent_product_id`, `child_product_id`, `quantity_per_bundle`

---

###  Questions / Missing Details
- Should each product belong to only one company, or can companies share product definitions?
- Should bundles allow nested bundles?
- How often should inventory history be archived?
- Do suppliers provide specific SKUs or entire categories?

---

### Design Choices
- Added **unique SKU constraint** to avoid duplicates.
- Indexed `warehouse_id`, `product_id` in `inventory` for faster lookups.
- Added `inventory_history` for full audit trail.
- Normalized relationships to maintain data consistency.

