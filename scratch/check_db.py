from app import app, db, Tenant, Branch, User, Order, Product
with app.app_context():
    try:
        print("Checking tables...")
        print(f"Tenants: {Tenant.query.count()}")
        print(f"Branches: {Branch.query.count()}")
        print(f"Users: {User.query.count()}")
        print("Success!")
    except Exception as e:
        print(f"Error: {e}")
