#!/usr/bin/env python3
"""
Database Migration Script: Convert POS Cafe to Multi-tenant SaaS
This script assigns all existing data to a 'Default Tenant' to preserve the current data.
Run this once after deploying the multi-tenant models.
"""

import os
import sys
from datetime import datetime

# Add the app directory to the path
sys.path.insert(0, os.path.dirname(__file__))

from app import app, db, Tenant, User, Branch, Product, Category, Floor, Table, PaymentMethod
from app import CafeSettings, Session, Order, OrderItem, KitchenTicket, Review, Reservation
from app import ReservationItem, PushSubscription, AttendanceEvent

def create_default_tenant():
    """Create the default tenant if it doesn't exist."""
    default_tenant = Tenant.query.filter_by(slug='default').first()
    if default_tenant:
        print("✓ Default tenant already exists (ID: {})".format(default_tenant.id))
        return default_tenant
    
    default_tenant = Tenant(
        name='Default Tenant',
        slug='default',
        plan='free',
        is_active=True
    )
    db.session.add(default_tenant)
    db.session.commit()
    print("✓ Created default tenant (ID: {})".format(default_tenant.id))
    return default_tenant

def migrate_data_to_tenant(tenant):
    """Assign all existing data without tenant_id to the default tenant."""
    tenant_id = tenant.id
    
    models_to_migrate = [
        (Branch, 'Branch'),
        (User, 'User'),
        (Category, 'Category'),
        (Product, 'Product'),
        (Floor, 'Floor'),
        (Table, 'Table'),
        (PaymentMethod, 'PaymentMethod'),
        (CafeSettings, 'CafeSettings'),
        (Session, 'Session'),
        (Order, 'Order'),
        (KitchenTicket, 'KitchenTicket'),
        (Review, 'Review'),
        (Reservation, 'Reservation'),
        (PushSubscription, 'PushSubscription'),
        (AttendanceEvent, 'AttendanceEvent'),
    ]
    
    for model, name in models_to_migrate:
        try:
            # Only update records that don't have a tenant_id yet
            if hasattr(model, 'tenant_id'):
                count = db.session.query(model).filter(model.tenant_id.is_(None)).count()
                if count > 0:
                    db.session.query(model).filter(model.tenant_id.is_(None)).update({model.tenant_id: tenant_id})
                    db.session.commit()
                    print("✓ Migrated {} {} records to default tenant".format(count, name))
                else:
                    print("  {} records already have tenant_id assigned".format(name))
            else:
                print("  {} model doesn't have tenant_id column".format(name))
        except Exception as e:
            print("✗ Error migrating {}: {}".format(name, str(e)))
            db.session.rollback()
            return False
    
    return True

def set_tenant_owner(tenant, user):
    """Set the first restaurant admin as the tenant owner."""
    if not tenant.owner_id:
        tenant.owner_id = user.id
        db.session.commit()
        print("✓ Set user '{}' ({}) as tenant owner".format(user.name, user.email))

def main():
    with app.app_context():
        print("\n" + "="*60)
        print("POS Cafe Multi-Tenant SaaS Migration")
        print("="*60 + "\n")
        
        try:
            # Step 1: Create default tenant
            print("Step 1: Creating default tenant...")
            default_tenant = create_default_tenant()
            
            # Step 2: Migrate existing data
            print("\nStep 2: Migrating existing data to default tenant...")
            if not migrate_data_to_tenant(default_tenant):
                print("\n✗ Migration failed!")
                return False
            
            # Step 3: Set tenant owner (first superadmin or restaurant admin)
            print("\nStep 3: Setting tenant owner...")
            owner = User.query.filter_by(is_superadmin=True).first()
            if not owner:
                owner = User.query.filter_by(role='restaurant').first()
            if owner:
                set_tenant_owner(default_tenant, owner)
            else:
                print("  No superadmin or restaurant admin found. Tenant owner not set.")
            
            print("\n" + "="*60)
            print("✓ Migration completed successfully!")
            print("="*60 + "\n")
            print("Summary:")
            print("  - Default Tenant ID: {}".format(default_tenant.id))
            print("  - Tenant Name: {}".format(default_tenant.name))
            print("  - All existing records now belong to this tenant")
            print("\nNext steps:")
            print("  1. Users login and get tenant_id in session automatically")
            print("  2. Platform admins can manage multiple tenants")
            print("  3. New restaurants can be created with /api/register-restaurant")
            print("\n")
            return True
            
        except Exception as e:
            print("\n✗ Unexpected error: {}".format(str(e)))
            import traceback
            traceback.print_exc()
            return False

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
